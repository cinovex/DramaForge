import asyncio
import json
import mimetypes
import os
import sys
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from database import get_db
from models.drama import pippitTaskRecord, Project, Shot, Outline
from config import STORAGE_DIR
from urllib.parse import urlparse
import hashlib
import math
from services import creativePreferences

router = APIRouter(prefix="/api/pippit", tags=["pippit"])
max_upload_bytes = 200 * 1024 * 1024
allowed_types = {"image/png", "image/jpeg", "image/webp", "video/mp4", "video/quicktime", "video/webm"}


def _skill_dir() -> Path:
    project_skill = Path(__file__).resolve().parents[2] / ".agents" / "skills" / "pippit-skill"
    if (project_skill / "scripts" / "nest" / "submit_run.py").is_file():
        return project_skill
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    return codex_home / "skills" / "pippit-skill"


def _ensure_skill() -> Path:
    skill_dir = _skill_dir()
    if not (skill_dir / "scripts" / "nest" / "submit_run.py").is_file():
        raise HTTPException(503, "Pippit 技能未安装，请先安装 pippit-skill")
    if not (codex_home := Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "pippit-skill" / "secrets.json").is_file() and not (os.environ.get("PIPPIT_ACCESS_KEY") or os.environ.get("PippitAccessKey")):
        raise HTTPException(503, "Pippit API 密钥尚未配置")
    return skill_dir


