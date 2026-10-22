from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi import HTTPException
import asyncio
import os
import html as html_lib
from urllib.parse import quote

from database import init_db
from config import STORAGE_DIR, VIDEOS_DIR

app = FastAPI(title="DramaForge API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup():
    init_db()
    from services.settings_service import ensure_default_settings
    ensure_default_settings()
    resume_video_polling()
    # 分析任务不会在重启后重复调用付费接口，恢复为可重试状态。
    from database import SessionLocal
    from models.drama import Project
    with SessionLocal() as db:
        for project in db.query(Project).filter_by(status="analyzing").all():
            state = project.analysis_state or {}
            project.status = state.get("previous_status") or ("ready" if project.outline else "draft")
            project.analysis_state = {**state, "status": "failed", "error": "服务重启中断分析，请重新开始；现有媒体保留"}
        db.commit()


def resume_video_polling():
    """服务重启后，恢复所有处于 processing 状态的视频任务的后台轮询"""
    from database import SessionLocal
    from models.drama import Shot
    from api.shots import _background_generate

    db = SessionLocal()
    try:
        stuck = (
            db.query(Shot)
            .filter(Shot.video_status == "processing", Shot.provider_task_id != "")
            .all()
        )
        for s in stuck:
            asyncio.get_event_loop().create_task(
                _background_generate(s.id, s.provider_task_id,
                    (s.generation_manifest or {}).get('prompt') or s.prompt or "",
                    model=s.provider_model or None)
            )
        # 有状态但从未拿到任务 ID 的僵尸记录 → 重置回待生成
        zombies = (
            db.query(Shot)
            .filter(Shot.video_status == "processing", Shot.provider_task_id == "")
            .all()
        )
        for s in zombies:
            s.video_status = "pending"
        db.commit()
    finally:
        db.close()


@app.get("/health")
def health():
    return {"status": "ok", "service": "DramaForge", "version": "1.0"}


@app.get("/videos-browse")
def videos_browse():
    """成品目录页：递归列出各项目目录和旧版目录中的视频。"""
    files = sorted(
        STORAGE_DIR.rglob("*.mp4"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    rows = []
    for p in files:
        size_mb = p.stat().st_size / 1024 / 1024
        relative = p.relative_to(STORAGE_DIR).as_posix()
        href = "/storage/" + quote(relative, safe="/")
        name = html_lib.escape(relative)
        rows.append(
            f'<li style="margin-bottom:10px">'
            f'<a href="{href}" target="_blank" '
            f'style="color:#a78bfa;text-decoration:none">{name}</a> '
            f'<span style="color:#71717a;font-size:12px">({size_mb:.1f} MB)</span>'
            f"</li>"
        )
    body = "".join(rows) or '<li style="color:#71717a">暂无成品</li>'
    page = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>📦 成品目录 — DramaForge</title></head>
<body style="background:#141416;color:#e4e4e7;font-family:system-ui,'Microsoft YaHei',sans-serif;margin:40px">
<h2 style="color:#a78bfa">📦 成品目录</h2>
<p style="color:#71717a;font-size:13px">点文件名直接播放；新项目素材按项目 ID 分目录保存在 storage\\projects</p>
<ul style="list-style:none;padding:0">{body}</ul>
</body></html>"""
    return HTMLResponse(page)


@app.post("/api/system/open-videos-folder")
def open_videos_folder():
    """在本机文件资源管理器中打开成品文件夹"""
    try:
        os.startfile(str(VIDEOS_DIR))  # Windows: 打开文件夹窗口
    except Exception as e:
        raise HTTPException(500, f"无法打开文件夹: {e}")
    return {"ok": True, "path": str(VIDEOS_DIR)}


# 静态文件（/storage/videos 开启目录浏览，方便“打开位置”查看成品）
app.mount("/storage", StaticFiles(directory=str(STORAGE_DIR)), name="storage")

# 路由
from api import settings as settings_api
from api import projects as projects_api
from api import scripts as scripts_api
from api import analyze as analyze_api
from api import assets as assets_api
from api import shots as shots_api
from api import batch as batch_api
app.include_router(settings_api.router)
app.include_router(projects_api.router)
app.include_router(scripts_api.router)
app.include_router(analyze_api.router)
app.include_router(assets_api.router)
app.include_router(shots_api.router)
app.include_router(batch_api.router)
from api import studio as studio_api
app.include_router(studio_api.router)
from api import pippit as pippit_api
from api import xyq as xyq_api
app.include_router(pippit_api.router)
app.include_router(xyq_api.router)
