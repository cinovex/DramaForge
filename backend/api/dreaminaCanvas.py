"""Local website adapter for the official Dreamina Canvas CLI."""
import asyncio
import json
import os
import shutil
import subprocess
import re
import threading
from pathlib import Path
from uuid import UUID
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from database import get_db
from models.drama import Project

router = APIRouter(prefix="/api/dreamina-canvas", tags=["dreamina-canvas"])
authProcess = None
authUrl = ""
authLock = threading.Lock()
authReady = threading.Event()


def readAuthorization(process):
    global authUrl
    for line in process.stdout:
        match = re.search(r"https://jimeng\.jianying\.com/[^\s]+", line)
        if match:
            authUrl = match.group(0)
            authReady.set()
    authReady.set()


def startAuthorization():
    global authProcess, authUrl
    with authLock:
        if authProcess is None or authProcess.poll() is not None:
            authUrl = ""
            authReady.clear()
            authProcess = subprocess.Popen([cliPath(), "auth", "login"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
            threading.Thread(target=readAuthorization, args=(authProcess,), daemon=True).start()
    authReady.wait(15)
    return {"url": authUrl or None, "pending": authProcess.poll() is None}


def cliPath():
    configured = os.environ.get("DREAMINA_CANVAS_CLI")
    candidates = [configured, shutil.which("dreamina-canvas"), str(Path.home() / ".local" / "bin" / ("dreamina-canvas.exe" if os.name == "nt" else "dreamina-canvas"))]
    for path in candidates:
        if path and Path(path).is_file():
            return str(path)
    raise HTTPException(503, detail={"reason": "cli_not_installed", "message": "即梦画布工具尚未安装"})


def runCliSync(args):
    try:
        result = subprocess.run([cliPath(), "--format", "json", "--non-interactive", *args], capture_output=True, timeout=90)
    except subprocess.TimeoutExpired:
        raise HTTPException(504, detail={"reason": "network_timeout", "message": "即梦请求超时；创建操作请保留原编号后重试"})
    except OSError:
        raise HTTPException(503, detail={"reason": "cli_unavailable", "message": "无法启动即梦画布工具"})
    try:
        response = json.loads((result.stdout or result.stderr).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(502, detail={"reason": "invalid_response", "message": "即梦工具未返回有效结果"})
    if not response.get("ok"):
        error = response.get("error") or {}
        reason = error.get("reason") or error.get("code") or "request_failed"
        messages = {"vip_membership_required": "账号已授权，但当前账号不满足即梦画布功能的会员要求。请在即梦官网核对账号权益。", "authentication_required": "请先完成即梦账号授权", "not_logged_in": "请先完成即梦账号授权", "network_timeout": "连接即梦超时，请稍后手动刷新"}
        message = messages.get(reason, "即梦请求未成功，请根据账号权限或服务状态处理后重试")
        status = 403 if error.get("class") == "access_denied" else 401 if error.get("class") in {"authentication", "authentication_required", "auth_required"} else 502
        raise HTTPException(status, detail={"reason": reason, "message": message, "requestId": error.get("requestId"), "retryable": bool(error.get("retryable"))})
    return response


async def runCli(*args):
    return await asyncio.to_thread(runCliSync, list(args))


@router.get("/status")
async def status():
    response = await runCli("auth", "status")
    data = response.get("data") or {}
    return {"installed": True, "loggedIn": bool(data.get("loggedIn")), "version": data.get("version"), "region": data.get("region"), "profile": data.get("profile"), "authPending": authProcess is not None and authProcess.poll() is None}


@router.post("/authorize")
async def authorize():
    state = (await runCli("auth", "status")).get("data", {})
    if state.get("loggedIn"):
        return {"loggedIn": True}
    try:
        return await asyncio.to_thread(startAuthorization)
    except OSError:
        raise HTTPException(503, "无法启动即梦授权，请检查工具安装")


@router.get("/canvases")
async def listCanvases(cursor: str = Query(default="", max_length=4096)):
    args = ["canvas", "ls", "--limit", "30"]
    if cursor:
        args += ["--cursor", cursor]
    return (await runCli(*args)).get("data", {})


class CanvasCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    requestId: UUID


@router.post("/canvases")
async def createCanvas(body: CanvasCreate):
    return (await runCli("canvas", "create", "--project-id", str(body.requestId), "--", body.name)).get("data", {})


@router.get("/canvases/{project_id}/nodes")
async def listNodes(project_id: UUID, offset: int = Query(default=0, ge=0, le=1000)):
    return (await runCli("node", "find", "--project-id", str(project_id), "--limit", "50", "--offset", str(offset))).get("data", {})


class CanvasLink(BaseModel):
    projectId: UUID
    name: str = Field(min_length=1, max_length=512)
    webUrl: str = Field(max_length=2048)


@router.put("/projects/{local_id}/link")
def linkCanvas(local_id: int, body: CanvasLink, db: Session = Depends(get_db)):
    from services.director_design import ensure_project_idle
    ensure_project_idle(local_id, db)
    project = db.get(Project, local_id)
    if not project:
        raise HTTPException(404, "本地项目不存在")
    url = urlparse(body.webUrl)
    if url.scheme != "https" or url.hostname != "jimeng.jianying.com" or url.username or url.password:
        raise HTTPException(400, "画布链接必须来自即梦官网")
    project.generation_settings = {**(project.generation_settings or {}), "dreaminaCanvas": {"projectId": str(body.projectId), "name": body.name, "webUrl": body.webUrl}}
    db.commit()
    return {"ok": True, "canvas": project.generation_settings["dreaminaCanvas"]}
