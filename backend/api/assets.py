import os
import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session
from pydantic import BaseModel
from database import get_db
from services import image_service, gpt_service
from config import project_directory

from services.director_design import ensure_project_idle

def idle_project(project_id: int, db: Session = Depends(get_db)):
    ensure_project_idle(project_id, db)

router = APIRouter(prefix="/api", tags=["assets"], dependencies=[Depends(idle_project)])

MAX_UPLOAD_BYTES = 30 * 1024 * 1024


def _is_local_project_image(url: str) -> bool:
    return bool(url and (
        url.startswith("/storage/images/")
        or (url.startswith("/storage/projects/") and "/images/" in url)
    ))


def _image_extension(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"): return "png"
    if data.startswith(b"\xff\xd8\xff"): return "jpg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP": return "webp"
    return None


async def _save_uploaded_image(db: Session, project_id: int, upload: UploadFile, subdir: str, prompt: str) -> dict:
    data = await upload.read(MAX_UPLOAD_BYTES + 1)
    if not data:
        raise HTTPException(400, "请选择一张图片")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "图片不能超过 30 MB")
    extension = _image_extension(data)
    if not extension:
        raise HTTPException(415, "仅支持 PNG、JPG 或 WEBP 图片")

    target_dir = project_directory(project_id) / "images" / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{uuid.uuid4().hex}.{extension}"
    local_url = f"/storage/projects/{project_id}/images/{subdir}/{target.name}"
    try:
        target.write_bytes(data)
        from services.media_host import publish_local_image
        from services.image_service import _store_image_prompt
        from services.media_host import can_inline_video_image
        public_url = publish_local_image(db, local_url)
        inline_ready = can_inline_video_image(local_url)
        _store_image_prompt(db, local_url, prompt, "外部 AI 上传")
        db.commit()
        reference_ready = bool(public_url or inline_ready)
        return {
            "url": local_url,
            "video_reference_ready": reference_ready,
            "message": ("图片已上传并绑定，可用于视频参考。" if reference_ready else
                        "图片已保存，但格式或大小不适合直接传给视频模型；请上传小于 12 MB 的 PNG、JPG 或 WEBP 图片。"),
        }
    except HTTPException:
        db.rollback()
        target.unlink(missing_ok=True)
        raise
    except gpt_service.GPTError as e:
        db.rollback()
        target.unlink(missing_ok=True)
        raise HTTPException(e.status_code, e.message)
    except Exception:
        db.rollback()
        target.unlink(missing_ok=True)
        raise

class PromoteReference(BaseModel):
    url: str


@router.post("/projects/{project_id}/assets/{kind}/{asset_id}/image")
async def upload_asset_image(project_id: int, kind: str, asset_id: int,
                             file: UploadFile = File(...), variant: str = Query("base"),
                             db: Session = Depends(get_db)):
    from models.drama import Character, Scene, Prop
    models = {"character": Character, "scene": Scene, "prop": Prop}
    model = models.get(kind)
    if not model:
        raise HTTPException(400, "不支持的资产类型")
    asset = db.query(model).filter_by(id=asset_id, project_id=project_id).first()
    if not asset:
        raise HTTPException(404, "资产不存在")
    if kind != "character" and variant != "base":
        raise HTTPException(400, "场景与道具只支持主参考图")
    if kind == "character" and variant != "base" and not (
        variant in {"front", "side", "back", "three_quarter", "turnaround", "detail_sheet", "expressions"}
        or (variant.startswith("expression_") and variant.removeprefix("expression_").isdigit())
    ):
        raise HTTPException(400, "不支持的角色参考类型")
    try:
        prompt = image_service.build_asset_prompt(kind, asset, variant)
    except gpt_service.GPTError as e:
        raise HTTPException(e.status_code, e.message)

    subdir = {"character": "characters", "scene": "scenes", "prop": "props"}[kind]
    result = await _save_uploaded_image(db, project_id, file, subdir, prompt)
    if kind == "character":
        if variant == "base":
            old = asset.base_image_url
            asset.base_image_url = result["url"]
            versions = list(asset.extra_images or [])
            if old and old != result["url"] and old not in versions:
                versions.append(old)
            asset.extra_images = (versions + [result["url"]])[-20:]
        else:
            refs = dict(asset.reference_images or {})
            refs[variant] = result["url"]
            asset.reference_images = refs
    elif kind == "scene":
        old = asset.image_url
        asset.image_url = result["url"]
        versions = list(asset.image_versions or [])
        if old and old != result["url"] and old not in versions:
            versions.append(old)
        asset.image_versions = (versions + [result["url"]])[-20:]
    else:
        asset.image_url = result["url"]
    db.commit()
    return {"ok": True, "kind": kind, "asset_id": asset_id, "variant": variant, **result}


