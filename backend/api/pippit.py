import asyncio
import json
import mimetypes
import os
import sys
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

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
    if not (codex_home := Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "pippit-skill" / "secrets.json").is_file() and not os.environ.get("PIPPIT_ACCESS_KEY"):
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
async def submit_run(body: SubmitRequest):
    skill_dir = _ensure_skill()
    args = ["--message", body.message]
    if body.thread_id:
        args += ["--thread-id", body.thread_id]
    if body.asset_ids:
        args += ["--asset-ids", *body.asset_ids]
    return await _run_skill(skill_dir / "scripts" / "nest" / "submit_run.py", *args, timeout=180)


@router.post("/thread")
async def get_thread(body: ThreadRequest):
    skill_dir = _ensure_skill()
    return await _run_skill(
        skill_dir / "scripts" / "nest" / "get_thread.py",
        "--thread-id", body.thread_id,
        "--run-id", body.run_id,
        "--after-seq", str(body.after_seq),
        timeout=90,
    )


