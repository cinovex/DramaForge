"""Shared Pippit Skill OpenAPI helpers for accounts, uploads, task CRUD, and analytics."""

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

PIPPIT_BASE = os.environ.get("PIPPIT_OPENAPI_BASE", os.environ.get("PIPPIT_BASE_URL", "https://www.pippit.ai"))
CODEX_HOME = os.environ.get("CODEX_HOME", os.path.expanduser("~/.codex"))
ACCESS_KEY_STORAGE_KEY = "PippitAccessKey"
DEFAULT_ACCESS_KEY_FILE = os.environ.get(
    "PIPPIT_ACCESS_KEY_FILE",
    os.path.join(CODEX_HOME, "pippit-skill", "secrets.json"),
)

LIST_USER_PLATFORM_ACCOUNT_PATH = "/api/biz/v1/common/skill/list_user_platform_account"
UPLOAD_FILE_PATH = "/api/biz/v1/skill/upload_file"
BATCHCREATE_SCHEDULE_TASK_PATH = "/api/biz/v1/publish/skill/batchcreate_schedule_task"
LIST_SCHEDULE_TASK_PATH = "/api/biz/v1/publish/skill/list_schedule_task"
UPDATE_SCHEDULE_TASK_PATH = "/api/biz/v1/publish/skill/update_schedule_task"
DELETE_SCHEDULE_TASK_PATH = "/api/biz/v1/publish/skill/delete_schedule_task"
LIST_VIDEOS_PATH = "/api/biz/v1/analytics/skill/videos"

PLATFORM_MAP = {
    "tiktok": 1,
    "facebook": 301,
    "facebook-page": 301,
    "facebook_page": 301,
    "instagram": 311,
    "ins": 311,
}

PUBLISH_TYPE_SCHEDULE = 2

TASK_TYPE_PUBLISH_MEDIA = 1
ACTION_TYPE_SAVE = 1
ACTION_TYPE_PUBLISH = 2
DEFAULT_ACTION_FROM = 0
DEFAULT_FILE_TYPE = 1
TASK_STATUS_MAP = {
    "pending": 1,
    "processing": 2,
    "done": 3,
    "failed": 4,
    "canceled": 5,
    "cancelled": 5,
    "init": 6,
    "partial-success": 7,
    "partial_success": 7,
    "queueing": 8,
}

ACTION_TYPE_MAP = {
    "save": ACTION_TYPE_SAVE,
    "publish": ACTION_TYPE_PUBLISH,
}

TIKTOK_PRIVACY_MAP = {
    "public": 1,
    "mutual": 2,
    "self": 3,
    "followers": 4,
}

VIDEO_ASSET_TYPE = 1
TIKTOK_VIDEO_MEDIA_TYPE = 1
FACEBOOK_REELS_MEDIA_TYPE = 1
FACEBOOK_VIDEO_MEDIA_TYPE = 3
INSTAGRAM_REELS_MEDIA_TYPE = 1
INSTAGRAM_VIDEO_MEDIA_TYPE = 3


def load_stored_access_key() -> str:
    path = DEFAULT_ACCESS_KEY_FILE
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
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


def ensure_access_key():
    if not ACCESS_KEY:
        print(
            f"Error: set PIPPIT_ACCESS_KEY first, or save a local {ACCESS_KEY_STORAGE_KEY}. If you do not have one yet, get it from https://www.pippit.ai.",
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
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
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
        errmsg = resp.get("errmsg", "Unknown error")
        print(f"Error code: {ret}, error message: {errmsg}", file=sys.stderr)
        sys.exit(1)
    return resp.get("data", {})


def load_json_args(request_json: str, request_file: str) -> dict:
    if request_json and request_file:
        print("Error: --request-json and --request-file cannot be used together", file=sys.stderr)
        sys.exit(1)

    raw = ""
    source = ""
    if request_json:
        raw = request_json
        source = "--request-json"
    elif request_file:
        source = request_file
        try:
            with open(request_file, "r", encoding="utf-8") as f:
                raw = f.read()
        except OSError as exc:
            print(f"Error: failed to read {request_file}: {exc}", file=sys.stderr)
            sys.exit(1)

    if not raw:
        return {}

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"Error: {source} is not valid JSON: {exc}", file=sys.stderr)
        sys.exit(1)
    if not isinstance(data, dict):
        print(f"Error: {source} must be a JSON object", file=sys.stderr)
        sys.exit(1)
    return data


