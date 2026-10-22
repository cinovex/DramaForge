from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from typing import Literal
from sqlalchemy.orm import Session
from database import get_db
from models.drama import Project, Character, Scene, Shot
from services.director_design import CharacterDesign, SceneDesign, ShotDirection, ensure_project_idle

router = APIRouter(prefix="/api/projects", tags=["studio"])

class Position(BaseModel):
    x: float = Field(ge=-100000, le=100000)
    y: float = Field(ge=-100000, le=100000)
class Viewport(BaseModel):
    x: float = Field(ge=-1000000, le=1000000)
    y: float = Field(ge=-1000000, le=1000000)
    zoom: float = Field(ge=0.1, le=2)
class CanvasState(BaseModel):
    positions: dict[str, Position] = Field(default_factory=dict, max_length=5000)
    viewport: Viewport | None = None
    background_mode: Literal["dots", "lines", "blank"] = "dots"
    version: int = 2

@router.put("/{project_id}/canvas")
def save_canvas(project_id: int, body: CanvasState, db: Session = Depends(get_db)):
    p = db.get(Project, project_id)
    if not p: raise HTTPException(404, "项目不存在")
    p.canvas_state = body.model_dump()
    db.commit()
    return {"ok": True}

@router.put("/{project_id}/characters/{char_id}/design")
def save_character(project_id: int, char_id: int, body: CharacterDesign, db: Session = Depends(get_db)):
    ensure_project_idle(project_id, db)
    c = db.query(Character).filter_by(id=char_id, project_id=project_id).first()
    if not c: raise HTTPException(404, "角色不存在")
    c.design = body.model_dump()
    db.commit()
    return {"ok": True}

@router.put("/{project_id}/scenes/{scene_id}/design")
def save_scene(project_id: int, scene_id: int, body: SceneDesign, db: Session = Depends(get_db)):
    ensure_project_idle(project_id, db)
    scene = db.query(Scene).filter_by(id=scene_id, project_id=project_id).first()
    if not scene: raise HTTPException(404, "场景不存在")
    scene.design = body.model_dump()
    db.commit()
    return {"ok": True}

class ShotDesignUpdate(BaseModel):
    direction: ShotDirection
    keyframe_prompt: str
    prompt: str
    duration: int = Field(ge=4, le=12)

@router.put("/{project_id}/shots/{shot_id}/design")
def save_shot(project_id: int, shot_id: int, body: ShotDesignUpdate, db: Session = Depends(get_db)):
    ensure_project_idle(project_id, db)
    shot = db.query(Shot).filter_by(id=shot_id, project_id=project_id).first()
    if not shot: raise HTTPException(404, "分镜不存在")
    if shot.video_status == "processing": raise HTTPException(409, "视频生成中，暂时不能编辑")
    shot.direction = body.direction.model_dump()
    shot.keyframe_prompt = body.keyframe_prompt
    shot.prompt = body.prompt
    shot.duration = body.duration
    # 保留旧媒体，编辑后的提示词应用于下次生成。
    db.commit()
    return {"ok": True, "message": "已保存，应用于下次生成；现有图片和视频保留"}

from services.generation_design import GenerationOptions, effective_options, compile_generation
from services.gpt_service import GPTError

class ShotReview(BaseModel):
    status: str
    note: str = Field(default="",max_length=1000)

@router.put("/{project_id}/shots/{shot_id}/review")
def review_shot(project_id: int,shot_id: int,body: ShotReview,db: Session = Depends(get_db)):
    if body.status not in ("approved","flagged","needs_review"):
        raise HTTPException(422,"无效审核状态")
    shot=db.query(Shot).filter_by(id=shot_id,project_id=project_id).first()
    if not shot: raise HTTPException(404,"镜头不存在")
    if shot.video_status!="done": raise HTTPException(409,"请等待视频生成完成")
    shot.review_status=body.status
    shot.review_note=body.note.strip()
    db.commit()
    return {"ok":True,"status":shot.review_status,"note":shot.review_note}

@router.put("/{project_id}/generation")
def save_project_generation(project_id: int, body: GenerationOptions, db: Session = Depends(get_db)):
    ensure_project_idle(project_id, db)
    p = db.get(Project, project_id)
    if db.query(Shot).filter_by(project_id=project_id,video_status="processing").first():
        raise HTTPException(409,"视频生成中，请完成后调整全片画幅")
    p.generation_settings = {**(p.generation_settings or {}),**body.model_dump()}
    if p.outline and body.aspect_ratio: p.outline.aspect_ratio=body.aspect_ratio
    db.commit()
    return {"ok":True,"settings":effective_options(p)}

@router.put("/{project_id}/shots/{shot_id}/generation")
def save_shot_generation(project_id: int, shot_id: int, body: GenerationOptions, db: Session = Depends(get_db)):
    ensure_project_idle(project_id, db)
    shot=db.query(Shot).filter_by(id=shot_id,project_id=project_id).first()
    if not shot: raise HTTPException(404,"分镜不存在")
    if shot.video_status=="processing": raise HTTPException(409,"视频生成中，不能修改本次生成参数")
    # 校验引用归属，不接受其他项目的资产。
    from services.generation_design import reference_items
    p=db.get(Project,project_id)
    try: reference_items(db,p,shot,body.model_dump())
    except GPTError as e: raise HTTPException(e.status_code,e.message)
    shot.generation_settings=body.model_dump()
    db.commit()
    return {"ok":True,"settings":effective_options(p,shot)}

@router.get("/{project_id}/shots/{shot_id}/generation-preview")
def generation_preview(project_id: int, shot_id: int, model: str | None = None, db: Session = Depends(get_db)):
    shot=db.query(Shot).filter_by(id=shot_id,project_id=project_id).first()
    if not shot: raise HTTPException(404,"分镜不存在")
    try:
        value=compile_generation(db,db.get(Project,project_id),shot,model,strict=False)
        value['references']=[{k:v for k,v in ref.items() if k!='public_url'} for ref in value['references']]
        value.pop('first_frame',None)
        return value
    except GPTError as e: raise HTTPException(e.status_code,e.message)
