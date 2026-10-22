"""Shared helpers for Pippit Nest Skill OpenAPI calls."""

import json
import os
import sys
from urllib.parse import urlencode, urlparse
import urllib.error
import urllib.request

_RAW_PIPPIT_BASE = os.environ.get("PIPPIT_OPENAPI_BASE", os.environ.get("PIPPIT_BASE_URL", "https://www.pippit.ai"))
PIPPIT_HOME_URL = os.environ.get("PIPPIT_HOME_URL", "https://www.pippit.ai/home?")

CODEX_HOME = os.environ.get("CODEX_HOME", os.path.expanduser("~/.codex"))
ACCESS_KEY_STORAGE_KEY = "PippitAccessKey"
DEFAULT_ACCESS_KEY_FILE = os.environ.get(
    "PIPPIT_ACCESS_KEY_FILE",
    os.path.join(CODEX_HOME, "pippit-skill", "secrets.json"),
)

SUBMIT_RUN_PATH = "/api/biz/v1/skill/submit_run"
GET_THREAD_PATH = "/api/biz/v1/skill/get_thread"
UPLOAD_FILE_PATH = "/api/biz/v1/skill/upload_file"

HIDDEN_CONTENT_SUB_TYPES = {"biz/general_agent_settings"}


def normalize_api_base(value: str) -> str:
    raw = (value or "https://www.pippit.ai").strip()
    parsed = urlparse(raw)
    if parsed.scheme and parsed.netloc and parsed.path.rstrip("/") == "/home":
        return f"{parsed.scheme}://{parsed.netloc}"
    return raw.rstrip("/")


PIPPIT_BASE = normalize_api_base(_RAW_PIPPIT_BASE)


def load_stored_access_key() -> str:
    path = DEFAULT_ACCESS_KEY_FILE
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as fp:
            data = json.load(fp)
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(data, dict):
        return ""
    value = data.get(ACCESS_KEY_STORAGE_KEY, "")
    return value.strip() if isinstance(value, str) else ""


def resolve_access_key() -> str:
    candidates = [
        os.environ.get("PIPPIT_ACCESS_KEY", ""),
        os.environ.get(ACCESS_KEY_STORAGE_KEY, ""),
        load_stored_access_key(),
    ]
    for value in candidates:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


ACCESS_KEY = resolve_access_key()


def ensure_access_key() -> None:
    if ACCESS_KEY:
        return
    print(
        "Error: set PIPPIT_ACCESS_KEY, set PippitAccessKey, or save a local PippitAccessKey first. "
        "If you do not have one, get it from https://www.pippit.ai/home?.",
        file=sys.stderr,
    )
    sys.exit(1)


def save_access_key(access_key: str, path: str = DEFAULT_ACCESS_KEY_FILE) -> str:
    value = (access_key or "").strip()
    if not value:
        print("Error: access key cannot be empty", file=sys.stderr)
        sys.exit(1)

    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, mode=0o700, exist_ok=True)

    payload = {ACCESS_KEY_STORAGE_KEY: value}
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=2)
        fp.write("\n")
    os.chmod(path, 0o600)
    return path