@router.post("/projects/{project_id}/shots/{shot_id}/keyframe/upload")
async def upload_shot_keyframe(project_id: int, shot_id: int,
                               file: UploadFile = File(...), db: Session = Depends(get_db)):
    from models.drama import Shot
    shot = db.query(Shot).filter_by(id=shot_id, project_id=project_id).first()
    if not shot:
        raise HTTPException(404, "分镜不存在")
    if shot.video_status == "processing":
        raise HTTPException(409, "视频生成中，暂时不能替换关键帧")
    if not shot.keyframe_prompt:
        raise HTTPException(400, "该分镜还没有关键帧提示词，请先完成剧本分析")
    result = await _save_uploaded_image(db, project_id, file, "keyframes", shot.keyframe_prompt)
    shot.keyframe_url = result["url"]
    db.commit()
    return {"ok": True, "shot_id": shot_id, **result}

@router.put("/projects/{project_id}/{kind}/{asset_id}/reference-active")
def promote_reference(project_id:int,kind:str,asset_id:int,body:PromoteReference,db:Session=Depends(get_db)):
    from models.drama import Character,Scene,Shot
    if db.query(Shot).filter_by(project_id=project_id,video_status='processing').first():
        raise HTTPException(409,'请等待本项目视频生成完成后切换参考版本')
    if kind=='characters':
        asset=db.query(Character).filter_by(id=asset_id,project_id=project_id).first()
        versions=asset.extra_images if asset else []
        field='base_image_url'
    elif kind=='scenes':
        asset=db.query(Scene).filter_by(id=asset_id,project_id=project_id).first()
        versions=asset.image_versions if asset else []
        field='image_url'
    else: raise HTTPException(400,'仅支持角色与场景参考')
    if not asset: raise HTTPException(404,'参考资产不存在')
    if body.url not in (versions or []): raise HTTPException(400,'只能启用当前资产的历史图片')
    setattr(asset,field,body.url);db.commit()
    return {'ok':True,'active_url':body.url}

@router.post("/projects/{project_id}/references/publish")
def publish_project_references(project_id: int, db: Session = Depends(get_db)):
    """将已有角色/场景/关键帧迁移到已配置的公网桶。"""
    from models.drama import Project
    from services.media_host import configured, publish_local_image
    from models.drama import ImageSource
    project=db.get(Project,project_id)
    if not project: raise HTTPException(404,'项目不存在')
    if not configured(): raise HTTPException(400,'请先配置公网图片存储，再迁移旧参考图')
    urls=[]
    for character in project.characters:
        urls += [character.base_image_url,*(character.extra_images or []),*((character.reference_images or {}).values())]
    for scene in project.scenes:
        urls += [scene.image_url,*(scene.image_versions or [])]
    urls += [prop.image_url for prop in project.props]
    urls += [shot.keyframe_url for shot in project.shots]
    published=0
    public_base=os.environ['DRAMAFORGE_MEDIA_PUBLIC_BASE'].rstrip('/')+'/'
    try:
        for url in set(url for url in urls if _is_local_project_image(url)):
            source=db.query(ImageSource).filter_by(local_url=url).first()
            if source and source.remote_url.startswith(public_base): continue
            publish_local_image(db,url);published+=1
        db.commit()
    except gpt_service.GPTError as e:
        db.rollback();raise HTTPException(e.status_code,e.message)
    return {'published':published,'total':len(set(url for url in urls if url))}


@router.post("/projects/{project_id}/characters/{char_id}/generate")
async def gen_character(project_id: int, char_id: int,
                        regenerate: bool = Query(False),
                        model: str | None = Query(None),
                        db: Session = Depends(get_db)):
    from models.drama import Character
    c = db.query(Character).filter_by(id=char_id, project_id=project_id).first()
    if not c:
        raise HTTPException(404, "角色不存在")
    try:
        url = await image_service.generate_character(
            db, project_id, char_id, c.description, regenerate, model=model)
        return {"ok": True, "char_id": char_id, "url": url}
    except gpt_service.GPTError as e:
        raise HTTPException(e.status_code, e.message)


