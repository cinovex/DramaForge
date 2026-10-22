from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from schemas.settings import SettingUpdate
from services import settings_service as svc
from services.api_tester import test_stage

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def list_settings(db: Session = Depends(get_db)):
    return svc.get_all_settings(db)


@router.get("/get")
def get_canvas_settings(db: Session = Depends(get_db)):
    """Compatibility endpoint for the retained Toonflow canvas settings UI."""
    return {"code": 200, "data": svc.get_toonflow_settings(db), "message": "成功"}


@router.put("/save")
def save_canvas_settings(body: dict, db: Session = Depends(get_db)):
    """Keep canvas preferences while routing API/model config to DramaForge's shared store."""
    settings = body.get("settings") if isinstance(body, dict) else None
    if not isinstance(settings, dict):
        raise HTTPException(422, "设置格式不正确")
    try:
        saved = svc.save_toonflow_settings(db, settings)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"code": 200, "data": {"customProviders": saved.get("customProviders", []), "nodeMenu": None}, "message": "设置已保存"}


@router.put("/{stage}")
def update_setting(stage: str, body: SettingUpdate, db: Session = Depends(get_db)):
    r = svc.update_setting(db, stage, body.model_dump())
    return {"stage": r.stage, "provider": r.provider,
            "base_url": r.base_url, "model": r.model, "ok": True}


@router.get("/{stage}/test")
async def test_connection(stage: str, db: Session = Depends(get_db)):
    """测试该环节 API 连通性"""
    result = await test_stage(db, stage)
    return result