def _headers(content_type: str = "application/json") -> dict:
    headers = {
        "Authorization": f"Bearer {ACCESS_KEY}",
    }
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def api_post(path: str, body: dict) -> dict:
    ensure_access_key()
    url = f"{PIPPIT_BASE.rstrip('/')}{path}"
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8") if exc.fp else ""
        print(f"API error {exc.code}: {err_body}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as exc:
        print(f"Network error: {exc.reason}", file=sys.stderr)
        sys.exit(1)


def parse_response(resp: dict) -> dict:
    ret = str(resp.get("ret", ""))
    if ret != "0":
        errmsg = resp.get("errmsg", "unknown error")
        print(f"Error code: {ret}, message: {errmsg}", file=sys.stderr)
        sys.exit(1)
    data = resp.get("data", {})
    return data if isinstance(data, dict) else {}


def submit_run(thread_id: str = "", message: str = "", asset_ids: list = None) -> dict:
    body = {}
    if thread_id:
        body["thread_id"] = thread_id
    if message:
        body["message"] = message
    if asset_ids:
        body["asset_ids"] = asset_ids
    return parse_response(api_post(SUBMIT_RUN_PATH, body))


def get_thread(thread_id: str, run_id: str, after_seq: int = 0) -> dict:
    if not run_id:
        print("Error: run_id is required by the Pippit Skill get_thread API", file=sys.stderr)
        sys.exit(1)

    body = {"thread_id": thread_id, "run_id": run_id, "after_seq": after_seq}
    data = parse_response(api_post(GET_THREAD_PATH, body))

    thread = data.get("thread", {})
    run_list = thread.get("run_list", [])
    if not run_list:
        print("Error: response did not include thread.run_list", file=sys.stderr)
        sys.exit(1)

    run = None
    for candidate in run_list:
        if candidate.get("run_id") == run_id:
            run = candidate
            break
    if run is None:
        print(f"Error: response did not include run_id {run_id}", file=sys.stderr)
        sys.exit(1)

    state = get_run_status(run)
    if state == "completed":
        print("Status: generation completed", file=sys.stderr)
        return run
    if state == "failed":
        fail_reason = run.get("fail_reason", "unknown failure")
        print(f"Error: {fail_reason}", file=sys.stderr)
        sys.exit(1)
    if state == "canceled":
        print("Error: generation was canceled", file=sys.stderr)
        sys.exit(1)
    if state == "requires_action":
        print("Status: clarification or interaction required", file=sys.stderr)
        return run

    print("Status: generation in progress", file=sys.stderr)
    return run


def normalize_state(value) -> str:
    if isinstance(value, int):
        state_value = str(value)
    else:
        state_value = str(value or "").strip().lower()

    completed = {"3", "completed", "complete", "succeeded", "success", "done", "runstate_completed"}
    failed = {"4", "failed", "failure", "error", "runstate_failed"}
    canceled = {"5", "canceled", "cancelled", "runstate_canceled"}
    requires_action = {
        "9",
        "requires_action",
        "requires_user_input",
        "interaction_required",
        "runstate_requires_action",
    }

    if state_value in completed:
        return "completed"
    if state_value in failed:
        return "failed"
    if state_value in canceled:
        return "canceled"
    if state_value in requires_action:
        return "requires_action"
    return "running"


def get_run_status(run: dict) -> str:
    state = normalize_state(run.get("state", ""))
    if state == "running" and extract_interactions_from_run(run):
        return "requires_action"
    return state


def build_web_thread_link(thread_id: str) -> str:
    if not thread_id:
        return ""
    params = urlencode(
        {
            "tab_name": "integrated-agent",
            "thread_id": thread_id,
            "agent_name": "pippit_nest_agent",
        }
    )
    if PIPPIT_HOME_URL.endswith("?") or PIPPIT_HOME_URL.endswith("&"):
        return f"{PIPPIT_HOME_URL}{params}"
    separator = "&" if "?" in PIPPIT_HOME_URL else "?"
    return f"{PIPPIT_HOME_URL}{separator}{params}"


def extract_entries_from_run(run: dict) -> list:
    matched = []
    for entry in run.get("entry_list") or []:
        item = {}
        message = entry.get("message")
        artifact = entry.get("artifact")
        if message:
            item["id"] = message.get("message_id", "")
            item["role"] = message.get("role", "")
            item["content"] = visible_content(message.get("content", []))
            client_tool_calls = as_list(message.get("client_tool_calls", []))
            if client_tool_calls:
                item["content"].extend(client_tool_calls)
        if artifact:
            item["id"] = artifact.get("artifact_id", "")
            item["role"] = artifact.get("role", "")
            item["content"] = visible_content(artifact.get("content", []))
        if item:
            matched.append(item)
    return matched


def visible_content(value):
    return [
        content
        for content in as_list(value)
        if not (
            isinstance(content, dict)
            and (content.get("sub_type") or content.get("subtype")) in HIDDEN_CONTENT_SUB_TYPES
        )
    ]


def extract_interactions_from_run(run: dict) -> list:
    return extract_interactions_from_messages(extract_entries_from_run(run))


def extract_interactions_from_messages(messages: list) -> list:
    interactions = []
    for message in messages:
        for content in as_list(message.get("content", [])):
            if not isinstance(content, dict):
                continue
            sub_type = content.get("sub_type") or content.get("subtype")
            if sub_type != "biz/x_data_dynamic_questionnaire":
                continue
            decoded = decode_content_data(content.get("data"))
            interaction = {
                "id": message.get("id", ""),
                "role": message.get("role", ""),
                "type": content.get("type", ""),
                "sub_type": sub_type,
                "data": decoded,
            }
            questions = extract_question_candidates(decoded)
            if questions:
                interaction["question"] = questions[0]
                interaction["questions"] = questions
            interactions.append(interaction)
    return interactions


def extract_download_urls_from_messages(messages: list) -> list:
    urls = []
    seen = set()
    for message in messages:
        # Download results should represent generated outputs, not uploaded/reference
        # assets echoed back by the thread.
        if message.get("role") != "assistant":
            continue
        for content in as_list(message.get("content", [])):
            if not isinstance(content, dict):
                continue
            sub_type = content.get("sub_type") or content.get("subtype") or ""
            if "upload" in sub_type:
                continue
            decoded = decode_content_data(content.get("data"))
            for path, url in iter_result_urls(decoded):
                if url in seen:
                    continue
                seen.add(url)
                urls.append(
                    {
                        "url": url,
                        "id": message.get("id", ""),
                        "role": message.get("role", ""),
                        "type": content.get("type", ""),
                        "sub_type": content.get("sub_type") or content.get("subtype") or "",
                        "path": path,
                    }
                )
    return urls


def extract_generated_assets_from_messages(messages: list) -> list:
    assets = []
    seen = set()
    for message in messages:
        for content in as_list(message.get("content", [])):
            if not isinstance(content, dict):
                continue
            decoded = decode_content_data(content.get("data"))
            for path, asset in iter_generated_assets(decoded):
                identity = (
                    asset.get("pippit_asset_id", ""),
                    asset.get("asset_id", ""),
                    asset.get("url", ""),
                    path,
                )
                if identity in seen:
                    continue
                seen.add(identity)
                item = {
                    "id": message.get("id", ""),
                    "role": message.get("role", ""),
                    "type": content.get("type", ""),
                    "sub_type": content.get("sub_type") or content.get("subtype") or "",
                    "path": path,
                }
                item.update(asset)
                assets.append(item)
    return assets


def decode_content_data(value):
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped:
        return value
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return value


def extract_question_candidates(value) -> list:
    questionnaire_questions = extract_questionnaire_questions(value)
    if questionnaire_questions:
        return questionnaire_questions

    preferred_keys = {"question", "title", "text", "content", "message", "desc", "description", "prompt"}
    candidates = []
    collect_strings_by_key(value, preferred_keys, candidates)
    if not candidates:
        collect_strings(value, candidates)
    return dedupe_strings(candidates)


def extract_questionnaire_questions(value) -> list:
    candidates = []
    if isinstance(value, dict):
        questions = value.get("questions")
        if isinstance(questions, list):
            for question in questions:
                if not isinstance(question, dict):
                    continue
                for key in ("question", "title", "text", "content", "message", "description", "desc", "prompt"):
                    item = question.get(key)
                    if isinstance(item, str):
                        candidates.append(item)
                        break
        for item in value.values():
            candidates.extend(extract_questionnaire_questions(item))
    elif isinstance(value, list):
        for item in value:
            candidates.extend(extract_questionnaire_questions(item))
    return dedupe_strings(candidates)


def collect_strings_by_key(value, keys: set, output: list) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, str) and key.lower() in keys:
                output.append(item)
            else:
                collect_strings_by_key(item, keys, output)
    elif isinstance(value, list):
        for item in value:
            collect_strings_by_key(item, keys, output)


