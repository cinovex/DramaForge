"""分析请求立即返回，后台使用独立数据库会话执行；页面轮询进度。"""
import asyncio
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from database import get_db, SessionLocal
from models.drama import Project, Shot
from services import analyze_service, gpt_service
from services.enrich_service import enrich_project

router = APIRouter(prefix="/api/projects", tags=["analyze"])
_tasks: set[asyncio.Task] = set()

async def _run_analysis(project_id: int, mode: str, model: str | None):
    db = SessionLocal()
    try:
        if mode == "enrich": result = await enrich_project(db, project_id, model, already_started=True)
        else:
            result = await analyze_service.analyze_project(db, project_id, model, already_started=True)
            p = db.get(Project, project_id)
            p.analysis_state = {**(p.analysis_state or {}), "previous_status": "ready", "progress": "故事结构已完成，正在自动补齐角色、场景与逐镜导演设计"}
            p.status = "analyzing"
            db.commit()
            result = await enrich_project(db, project_id, model, already_started=True)
        p = db.get(Project, project_id)
        if p:
            p.analysis_state = {**(p.analysis_state or {}), "status": "done", "progress": "分析完成", "result": result,
                                "finished_at": datetime.utcnow().isoformat()}
            db.commit()
    except Exception as error:
        db.rollback()
        p = db.get(Project, project_id)
        if p:
            p.status = "analysis_failed"
            p.analysis_state = {**(p.analysis_state or {}), "status": "failed", "progress": "分析失败",
                                "error": error.message if isinstance(error, gpt_service.GPTError) else "分析失败，现有作品未被修改，请重试",
                                "finished_at": datetime.utcnow().isoformat()}
            db.commit()
    finally: db.close()

def enqueue_analysis(project_id: int, mode: str, model: str | None, db: Session):
    p = db.get(Project, project_id)
    if not p: raise HTTPException(404, "项目不存在")
    if not (p.script_text or "").strip(): raise HTTPException(400, "项目没有剧本")
    if p.status == "analyzing": raise HTTPException(409, "项目正在分析，请等待当前任务完成")
    shots = db.query(Shot).filter_by(project_id=project_id).all()
    if mode == "enrich" and not shots: raise HTTPException(400, "请先分析剧本")
    if mode == "analyze" and shots: raise HTTPException(409, "已有分镜请使用深化分析，保留现有作品")
    if any(s.video_status == "processing" for s in shots): raise HTTPException(409, "请等待视频生成结束后再分析")
    previous = p.analysis_state or {}
    # 首次分析会自动接续一次 enrich。若 enrich 中途失败，前端下一次提交的 mode
    # 会从 analyze 变为 enrich；只要源剧本指纹未变，就继续复用已完成的检查点。
    cache = {k: previous[k] for k in ("staged", "fingerprint") if k in previous} if previous.get("status") == "failed" else {}
    p.analysis_state = {**cache, "status": "running", "previous_status": p.status, "mode": mode,
                        "progress": f"正在读取剧本（{len(p.script_text):,} 字）", "phase": "reading",
                        "completed": 0, "total": 0, "started_at": datetime.utcnow().isoformat()}
    p.status = "analyzing"
    db.commit()
    task = asyncio.create_task(_run_analysis(project_id, mode, model))
    _tasks.add(task); task.add_done_callback(_tasks.discard)
    return {"status": "analyzing", "project_id": project_id, "message": "分析任务已提交"}

@router.post("/{project_id}/analyze", status_code=202)
async def analyze(project_id: int, model: str | None = Query(None), db: Session = Depends(get_db)):
    return enqueue_analysis(project_id, "analyze", model, db)

@router.post("/{project_id}/enrich", status_code=202)
async def enrich(project_id: int, model: str | None = Query(None), db: Session = Depends(get_db)):
    return enqueue_analysis(project_id, "enrich", model, db)
