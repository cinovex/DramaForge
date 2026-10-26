"""分析请求立即返回，后台使用独立数据库会话执行；页面轮询进度。"""
import asyncio
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from database import get_db, SessionLocal
from models.drama import Project, Shot, Setting
from services import analyze_service, gpt_service
from services.enrich_service import enrich_project
from services.analysisTasks import analysisPaused, checkAnalysisPause
from services.settings_service import get_stage_config

router = APIRouter(prefix="/api/projects", tags=["analyze"])
_tasks: set[asyncio.Task] = set()

async def _run_analysis(project_id: int, mode: str, model: str | None):
    db = SessionLocal()
    cfg = get_stage_config(db, "script") or {}
    setting = db.query(Setting).filter_by(stage="script").first()
    cfg = {**cfg, "configRevision": setting.updated_at.isoformat() if setting and setting.updated_at else ""}
    if model: cfg = {**cfg, "model": model}
    token = gpt_service.executionConfig.set(cfg)
    try:
        if mode == "enrich": result = await enrich_project(db, project_id, model, already_started=True)
        else:
            result = await analyze_service.analyze_project(db, project_id, model, already_started=True)
            p = db.get(Project, project_id)
            checkAnalysisPause(db, p)
            p.analysis_state = {**(p.analysis_state or {}), "previous_status": "ready", "progress": "故事结构已完成，正在自动补齐角色、场景与逐镜导演设计"}
            p.status = "analyzing"
            db.commit()
            result = await enrich_project(db, project_id, model, already_started=True)
        p = db.get(Project, project_id)
        if p:
            p.analysis_state = {**(p.analysis_state or {}), "status": "done", "progress": "分析完成", "result": result,
                                "finished_at": datetime.utcnow().isoformat()}
            db.commit()
    except analysisPaused:
        db.rollback()
        p = db.get(Project, project_id)
        db.refresh(p)
        p.status = "analysis_paused"
        p.analysis_state = {**(p.analysis_state or {}), "status": "paused", "progress": "已暂停，完成部分已保存；可更换 API 配置后继续剩余任务", "pauseRequested": False}
        db.commit()
    except Exception as error:
        db.rollback()
        p = db.get(Project, project_id)
        if p:
            db.refresh(p)
            state = p.analysis_state or {}
            uncertain = isinstance(error, gpt_service.GPTError) and error.status_code == 504
            units = {key: {**unit, "status": "interrupted" if uncertain else "failed", "error": "请求超时，远端可能已消耗额度；继续将重试未保存项" if uncertain else "本项未完成，可继续重试"} if unit.get("status") == "running" else unit for key, unit in (state.get("units") or {}).items()}
            p.status = "analysis_failed"
            p.analysis_state = {**state, "units": units, "status": "failed", "progress": "分析暂停于未完成项，已保存成果保留",
                                "error": error.message if isinstance(error, gpt_service.GPTError) else "分析失败，现有作品未被修改，请重试",
                                "finished_at": datetime.utcnow().isoformat()}
            db.commit()
    finally:
        gpt_service.executionConfig.reset(token)
        db.close()

def enqueue_analysis(project_id: int, mode: str, model: str | None, db: Session):
    p = db.get(Project, project_id)
    if not p: raise HTTPException(404, "项目不存在")
    if not (p.script_text or "").strip(): raise HTTPException(400, "项目没有剧本")
    if p.status == "analyzing": raise HTTPException(409, "项目正在分析，请等待当前任务完成")
    shots = db.query(Shot).filter_by(project_id=project_id).all()
    previous = p.analysis_state or {}
    structurePending = previous.get("structurePlan") and previous.get("structureNext", 0) < len(previous["structurePlan"])
    if structurePending: mode = "analyze"
    if mode == "enrich" and not shots: raise HTTPException(400, "请先分析剧本")
    if mode == "analyze" and shots and not structurePending: raise HTTPException(409, "已有分镜请使用深化分析，保留现有作品")
    if any(s.video_status == "processing" for s in shots): raise HTTPException(409, "请等待视频生成结束后再分析")
    # 首次分析会自动接续一次 enrich。若 enrich 中途失败，前端下一次提交的 mode
    # 会从 analyze 变为 enrich；只要源剧本指纹未变，就继续复用已完成的检查点。
    cacheKeys = ("staged", "fingerprint", "units", "structurePlan", "structureNext", "structureFingerprint", "counts", "completed", "total")
    cache = {k: previous[k] for k in cacheKeys if k in previous} if previous.get("status") in {"failed", "paused"} else {}
    p.analysis_state = {**cache, "status": "running", "previous_status": p.status, "mode": mode,
                        "progress": f"正在读取剧本（{len(p.script_text):,} 字）", "phase": "reading",
                        "completed": cache.get("completed", 0), "total": cache.get("total", 0), "pauseRequested": False, "started_at": datetime.utcnow().isoformat()}
    p.status = "analyzing"
    db.commit()
    task = asyncio.create_task(_run_analysis(project_id, mode, model))
    _tasks.add(task); task.add_done_callback(_tasks.discard)
    return {"status": "analyzing", "project_id": project_id, "message": "分析任务已提交"}


@router.post("/{project_id}/analysis/pause", status_code=202)
async def pauseAnalysis(project_id: int, db: Session = Depends(get_db)):
    p = db.get(Project, project_id)
    if not p: raise HTTPException(404, "项目不存在")
    if p.status != "analyzing": raise HTTPException(409, "项目当前没有正在运行的分析")
    p.analysis_state = {**(p.analysis_state or {}), "pauseRequested": True}
    db.commit()
    return {"status": "pausing", "message": "当前请求结束并保存后暂停，不再启动下一项"}

@router.post("/{project_id}/analyze", status_code=202)
async def analyze(project_id: int, model: str | None = Query(None), db: Session = Depends(get_db)):
    return enqueue_analysis(project_id, "analyze", model, db)

@router.post("/{project_id}/enrich", status_code=202)
async def enrich(project_id: int, model: str | None = Query(None), db: Session = Depends(get_db)):
    return enqueue_analysis(project_id, "enrich", model, db)