def collect_strings(value, output: list) -> None:
    if isinstance(value, str):
        output.append(value)
    elif isinstance(value, dict):
        for item in value.values():
            collect_strings(item, output)
    elif isinstance(value, list):
        for item in value:
            collect_strings(item, output)


def dedupe_strings(values: list) -> list:
    result = []
    seen = set()
    for value in values:
        text = " ".join(str(value).split())
        if not text or text in seen or text.startswith("http://") or text.startswith("https://"):
            continue
        seen.add(text)
        result.append(text)
    return result


def iter_result_urls(value, path: str = ""):
    if isinstance(value, dict):
        for key, item in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            key_lower = str(key).lower()
            is_url_key = (
                key_lower in {"download_url", "url"}
                or key_lower.endswith("_url")
                or key_lower.endswith("_urls")
            )
            if is_url_key and isinstance(item, str) and item.startswith(("http://", "https://")):
                yield child_path, item
            elif is_url_key and isinstance(item, list):
                for index, url in enumerate(item):
                    if isinstance(url, str) and url.startswith(("http://", "https://")):
                        yield f"{child_path}[{index}]", url
            yield from iter_result_urls(item, child_path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            child_path = f"{path}[{index}]" if path else f"[{index}]"
            yield from iter_result_urls(item, child_path)


def iter_generated_assets(value, path: str = ""):
    if isinstance(value, dict):
        if any(key in value for key in ("asset_id", "pippit_asset_id", "url", "download_url")):
            asset = normalize_asset_info(value)
            if asset:
                yield path, asset
        for key, item in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            yield from iter_generated_assets(item, child_path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            child_path = f"{path}[{index}]" if path else f"[{index}]"
            yield from iter_generated_assets(item, child_path)


def normalize_asset_info(value: dict) -> dict:
    asset = {}
    for key in ("asset_id", "pippit_asset_id", "uri", "url", "download_url", "caption", "name"):
        item = value.get(key)
        if item:
            asset[key] = item
    metadata = value.get("metadata")
    if isinstance(metadata, dict):
        for key in ("width", "height", "format", "mime", "ratio", "size"):
            item = metadata.get(key)
            if item:
                asset[key] = item
    for key in ("width", "height", "format", "mime", "ratio", "size"):
        item = value.get(key)
        if item:
            asset[key] = item
    return asset


def as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]
