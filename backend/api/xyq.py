"""Domestic Xiaoyunque workflows through the official pippit-tool-cli."""
import asyncio
import json
import mimetypes
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

router = APIRouter(prefix="/api/xyq", tags=["xyq"])
MAX_FILE_BYTES = 500_000_000
_login_process: subprocess.Popen | None = None


def _cli_path() -> Path:
    configured = os.environ.get("PIPPIT_TOOL_CLI")
    if configured and Path(configured).is_file():
        return Path(configured)
    found = shutil.which("pippit-tool-cli")
    if found:
        return Path(found)
    suffix = ".exe" if os.name == "nt" else ""
    cached = Path.home() / ".cache" / "pippit-tool-cli" / "xyq-skill" / f"{os.sys.platform}-{'x64' if os.sys.maxsize > 2**32 else 'x86'}" / "current" / "node_modules" / "@pippit-dev" / "cli" / "bin" / f"pippit-tool-cli{suffix}"
    # CLI cache uses Go's platform names.
    if not cached.is_file() and os.name == "nt":
        cached = Path.home() / ".cache" / "pippit-tool-cli" / "xyq-skill" / "win32-x64" / "current" / "node_modules" / "@pippit-dev" / "cli" / "bin" / f"pippit-tool-cli{suffix}"
    if not cached.is_file():
        raise HTTPException(503, "小云雀 CLI 尚未安装，请检查项目技能安装状态")
    return cached


