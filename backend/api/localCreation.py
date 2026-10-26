"""Single media creations using configured APIs, independent of Pippit Nest."""
import asyncio
import uuid
from typing import Literal
import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session
from database import get_db
from config import project_directory
from models.drama import Project, Outline, Shot, ImageSource
from services.settings_service import get_stage_config, stageExecutionConfigs
from services.creativePreferences import creativeOptions, resolveCreativeOptions
from services.gpt_service import GPTError

router = APIRouter(prefix="/api/creation", tags=["creation"])
# ACT: one local worker owns submissions; multi-worker hosting needs a unique database claim.
submitLocks = {}


@router.get("/models")
async def modelCatalog(db: Session = Depends(get_db)):
    providers = []
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get("http://127.0.0.1:3001/api/providers/media/list")
            providers = response.json().get("data", []) if response.is_success else []
    except (httpx.HTTPError, ValueError): pass
    items = []
    for kind in ("image", "video"):
        cfg = get_stage_config(db, kind) or {}
        if not cfg.get("api_key") or not cfg.get("model"): continue
        if kind == "video" and not cfg["model"].startswith("agnes-video-"): continue
        provider = next((item for item in providers if item.get("id") == cfg.get("provider")), {})
        models = {item["id"]: item.get("label") or item["id"] for item in provider.get("models", []) if item.get("type") == kind}
        models.setdefault(cfg["model"], cfg["model"])
        for model, label in models.items():
            agnes = model.startswith("agnes-")
            if kind == "video" and not model.startswith("agnes-video-"): continue
            items.append({"id": kind + ":" + model, "kind": kind, "model": model, "label": label,
                          "provider": provider.get("label") or cfg.get("provider"), "providerId": cfg.get("provider"),
                          "ratios": ["9:16", "3:4", "1:1", "4:3", "16:9", "21:9"] if agnes else ["1:1"],
                          "resolutions": (["720P"] if model.endswith("-flash") else ["720P", "1080P", "1K", "2K"]) if kind == "video" else ["2K" if agnes else "1K"],
                          "maxImages": 8 if agnes else 1, "referenceVideo": False})
    return {"items": items}


class creationRequest(BaseModel):
    requestId: uuid.UUID
    modelId: str = Field(min_length=1, max_length=150)
    message: str = Field(min_length=1, max_length=100000)
    preferences: creativeOptions = Field(default_factory=creativeOptions)
    resolution: Literal["720P", "1080P", "1K", "2K"]
    duration: int = Field(default=6, ge=4, le=12)
    projectId: int | None = Field(default=None, gt=0)


def taskSnapshot(project, shot):
    kind = (shot.generation_manifest or {}).get("kind", "video")
    url = shot.keyframe_url if kind == "image" else shot.video_url
    status = "completed" if url else "failed" if shot.video_status == "failed" else "running"
    return {"status": status, "project_id": project.id, "shot_id": shot.id,
            "execution": {"kind": kind, "model": (shot.generation_manifest or {}).get("model"), "provider": (shot.generation_manifest or {}).get("provider"), "resolution": (shot.generation_manifest or {}).get("resolution"), "duration": shot.duration},
            "creativeOptions": (shot.generation_manifest or {}).get("preferences"),
            "messages": [{"id": "user", "role": "user", "content": [{"type": "text", "data": shot.keyframe_prompt if kind == "image" else shot.prompt}]},
                         {"id": "status", "role": "assistant", "content": [{"type": "text", "data": shot.last_error or ("成果已保存到项目" if url else "生成任务正在处理，完成后自动保存到项目") }]}],
            "generated_assets": [{"role": "assistant", "url": url, "mime": "image/png" if kind == "image" else "video/mp4"}] if url else []}


@router.get("/tasks/{projectId}/{shotId}")
def getTask(projectId: int, shotId: int, db: Session = Depends(get_db)):
    shot = db.query(Shot).filter_by(project_id=projectId, id=shotId).first()
    if not shot: raise HTTPException(404, "创作任务不存在")
    return taskSnapshot(shot.project, shot)


