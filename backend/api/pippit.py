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


class ThreadRequest(BaseModel):
    thread_id: str = Field(min_length=1, max_length=200)
    run_id: str = Field(min_length=1, max_length=200)
    after_seq: int = Field(default=0, ge=0)


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
    skill_dir = _ensure_skill()
    args = ["--message", body.message]
    if body.thread_id:
        args += ["--thread-id", body.thread_id]
    if body.asset_ids:
        args += ["--asset-ids", *body.asset_ids]
    result = await _run_skill(skill_dir / "scripts" / "nest" / "submit_run.py", *args, timeout=180)
    task = pippitTaskRecord(run_id=result["run_id"], thread_id=result["thread_id"],
                            message=body.message, web_thread_link=result.get("web_thread_link", ""))
    db.add(task)
    db.commit()
    return result


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
        task.result = result
        task.status = result.get("status", "unknown")
        db.commit()
    return result


@router.get("/tasks")
def listTasks(db: Session = Depends(get_db)):
    return [{"thread_id": task.thread_id, "run_id": task.run_id,
             "message": task.message, "status": task.status,
             "web_thread_link": task.web_thread_link, "project_id": task.project_id,
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
        project = Project(name=task.message[:60] or "Pippit 创作", script_text=task.message, status="ready",
                          analysis_state={"source": "pippit", "thread_id": task.thread_id, "run_id": task.run_id})
        db.add(project)
        db.flush()
        db.add(Outline(project_id=project.id, title=project.name, aspect_ratio=ratio))
        for index, (suffix, url, duration) in enumerate(media, 1):
            video = suffix in (".mp4", ".mov")
            db.add(Shot(project_id=project.id, shot_no=index, title="Pippit 生成素材 " + str(index),
                        prompt=task.message, keyframe_prompt="" if video else task.message, duration=duration,
                        video_url=url if video else "", keyframe_url="" if video else url,
                        video_status="done" if video else "pending"))
        task.project_id = project.id
        db.commit()
        return {"project_id": project.id, "count": len(media)}