def platform_code(platform_name: str) -> int:
    key = (platform_name or "").strip().lower()
    if key not in PLATFORM_MAP:
        print(f"Error: unsupported platform {platform_name}; supported values are tiktok/facebook/instagram", file=sys.stderr)
        sys.exit(1)
    return PLATFORM_MAP[key]


def normalize_statuses(statuses) -> list:
    result = []
    for item in statuses or []:
        key = item.strip().lower()
        if key.isdigit():
            result.append(int(key))
            continue
        if key not in TASK_STATUS_MAP:
            print(f"Error: unknown status {item}", file=sys.stderr)
            sys.exit(1)
        result.append(TASK_STATUS_MAP[key])
    return result


def parse_publish_time(value: str) -> int:
    if not value:
        return 0
    text = value.strip()
    if text.isdigit():
        return int(text)
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        print(f"Error: could not parse publish time {value}: {exc}", file=sys.stderr)
        sys.exit(1)
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return int(dt.timestamp() * 1000)


def build_account_list(platform_name: str, platform_user_ids: list) -> dict:
    return {
        "platform_type": platform_code(platform_name),
        "platform_user_ids": platform_user_ids,
    }


def require_schedule_time_ms(schedule_time: str) -> int:
    if schedule_time:
        return parse_publish_time(schedule_time)
    print("Error: --schedule-time is required, and publishing only supports scheduled tasks", file=sys.stderr)
    sys.exit(1)


def default_list_window_ms() -> tuple[int, int]:
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=30)
    end = now + timedelta(days=31)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


def parse_json_object(name: str, raw: str) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"Error: {name} is not valid JSON: {exc}", file=sys.stderr)
        sys.exit(1)
    if not isinstance(data, dict):
        print(f"Error: {name} must be a JSON object", file=sys.stderr)
        sys.exit(1)
    return data


def merge_dict(target: dict, patch: dict) -> dict:
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            merge_dict(target[key], value)
        else:
            target[key] = value
    return target


def build_platform_params(args, asset_ids: list, schedule_time_ms: int) -> dict:
    platform = platform_code(args.platform)
    title = args.title or ""

    if platform == 1:
        payload = {
            "title": title,
            "urls": list(args.url or []),
            "anchors": [],
            "privacy_level": TIKTOK_PRIVACY_MAP.get((args.privacy_level or "public").lower(), 1),
            "disable_comment": bool(args.disable_comment),
            "disable_duet": bool(args.disable_duet),
            "disable_stitch": bool(args.disable_stitch),
            "is_disclose_video_content": bool(args.disclose_video_content),
            "is_promote_own_brand": bool(args.promote_own_brand),
            "is_promote_other_brand": bool(args.promote_other_brand),
            "asset_id_list": list(asset_ids or []),
            "schedule_time": schedule_time_ms,
            "is_brand_organic": bool(args.is_brand_organic),
            "is_branded_content": bool(args.is_branded_content),
        }
        if args.cover_timestamp_ms is not None:
            payload["video_cover_timestamp_ms"] = args.cover_timestamp_ms
        if args.tiktok_json:
            merge_dict(payload, parse_json_object("--tiktok-json", args.tiktok_json))
        return {"publish_tiktok_param": payload}

    if platform == 311:
        payload = {
            "title": title,
            "media_type": INSTAGRAM_REELS_MEDIA_TYPE if args.instagram_media_type == "reels" else INSTAGRAM_VIDEO_MEDIA_TYPE,
            "collaborators": list(args.collaborators or []),
        }
        if args.audio_name:
            payload["audio_name"] = args.audio_name
        if args.cover_timestamp_ms is not None:
            payload["thumb_offset_ms"] = args.cover_timestamp_ms
        payload["share_to_feed"] = bool(args.share_to_feed)
        if args.instagram_json:
            merge_dict(payload, parse_json_object("--instagram-json", args.instagram_json))
        return {"publish_instagram_param": payload}

    payload = {
        "title": title,
        "media_type": FACEBOOK_REELS_MEDIA_TYPE if args.facebook_media_type == "reels" else FACEBOOK_VIDEO_MEDIA_TYPE,
    }
    if args.description:
        payload["description"] = args.description
    if args.facebook_json:
        merge_dict(payload, parse_json_object("--facebook-json", args.facebook_json))
    return {"publish_facebook_page_param": payload}