async def _run_skill(script: Path, *args: str, timeout: int = 150) -> dict[str, Any]:
    try:
        process = await asyncio.to_thread(
            subprocess.run, [sys.executable, str(script), *args],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=str(script.parent), timeout=timeout,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        stdout, stderr = process.stdout, process.stderr
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(504, "Pippit 请求超时，请稍后重试") from exc
    except OSError as exc:
        raise HTTPException(503, "无法启动 Pippit 技能") from exc
    if process.returncode:
        detail = stderr.decode("utf-8", errors="replace").strip()
        if "API error 401" in detail or "API error 403" in detail:
            raise HTTPException(502, "Pippit API 密钥无效或权限不足")
        if "Network error" in detail:
            raise HTTPException(502, "无法连接 Pippit API，请检查网络")
        raise HTTPException(502, detail[-1200:] or "Pippit 请求失败")
    try:
        return json.loads(stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(502, "Pippit 返回内容无法解析") from exc


class SubmitRequest(BaseModel):
    message: str = Field(min_length=1, max_length=100000)
    thread_id: str = Field(default="", max_length=200)
    asset_ids: list[str] = Field(default_factory=list, max_length=32)
    creativeOptions: creativePreferences.creativeOptions | None = None
    creationMode: str = Field(default="", pattern="^(writer|remix|image|video|)$")


class ThreadRequest(BaseModel):
    thread_id: str = Field(min_length=1, max_length=200)
    run_id: str = Field(min_length=1, max_length=200)
    after_seq: int = Field(default=0, ge=0)


class TargetRequest(BaseModel):
    project_id: int = Field(gt=0)
    kind: str = Field(pattern="^(character|scene|prop|video)$")
    target_id: int = Field(gt=0)
    message: str = Field(min_length=1, max_length=100000)


def targetAsset(db, binding):
    from models.drama import Character, Scene, Prop
    model = {"character": Character, "scene": Scene, "prop": Prop, "video": Shot}[binding["kind"]]
    asset = db.query(model).filter_by(id=binding["target_id"], project_id=binding["project_id"]).first()
    if not asset:
        raise HTTPException(404, "生成目标已不存在")
    return asset


targetSubmitLocks = {}


@router.post("/generate-target")
async def generateTarget(body: TargetRequest, db: Session = Depends(get_db)):
    key = (body.project_id, body.kind, body.target_id)
    async with targetSubmitLocks.setdefault(key, asyncio.Lock()):
        for task in db.query(pippitTaskRecord).filter_by(project_id=body.project_id).all():
            binding = (task.result or {}).get("binding", {})
            if binding.get("kind") == body.kind and binding.get("target_id") == body.target_id and not binding.get("bound_url") and task.status not in {"failed", "failure", "error", "canceled", "cancelled", "requires_action", "requires_user_input", "interaction_required"}:
                startTargetPolling(task.thread_id, task.run_id)
                return {"thread_id": task.thread_id, "run_id": task.run_id, "web_thread_link": task.web_thread_link, "resumed": True}
        return await submitTarget(body, db)


async def submitTarget(body: TargetRequest, db: Session):
    from services.director_design import ensure_project_idle
    ensure_project_idle(body.project_id, db)
    binding = body.model_dump(exclude={"message"})
    asset = targetAsset(db, binding)
    if body.kind != "video":
        binding["previous_url"] = asset.base_image_url if body.kind == "character" else asset.image_url
    if body.kind == "video" and asset.video_status == "processing":
        raise HTTPException(409, "当前片段正在生成")
    skillDir = _ensure_skill()
    references = []
    if body.kind == "video":
        from models.drama import Character, Scene
        references = [c.base_image_url for c in db.query(Character).filter_by(project_id=body.project_id).all() if c.name in (asset.character_names or []) and c.base_image_url]
        references += [s.image_url for s in db.query(Scene).filter_by(project_id=body.project_id).all() if s.name == asset.scene_name and s.image_url]
        if asset.keyframe_url:
            references = [asset.keyframe_url]
    assetIds = []
    for url in dict.fromkeys(references):
        if not url.startswith("/storage/"):
            raise HTTPException(400, "请先将参考图保存到本地项目")
        path = (STORAGE_DIR / url.removeprefix("/storage/")).resolve()
        if not path.is_relative_to(STORAGE_DIR.resolve()) or not path.is_file():
            raise HTTPException(400, "参考图文件不存在")
        uploaded = await _run_skill(skillDir / "scripts" / "nest" / "upload_file.py", str(path), timeout=180)
        if not uploaded.get("asset_id"):
            raise HTTPException(502, "Pippit 未返回参考素材编号")
        assetIds.append(str(uploaded["asset_id"]))
    result = await submit_run(SubmitRequest(message=body.message, asset_ids=assetIds), db)
    task = db.query(pippitTaskRecord).filter_by(run_id=result["run_id"]).one()
    task.project_id = body.project_id
    task.result = {"binding": binding}
    if body.kind == "video":
        asset.video_status = "processing"
        asset.provider_model = "pippit"
        asset.provider_task_id = result["run_id"]
        asset.last_error = ""
    db.commit()
    startTargetPolling(task.thread_id, task.run_id)
    return result


targetPolling = {}


def startTargetPolling(threadId, runId):
    if runId not in targetPolling or targetPolling[runId].done():
        targetPolling[runId] = asyncio.create_task(pollTarget(threadId, runId))


async def pollTarget(threadId, runId):
    from database import SessionLocal
    for _ in range(720):
        with SessionLocal() as db:
            try:
                result = await get_thread(ThreadRequest(thread_id=threadId, run_id=runId), db)
                status = str(result.get("status", "")).lower()
                if status in {"completed", "complete", "succeeded", "success", "done", "failed", "failure", "error", "canceled", "cancelled", "requires_action", "requires_user_input", "interaction_required"}:
                    return
            except HTTPException as exc:
                db.rollback()
                task = db.query(pippitTaskRecord).filter_by(run_id=runId).first()
                if task:
                    task.result = {**(task.result or {}), "binding_error": str(exc.detail)}
                    if exc.status_code in {400, 404, 409}:
                        task.status = "failed"
                        binding = (task.result or {}).get("binding", {})
                        if binding.get("kind") == "video":
                            asset = db.query(Shot).filter_by(id=binding["target_id"], project_id=binding["project_id"]).first()
                            if asset and asset.provider_task_id == runId:
                                asset.video_status = "failed"
                                asset.last_error = str(exc.detail)
                    db.commit()
                if exc.status_code in {400, 404, 409}:
                    return
        await asyncio.sleep(5)


async def bindTargetResult(task, result, db):
    binding = (task.result or {}).get("binding")
    if not binding or binding.get("bound_url"):
        return binding
    status = str(result.get("status", "")).lower()
    if status not in {"completed", "complete", "succeeded", "success", "done"}:
        if status in {"failed", "failure", "error", "canceled", "cancelled", "requires_action", "requires_user_input", "interaction_required"} and binding["kind"] == "video":
            asset = targetAsset(db, binding)
            asset.video_status = "failed"
            asset.last_error = "Pippit 任务需要补充信息或未完成，请查看 Pippit 任务回复"
        return binding
    urls = []
    for item in result.get("generated_assets", []):
        if item.get("role") != "assistant":
            continue
        url = item.get("download_url") or item.get("url")
        if not isinstance(url, str):
            continue
        parsed = urlparse(url)
        host = parsed.hostname or ""
        if parsed.scheme != "https" or not any(host == d or host.endswith("." + d) for d in ("pippit.ai", "capcut.com", "tiktokcdn.com", "byteoversea.com")):
            continue
        suffix = Path(parsed.path).suffix.lower()
        mime = str(item.get("mime") or item.get("format") or "").lower()
        mediaType = " ".join(str(item.get(key, "")) for key in ("type", "sub_type", "path")).lower()
        video = mime.startswith("video") or mime in {"mp4", "mov", "webm"} or suffix in {".mp4", ".mov", ".webm"} or "video" in mediaType
        if video == (binding["kind"] == "video"):
            urls.append(url)
    if not urls:
        raise HTTPException(409, "Pippit 未返回所需类型的生成素材，请查看任务回复")
    outputDir = STORAGE_DIR / "projects" / str(binding["project_id"]) / "pippit" / hashlib.sha256(task.run_id.encode()).hexdigest()[:24]
    downloaded = await _run_skill(_ensure_skill() / "scripts" / "nest" / "download_results.py", "--urls", urls[0], "--output-dir", str(outputDir), "--prefix", "result", timeout=660)
    files = downloaded.get("downloaded", [])
    if downloaded.get("errors") or not files:
        raise HTTPException(502, "Pippit 素材保存失败，可刷新重试，不会重新生成")
    path = Path(files[0]).resolve()
    if not path.is_relative_to(outputDir.resolve()) or not path.is_file():
        raise HTTPException(502, "Pippit 返回文件路径无效")
    video = binding["kind"] == "video"
    if path.suffix.lower() not in ({".mp4", ".mov", ".webm"} if video else {".png", ".jpg", ".jpeg", ".webp"}):
        raise HTTPException(502, "Pippit 返回的文件类型不匹配")
    url = "/storage/" + path.relative_to(STORAGE_DIR.resolve()).as_posix()
    asset = targetAsset(db, binding)
    if video:
        if asset.provider_task_id != task.run_id:
            raise HTTPException(409, "该片段已有更新的生成任务，旧结果不覆盖当前片段")
        asset.video_url = url
        asset.video_status = "done"
        asset.last_error = ""
        asset.history = [*(asset.history or []), {"video_url": url, "provider_task_id": task.run_id, "model": "pippit"}]
    else:
        from services.image_service import _store_image_prompt
        from models.drama import ImageSource
        currentUrl = asset.base_image_url if binding["kind"] == "character" else asset.image_url
        if currentUrl != binding.get("previous_url", currentUrl):
            raise HTTPException(409, "该资产已有更新的图片，Pippit 旧任务结果保留在项目文件夹，不覆盖当前图片")
        if binding["kind"] == "character":
            asset.extra_images = list(dict.fromkeys([*(asset.extra_images or []), *([asset.base_image_url] if asset.base_image_url else []), url]))[-20:]
            asset.base_image_url = url
        else:
            if binding["kind"] == "scene":
                asset.image_versions = list(dict.fromkeys([*(asset.image_versions or []), *([asset.image_url] if asset.image_url else []), url]))[-20:]
            asset.image_url = url
        _store_image_prompt(db, url, task.message, "pippit")
        db.query(ImageSource).filter_by(local_url=url).one().remote_url = urls[0]
    return {**binding, "bound_url": url}


@router.get("/status")
async def get_pippit_status():
    """Check API connectivity without returning linked account details or secrets."""
    try:
        skill_dir = _ensure_skill()
        await _run_skill(skill_dir / "scripts" / "publish" / "list_user_platform_account.py", timeout=60)
    except HTTPException as exc:
        return {
            "connected": False,
            "message": exc.detail,
            "capabilities": _capabilities(),
        }
    except Exception:
        return {
            "connected": None,
            "message": "Pippit 状态检查暂时失败；提交前仍会再次确认。",
            "capabilities": _capabilities(),
        }
    return {"connected": True, "message": "Pippit 海外 API 已连接", "capabilities": _capabilities()}


def _capabilities() -> dict[str, Any]:
    return {
        "credit_balance": False,
        "per_step_cost": False,
        "model_catalog": False,
        "model_selection": False,
        "skill_catalog": False,
        "skill_selection": False,
        "reference_images": True,
        "reference_videos": True,
        "generation_status": True,
        "generated_assets": True,
        "model_routing": "Pippit Nest 自动选择",
    }


@router.post("/upload")
async def upload_reference(file: UploadFile = File(...)):
    skill_dir = _ensure_skill()
    content_type = (file.content_type or "").lower()
    if content_type not in allowed_types:
        raise HTTPException(415, "参考素材仅支持 PNG、JPG、WEBP、MP4、MOV 或 WEBM")
    data = await file.read(max_upload_bytes + 1)
    if not data:
        raise HTTPException(400, "请选择一个参考素材")
    if len(data) > max_upload_bytes:
        raise HTTPException(413, "参考素材不能超过 200 MB")
    suffix = mimetypes.guess_extension(content_type) or ".bin"
    if suffix == ".jpe": suffix = ".jpg"
    path = None
    try:
        with tempfile.NamedTemporaryFile(prefix="dramaforge-pippit-", suffix=suffix, delete=False) as temp:
            temp.write(data)
            path = Path(temp.name)
        result = await _run_skill(skill_dir / "scripts" / "nest" / "upload_file.py", str(path), timeout=180)
        return result
    finally:
        if path:
            path.unlink(missing_ok=True)


@router.post("/submit")
async def submit_run(body: SubmitRequest, db: Session = Depends(get_db)):
    if body.creationMode == "remix" and not body.thread_id:
        raise HTTPException(501, "Pippit 官网专用重制转绘尚未接通，不能以通用 Nest 创作代替。本次未提交创作任务。")
    skill_dir = _ensure_skill()
    preferences = None
    message = body.message
    if body.creativeOptions:
        try: preferences = creativePreferences.resolveCreativeOptions(body.creativeOptions)
        except ValueError as error: raise HTTPException(422, str(error))
        choices = f"\n\n【用户在创作面板选择的设置】\n输出比例：{preferences['aspectRatio']}。"
        if preferences["stylePrompt"]: choices += f"\n视觉风格：{preferences['styleName']}。{preferences['stylePrompt']}"
        if body.creationMode == "writer":
            choices += f"\n剧本集数：{preferences['episodes']} 集。"
            if not body.thread_id: choices += "本次仅创作剧本文本，不生成图片或视频；媒体生成待用户后续确认。"
        elif body.creationMode in {"image", "video"}:
            choices += "\n本次用户选择生成" + ("图片。" if body.creationMode == "image" else "视频。")
        message += choices
    args = ["--message", message]
    if body.thread_id:
        args += ["--thread-id", body.thread_id]
    if body.asset_ids:
        args += ["--asset-ids", *body.asset_ids]
    result = await _run_skill(skill_dir / "scripts" / "nest" / "submit_run.py", *args, timeout=180)
    task = pippitTaskRecord(run_id=result["run_id"], thread_id=result["thread_id"],
                            message=body.message, web_thread_link=result.get("web_thread_link", ""),
                            result={"creativeOptions": preferences, "submittedMessage": message, "creationMode": body.creationMode})
    db.add(task)
    db.commit()
    return conversationSnapshot(db, task, result)


@router.post("/thread")
async def get_thread(body: ThreadRequest, db: Session = Depends(get_db)):
    skill_dir = _ensure_skill()
    result = await _run_skill(
        skill_dir / "scripts" / "nest" / "get_thread.py",
        "--thread-id", body.thread_id,
        "--run-id", body.run_id,
        "--after-seq", str(body.after_seq),
        timeout=90,
    )



    task = db.query(pippitTaskRecord).filter_by(run_id=body.run_id).first()
    if task and task.thread_id == body.thread_id and body.after_seq == 0:
        if (task.result or {}).get("binding"):
            lock = importLocks.setdefault(body.run_id, asyncio.Lock())
            async with lock:
                db.refresh(task)
                binding = await bindTargetResult(task, result, db)
                task.result = {**result, "binding": binding}
                task.status = result.get("status", "unknown")
                db.commit()
        else:
            binding = None
            task.result = {**{key: value for key, value in (task.result or {}).items() if key in {"creativeOptions", "submittedMessage", "creationMode"}}, **result}
            task.status = result.get("status", "unknown")
            db.commit()
        if binding:
            result["binding"] = binding
    return conversationSnapshot(db, task, result) if task and task.thread_id == body.thread_id and body.after_seq == 0 else result


def conversationSnapshot(db, task, snapshot=None):
    result = {**(task.result or {}), **(snapshot or {})}
    result.setdefault("status", task.status)
    messages = []
    seen = set()
    for item in db.query(pippitTaskRecord).filter_by(thread_id=task.thread_id).filter(pippitTaskRecord.id <= task.id).order_by(pippitTaskRecord.id).all():
        current = result if item.id == task.id else (item.result or {})
        entries = current.get("messages") or []
        hasUserMessage = any(entry.get("role") == "user" and any(isinstance(part, dict) and part.get("data") in (item.message, (item.result or {}).get("submittedMessage", item.message)) for part in entry.get("content", []) or []) for entry in entries if isinstance(entry, dict))
        if not hasUserMessage:
            entries = [{"id": f"local-{item.run_id}", "role": "user", "content": [{"type": "text", "data": item.message}]}, *entries]
        for entry in entries:
            if not isinstance(entry, dict): continue
            key = hashlib.sha256(json.dumps(entry, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            if key not in seen:
                messages.append({**entry, "displayId": key})
                seen.add(key)
    result["conversation_messages"] = messages
    return result


@router.get("/tasks/{runId}")
def savedTask(runId: str, db: Session = Depends(get_db)):
    task = db.query(pippitTaskRecord).filter_by(run_id=runId).first()
    if not task: raise HTTPException(404, "会话记录不存在")
    return conversationSnapshot(db, task)


@router.get("/creative-options")
def creativeOptionCatalog():
    return {"styles": creativePreferences.stylePresets, "source": "local"}


@router.get("/tasks")
def listTasks(db: Session = Depends(get_db)):
    return [{"thread_id": task.thread_id, "run_id": task.run_id,
             "message": task.message, "status": task.status,
             "web_thread_link": task.web_thread_link, "project_id": task.project_id,
             "creativeOptions": (task.result or {}).get("creativeOptions"),
             "created_at": task.created_at.isoformat()} for task in
            db.query(pippitTaskRecord).order_by(pippitTaskRecord.id.desc()).limit(100).all()]


importLocks = {}


@router.post("/import")
async def importResults(body: ThreadRequest, db: Session = Depends(get_db)):
    # ACT: One local process owns imports; a multi-worker deployment needs a database claim.
    lock = importLocks.setdefault(body.run_id, asyncio.Lock())
    if lock.locked():
        raise HTTPException(409, "此任务正在保存，请稍后刷新资产库")
    async with lock:
        task = db.query(pippitTaskRecord).filter_by(run_id=body.run_id, thread_id=body.thread_id).first()
        if not task:
            raise HTTPException(404, "任务尚未保存，请先在本网站提交任务")
        if task.project_id and db.get(Project, task.project_id):
            return {"project_id": task.project_id, "already_imported": True}
        result = await get_thread(body, db)
        urls = []
        ratio = ""
        for asset in result.get("generated_assets", []):
            if asset.get("role") != "assistant":
                continue
            width, height = asset.get("width"), asset.get("height")
            if isinstance(width, int) and isinstance(height, int) and width > 0 and height > 0:
                divisor = math.gcd(width, height)
                ratio = str(width // divisor) + ":" + str(height // divisor)
            url = asset.get("download_url") or asset.get("url")
            if not isinstance(url, str):
                continue
            parsed = urlparse(url)
            host = parsed.hostname or ""
            if parsed.scheme == "https" and any(host == domain or host.endswith("." + domain)
                    for domain in ("pippit.ai", "capcut.com", "tiktokcdn.com", "byteoversea.com")):
                if url not in urls:
                    urls.append(url)
        if not urls:
            raise HTTPException(409, "该任务没有可保存的生成素材，请查看实际回复（可能需要补充信息或积分）")
        folderName = hashlib.sha256(body.run_id.encode()).hexdigest()[:24]
        outputDir = STORAGE_DIR / "pippit" / folderName
        skillDir = _ensure_skill()
        downloaded = await _run_skill(skillDir / "scripts" / "nest" / "download_results.py",
            "--urls", *urls, "--output-dir", str(outputDir), "--prefix", "result", timeout=660)
        if downloaded.get("errors") or not downloaded.get("downloaded"):
            raise HTTPException(502, "素材下载未完成，请重试；原任务不会重新生成")
        media = []
        for filename in downloaded["downloaded"]:
            filePath = Path(filename).resolve()
            if not filePath.is_relative_to(outputDir.resolve()):
                raise HTTPException(502, "生成文件路径不正确")
            suffix = filePath.suffix.lower()
            if suffix not in (".mp4", ".mov", ".png", ".jpg", ".jpeg", ".webp", ".gif"):
                raise HTTPException(502, "返回了暂不支持的素材格式")
            duration = 0
            if suffix in (".mp4", ".mov"):
                from api.batch import _media_info
                duration, _ = await asyncio.to_thread(_media_info, filePath)
            media.append((suffix, "/storage/" + filePath.relative_to(STORAGE_DIR.resolve()).as_posix(), duration))
        preferences = (task.result or {}).get("creativeOptions") or {}
        project = Project(name=task.message[:60] or "Pippit 创作", script_text=task.message, status="ready",
                          generation_settings={"aspect_ratio": preferences.get("aspectRatio") or ratio or "9:16", "creativePreferences": preferences},
                          analysis_state={"source": "pippit", "thread_id": task.thread_id, "run_id": task.run_id})
        db.add(project)
        db.flush()
        db.add(Outline(project_id=project.id, title=project.name, aspect_ratio=preferences.get("aspectRatio") or ratio or "9:16", video_style=preferences.get("stylePrompt", "")))
        for index, (suffix, url, duration) in enumerate(media, 1):
            video = suffix in (".mp4", ".mov")
            db.add(Shot(project_id=project.id, shot_no=index, title="Pippit 生成素材 " + str(index),
                        prompt=task.message, keyframe_prompt="" if video else task.message, duration=duration,
                        video_url=url if video else "", keyframe_url="" if video else url,
                        video_status="done" if video else "pending"))
        task.project_id = project.id
        db.commit()
        return {"project_id": project.id, "count": len(media)}