@router.post("/generate")
async def generate(payload: str = Form(...), files: list[UploadFile] = File(default=[]), db: Session = Depends(get_db)):
    try: body = creationRequest.model_validate_json(payload)
    except ValidationError: raise HTTPException(422, "生成配置格式不正确")
    if not body.message.strip(): raise HTTPException(422, "请输入生成需求")
    async with submitLocks.setdefault(str(body.requestId), asyncio.Lock()):
        existing = db.query(Shot).filter(Shot.generation_manifest["creationRequestId"].as_string() == str(body.requestId)).first()
        if existing: return taskSnapshot(existing.project, existing)
        option = next((item for item in (await modelCatalog(db))["items"] if item["id"] == body.modelId), None)
        if not option: raise HTTPException(422, "模型配置已变化，请刷新模型列表")
        cfg = get_stage_config(db, option["kind"]) or {}
        if cfg.get("provider") != option["providerId"]: raise HTTPException(409, "供应商配置已变化，请刷新后重新选择")
        if body.resolution not in option["resolutions"] or body.preferences.aspectRatio not in option["ratios"]:
            raise HTTPException(422, "所选模型不支持当前清晰度或比例")
        if len(files) > option["maxImages"]: raise HTTPException(422, "参考图片数量超过当前模型上限")
        from api.assets import _image_extension
        uploads = []
        limit = (12 if option["kind"] == "video" else 30) * 1024 * 1024
        for file in files:
            data = await file.read(limit+1)
            extension = _image_extension(data)
            if not data or len(data) > limit or not extension:
                raise HTTPException(422, "当前模型仅支持参考图片，视频请使用 Pippit；图片需为 PNG/JPG/WEBP，视频参考图最多12MB，图片生成参考图最多30MB")
            uploads.append((data, extension))
        try: preferences = resolveCreativeOptions(body.preferences)
        except ValueError as error: raise HTTPException(422, str(error))
        project = db.get(Project, body.projectId) if body.projectId else None
        if body.projectId:
            from services.director_design import ensure_project_idle
            ensure_project_idle(body.projectId, db)
        if not project:
            project = Project(name=body.message[:60], script_text=body.message, status="ready", generation_settings={"aspect_ratio": preferences["aspectRatio"], "creativePreferences": preferences})
            db.add(project); db.flush()
            db.add(Outline(project_id=project.id, title=project.name, video_style=preferences["stylePrompt"], aspect_ratio=preferences["aspectRatio"]))
        shotNo = max((item.shot_no for item in project.shots if item.episode_no == 1), default=0)+1
        shot = Shot(project_id=project.id, shot_no=shotNo, prompt=body.message, keyframe_prompt=body.message, title=body.message[:60], duration=body.duration,
                    video_status="processing" if option["kind"] == "video" else "pending",
                    generation_manifest={"creationRequestId": str(body.requestId), "kind": option["kind"], "model": option["model"], "provider": option["provider"], "preferences": preferences, "resolution": body.resolution})
        db.add(shot); db.commit()
        prompt = body.message + (f"\n用户选定风格：{preferences['stylePrompt']}" if preferences["stylePrompt"] else "")
        prompt += f"\n输出比例：{preferences['aspectRatio']}。"
        token = stageExecutionConfigs.set({option["kind"]: dict(cfg)})
        try:
            references = []
            for data, extension in uploads:
                directory = project_directory(project.id) / "images" / "references"
                directory.mkdir(parents=True, exist_ok=True)
                filename = uuid.uuid4().hex + "." + extension
                (directory / filename).write_bytes(data)
                url = f"/storage/projects/{project.id}/images/references/{filename}"
                db.add(ImageSource(local_url=url, prompt=body.message, model="用户参考图"))
                references.append({"url": url})
            shot.generation_manifest = {**shot.generation_manifest, "references": references, "prompt": prompt}
            db.commit()
            if option["kind"] == "image":
                from services.image_service import _generate_image
                shot.keyframe_url = await _generate_image(db, prompt, project.id, "creations", model=option["model"], reference_images=[data for data, _ in uploads] or None, aspect_ratio=preferences["aspectRatio"])
            else:
                from services.agnes_video_service import create_video_task
                from api.shots import _background_generate
                generation = {"model": option["model"], "prompt": prompt, "mode": "reference" if references else "text", "resolution": body.resolution, "aspect_ratio": preferences["aspectRatio"], "references": references}
                shot.provider_task_id = await create_video_task(db, prompt, body.duration, model=option["model"], generation=generation)
                shot.provider_model = option["model"]
                db.commit()
                asyncio.create_task(_background_generate(shot.id, shot.provider_task_id, prompt, model=option["model"]))
            db.commit()
        except Exception as error:
            db.rollback(); db.refresh(shot)
            shot.video_status = "failed"
            shot.last_error = (error.message + ("；远端可能仍在运行并产生费用，不会自动重复提交" if error.status_code == 504 else "")) if isinstance(error, GPTError) else "生成或保存未完成，请在项目中查看；提交超时可能已产生费用，不会自动重复生成"
            db.commit()
        finally:
            stageExecutionConfigs.reset(token)
        return taskSnapshot(project, shot)