@router.post("/projects/{project_id}/scenes/{scene_id}/generate")
async def gen_scene(project_id: int, scene_id: int,
                   regenerate: bool = Query(False),
                   model: str | None = Query(None),
                   db: Session = Depends(get_db)):
    from models.drama import Scene
    s = db.query(Scene).filter_by(id=scene_id, project_id=project_id).first()
    if not s:
        raise HTTPException(404, "场景不存在")
    try:
        url = await image_service.generate_scene(
            db, project_id, scene_id, s.description, regenerate, model=model)
        return {"ok": True, "scene_id": scene_id, "url": url}
    except gpt_service.GPTError as e:
        raise HTTPException(e.status_code, e.message)


@router.post("/projects/{project_id}/props/{prop_id}/generate")
async def gen_prop(project_id: int, prop_id: int,
                   regenerate: bool = Query(False),
                   model: str | None = Query(None),
                   db: Session = Depends(get_db)):
    from models.drama import Prop
    p = db.query(Prop).filter_by(id=prop_id, project_id=project_id).first()
    if not p:
        raise HTTPException(404, "道具不存在")
    try:
        url = await image_service.generate_prop(
            db, project_id, prop_id, p.description, regenerate, model=model)
        return {"ok": True, "prop_id": prop_id, "url": url}
    except gpt_service.GPTError as e:
        raise HTTPException(e.status_code, e.message)

@router.post("/projects/{project_id}/characters/{char_id}/references/{variant}/generate")
async def gen_reference(project_id: int, char_id: int, variant: str,
                        model: str | None = Query(None), db: Session = Depends(get_db)):
    try:
        url = await image_service.generate_character_reference(db, project_id, char_id, variant, model)
        return {"ok": True, "url": url, "variant": variant}
    except gpt_service.GPTError as e: raise HTTPException(e.status_code, e.message)

@router.post("/projects/{project_id}/shots/{shot_id}/keyframe/generate")
async def gen_keyframe(project_id: int, shot_id: int, model: str | None = Query(None), db: Session = Depends(get_db)):
    try:
        url = await image_service.generate_keyframe(db, project_id, shot_id, model)
        return {"ok": True, "url": url}
    except gpt_service.GPTError as e: raise HTTPException(e.status_code, e.message)


@router.post("/projects/{project_id}/characters/{char_id}/audio")
async def uploadCharacterAudio(project_id: int, char_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    import asyncio, json, math, subprocess
    from models.drama import Character, Project
    from api.batch import FFPROBE
    character = db.query(Character).filter_by(project_id=project_id, id=char_id).first()
    if not character: raise HTTPException(404, "角色不存在")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".mp3", ".wav", ".m4a", ".ogg", ".flac"}: raise HTTPException(422, "支持 MP3/WAV/M4A/OGG/FLAC 音频")
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if not content or len(content) > MAX_UPLOAD_BYTES: raise HTTPException(422, "音频不能为空且不能超过30MB")
    directory = project_directory(project_id) / "audio" / "characters"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (uuid.uuid4().hex + suffix)
    try:
        path.write_bytes(content)
        result = await asyncio.to_thread(subprocess.run, [FFPROBE, "-v", "error", "-show_entries", "format=duration:stream=codec_type", "-of", "json", str(path)], capture_output=True, text=True, timeout=30)
        if result.returncode: raise ValueError("无法解析音频")
        info = json.loads(result.stdout)
        streams = info.get("streams", [])
        duration = float(info["format"]["duration"])
        if not any(stream.get("codec_type") == "audio" for stream in streams) or any(stream.get("codec_type") == "video" for stream in streams) or not math.isfinite(duration) or duration <= 0 or duration > 300:
            raise ValueError("请上传最长300秒的纯音频")
        project = db.get(Project, project_id)
        settings = dict(project.generation_settings or {})
        record = {"url": f"/storage/projects/{project_id}/audio/characters/{path.name}", "duration": round(duration, 2), "name": (file.filename or "角色声音")[:200]}
        settings["characterAudio"] = {**settings.get("characterAudio", {}), str(char_id): record}
        project.generation_settings = settings
        db.commit()
        return {"ok": True, **record}
    except (ValueError, KeyError, subprocess.TimeoutExpired) as error:
        db.rollback(); path.unlink(missing_ok=True)
        raise HTTPException(422, "音频解析失败，请上传有效且最长300秒的纯音频") from error
    except Exception:
        db.rollback(); path.unlink(missing_ok=True)
        raise