def _run_sync(args: list[str], timeout: int) -> Any:
    cli = _cli_path()
    try:
        proc = subprocess.run(
            [str(cli), *args], capture_output=True, timeout=timeout,
            cwd=str(cli.parent), env={**os.environ, "PIPPIT_CLI_DISABLE_UPDATE_CHECK": "1"},
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(504, "小云雀请求超时；如果是提交创作，请先核对任务列表后再重试") from exc
    except OSError as exc:
        raise HTTPException(503, "无法启动小云雀 CLI") from exc
    if proc.returncode:
        detail = proc.stderr.decode("utf-8", errors="replace").strip()
        # The CLI may print server diagnostics; never reflect credential-like strings.
        for marker in ("access_token", "access key", "Authorization", "Bearer "):
            if marker.lower() in detail.lower():
                detail = "小云雀 CLI 调用失败，请检查登录状态和接口返回。"
                break
        raise HTTPException(502, detail[-1600:] or "小云雀 CLI 调用失败")
    raw = proc.stdout.decode("utf-8", errors="replace").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(502, "小云雀 CLI 没有返回有效 JSON")


async def _run(args: list[str], timeout: int = 180) -> Any:
    # Windows' default asyncio selector loop cannot spawn subprocesses; delegate to a worker thread.
    return await asyncio.to_thread(_run_sync, args, timeout)


async def _require_login() -> None:
    state = await _run(["status"], timeout=20)
    if not isinstance(state, dict) or state.get("logged_in") is not True:
        raise HTTPException(401, "请先点击“小云雀登录”，完成浏览器授权后再提交")


@router.get("/status")
async def status():
    return await _run(["status"], timeout=20)


@router.get("/models")
async def models(kind: str = "video"):
    if kind not in {"image", "video"}:
        raise HTTPException(400, "模型类型仅支持 image 或 video")
    await _require_login()
    return await _run(["model", "list", "--type", kind], timeout=45)


@router.post("/login")
async def start_login():
    global _login_process
    state = await _run(["status"], timeout=20)
    if isinstance(state, dict) and state.get("logged_in") is True:
        return {"status": "logged_in"}
    if _login_process and _login_process.poll() is None:
        return {"status": "waiting_for_browser"}
    cli = _cli_path()
    try:
        _login_process = subprocess.Popen(
            [str(cli), "login"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL, cwd=str(cli.parent),
            env={**os.environ, "PIPPIT_CLI_DISABLE_UPDATE_CHECK": "1"},
        )
    except OSError as exc:
        raise HTTPException(503, "无法打开小云雀登录流程") from exc
    return {"status": "waiting_for_browser"}


@router.post("/short-drama/submit")
async def short_drama_submit(
    message: str = Form(..., min_length=1, max_length=100000),
    thread_id: str = Form(""),
    script: UploadFile | None = File(None),
):
    await _require_login()
    asset_ids: list[str] = []
    if script:
        suffix = Path(script.filename or "script.txt").suffix.lower()
        if suffix not in {".txt", ".doc", ".docx"}:
            raise HTTPException(415, "短剧剧本仅支持 TXT、DOC 或 DOCX")
        content = await script.read(MAX_FILE_BYTES + 1)
        if not content or len(content) > MAX_FILE_BYTES:
            raise HTTPException(413, "剧本文件为空或超过 500 MB")
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(prefix="dramaforge-xyq-script-", suffix=suffix, delete=False) as temp:
                temp.write(content)
                temp_path = Path(temp.name)
            uploaded = await _run(["short-drama", "+upload-file", "--path", str(temp_path)], timeout=180)
            data = uploaded.get("data", uploaded) if isinstance(uploaded, dict) else {}
            asset_id = data.get("pippit_asset_id") or data.get("asset_id")
            if asset_id:
                asset_ids.append(str(asset_id))
            else:
                raise HTTPException(502, "剧本上传未返回素材 ID")
        finally:
            if temp_path:
                temp_path.unlink(missing_ok=True)
    args = ["short-drama", "+submit-run", "--message", message.strip()]
    if thread_id.strip():
        args += ["--thread-id", thread_id.strip()]
    for asset_id in asset_ids:
        args += ["--asset-ids", asset_id]
    return await _run(args, timeout=180)


@router.post("/short-drama/thread")
async def short_drama_thread(thread_id: str = Form(..., min_length=1, max_length=200), run_id: str = Form("", max_length=200)):
    await _require_login()
    args = ["get-thread", "--thread-id", thread_id.strip()]
    if run_id.strip(): args += ["--run-id", run_id.strip()]
    return await _run(args, timeout=90)


async def _persist_upload(upload: UploadFile, allowed: set[str], prefix: str) -> Path:
    content_type = (upload.content_type or "").lower()
    if content_type not in allowed:
        raise HTTPException(415, f"不支持的参考素材类型：{upload.filename or content_type}")
    content = await upload.read(MAX_FILE_BYTES + 1)
    if not content or len(content) > MAX_FILE_BYTES:
        raise HTTPException(413, "参考素材为空或超过 500 MB")
    suffix = Path(upload.filename or "").suffix.lower() or mimetypes.guess_extension(content_type) or ".bin"
    handle = tempfile.NamedTemporaryFile(prefix=prefix, suffix=suffix, delete=False)
    try:
        handle.write(content)
    finally:
        handle.close()
    return Path(handle.name)


@router.post("/media/generate")
async def media_generate(
    kind: str = Form(...), prompt: str = Form(..., min_length=1, max_length=100000),
    model: str = Form(..., min_length=1, max_length=300), ratio: str = Form(""),
    duration: int | None = Form(None, ge=1, le=600), resolution: str = Form(""),
    reference_files: list[UploadFile] = File(default=[]),
):
    await _require_login()
    if kind not in {"image", "video"}:
        raise HTTPException(400, "创作类型仅支持图片或视频")
    allowed = {"image/png", "image/jpeg", "image/webp"} if kind == "image" else {
        "image/png", "image/jpeg", "image/webp", "video/mp4", "video/quicktime", "video/webm",
        "audio/mpeg", "audio/mp4", "audio/wav", "audio/x-wav", "audio/aac",
    }
    stored: list[Path] = []
    try:
        for upload in reference_files:
            stored.append(await _persist_upload(upload, allowed, "dramaforge-xyq-ref-"))
        args = ["generate-image" if kind == "image" else "generate-video", "--prompt", prompt.strip(), "--model", model.strip()]
        if ratio.strip(): args += ["--ratio", ratio.strip()]
        if kind == "image":
            for path in stored: args += ["--image", str(path)]
        else:
            if duration is not None: args += ["--duration", str(duration)]
            if resolution.strip(): args += ["--resolution", resolution.strip()]
            for path in stored:
                mime = mimetypes.guess_type(path.name)[0] or ""
                flag = "--video" if mime.startswith("video/") else "--audio" if mime.startswith("audio/") else "--image"
                args += [flag, str(path)]
        return await _run(args, timeout=300)
    finally:
        for path in stored: path.unlink(missing_ok=True)


@router.post("/media/query")
async def media_query(thread_id: str = Form(..., min_length=1), run_id: str = Form(..., min_length=1)):
    await _require_login()
    return await _run(["query-result", "--thread-id", thread_id, "--run-id", run_id], timeout=90)


@router.post("/marketing/submit")
async def marketing_submit(
    message: str = Form(..., min_length=1, max_length=100000),
    video_model: str = Form(..., min_length=1, max_length=300),
    ratio: int | None = Form(None), duration: int | None = Form(None, ge=1, le=600),
    show_subtitle: bool | None = Form(None), video_resolution: str = Form(""),
    asset_files: list[UploadFile] = File(default=[]),
):
    await _require_login()
    if ratio is not None and ratio not in {2, 3, 4, 5, 6}:
        raise HTTPException(400, "画幅值必须为 2、3、4、5 或 6")
    cli = _cli_path()
    stored: list[Path] = []
    try:
        asset_ids = []
        for upload in asset_files:
            allowed = {"image/png", "image/jpeg", "image/webp", "video/mp4", "video/quicktime", "video/webm", "audio/mpeg", "audio/mp4", "audio/wav", "audio/x-wav"}
            stored.append(await _persist_upload(upload, allowed, "dramaforge-xyq-marketing-"))
            uploaded = await _run(["marketing", "upload", "--file", str(stored[-1])], timeout=180)
            data = uploaded.get("data", uploaded) if isinstance(uploaded, dict) else {}
            asset_id = data.get("pippit_asset_id")
            if not asset_id:
                raise HTTPException(502, "素材上传没有返回 pippit_asset_id")
            asset_ids.append(asset_id)
        settings: dict[str, Any] = {"video_model": video_model.strip()}
        if ratio is not None: settings["ratio"] = ratio
        if duration is not None:
            settings["duration_start"] = duration
            settings["duration_end"] = duration
        if show_subtitle is not None: settings["show_subtitle"] = show_subtitle
        if video_resolution.strip(): settings["video_resolution"] = video_resolution.strip()
        request_body = {"message": message.strip(), "general_agent_settings": settings}
        if asset_ids: request_body["asset_ids"] = asset_ids
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".json", prefix="dramaforge-xyq-request-", delete=False) as f:
            json.dump(request_body, f, ensure_ascii=False)
            request_path = Path(f.name)
        try:
            return await _run(["marketing", "generate", "--request", str(request_path), "--execute", "--source", "codex"], timeout=180)
        finally:
            request_path.unlink(missing_ok=True)
    finally:
        for path in stored: path.unlink(missing_ok=True)


@router.post("/marketing/query")
async def marketing_query(thread_id: str = Form(..., min_length=1), run_id: str = Form(..., min_length=1)):
    await _require_login()
    return await _run(["marketing", "query", "--thread-id", thread_id, "--run-id", run_id], timeout=90)
