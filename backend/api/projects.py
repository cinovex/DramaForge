from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Query
from sqlalchemy.orm import Session
from database import get_db
from models.drama import Project, Shot, ImageSource
from typing import Literal
from pydantic import BaseModel
from services.generation_design import Ratio, effective_options
import os, uuid, json, shutil, re
from pathlib import Path

router = APIRouter(prefix="/api/projects", tags=["projects"])
from config import (SCRIPTS_DIR, IMAGES_DIR, VIDEOS_DIR, STORAGE_DIR,
                    PROJECTS_DIR, project_directory, ensure_project_directory)


class ProjectCreate(BaseModel):
    name: str
    script_text: str = ""
    aspect_ratio: Ratio = "9:16"
    project_type: Literal["drama", "canvas"] = "drama"


@router.get("")
def list_projects(db: Session = Depends(get_db)):
    return [{**{column.name: getattr(project, column.name) for column in Project.__table__.columns},
             "workspace_directory": str(project_directory(project.id)),
             "project_type": (project.generation_settings or {}).get("project_type", "drama")}
            for project in db.query(Project).order_by(Project.created_at.desc()).all()]


@router.get("/{project_id}")
def get_project(project_id: int, db: Session = Depends(get_db)):
    p = db.query(Project).get(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    # 附带 outline / characters / scenes / shots
    from models.drama import Outline, Character, Scene, Prop, Shot
    result = {
        "id": p.id, "name": p.name, "status": p.status,
        "project_type": (p.generation_settings or {}).get("project_type", "drama"),
        "workspace_directory": str(ensure_project_directory(p.id)),
        "script_text": p.script_text, "generation_settings": effective_options(p),
        "planned_duration": sum(sh.duration or 0 for sh in p.shots),
        "canvas_state": p.canvas_state or {}, "analysis_state": {k: v for k, v in (p.analysis_state or {}).items() if k not in ("staged", "fingerprint")},
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "outline": {
            "title": p.outline.title, "synopsis": p.outline.synopsis,
            "video_style": p.outline.video_style, "aspect_ratio": p.outline.aspect_ratio,
            "story_type": p.outline.story_type, "target_audience": p.outline.target_audience, "raw_data": p.outline.raw_data,
        } if p.outline else None,
        "characters": [
            {"id": c.id, "name": c.name, "description": c.description,
             "base_image_url": c.base_image_url, "extra_images": c.extra_images,
             "design": c.design or {}, "reference_images": c.reference_images or {}}
            for c in p.characters
        ],
        "scenes": [
            {"id": s.id, "name": s.name, "description": s.description, "image_url": s.image_url, "image_versions": s.image_versions or [], "design": s.design or {}}
            for s in p.scenes
        ],
        "props": [
            {"id": pr.id, "name": pr.name, "description": pr.description, "image_url": pr.image_url}
            for pr in p.props
        ],
        "shots": [
            {"id": sh.id, "episode_no": sh.episode_no, "shot_no": sh.shot_no,
             "title": sh.title, "duration": sh.duration, "scene_name": sh.scene_name,
             "character_names": sh.character_names, "prompt": sh.prompt,
             "generation_settings": sh.generation_settings or {}, "effective_generation": effective_options(p,sh),
             "direction": sh.direction or {}, "keyframe_prompt": sh.keyframe_prompt or "",
             "keyframe_url": sh.keyframe_url, "video_url": sh.video_url, "last_error": sh.last_error,
             "video_status": sh.video_status,
             "generation_manifest": sh.generation_manifest or {},
             "review_status": sh.review_status or "unreviewed", "review_note": sh.review_note or "",
             "started_at": sh.started_at.isoformat() if sh.started_at else None,
             "finished_at": sh.finished_at.isoformat() if sh.finished_at else None}
            for sh in p.shots
        ],
    }
    return result


@router.get("/{project_id}/media-prompt")
def get_media_prompt(project_id: int, media_url: str = Query(...), db: Session = Depends(get_db)):
    """Return a saved image-generation prompt only for media owned by this project."""
    from models.drama import ImageSource
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")

    owned_urls = set()
    for character in project.characters:
        owned_urls.update(url for url in [character.base_image_url, *(character.extra_images or []), *((character.reference_images or {}).values())] if url)
    for scene in project.scenes:
        owned_urls.update(url for url in [scene.image_url, *(scene.image_versions or [])] if url)
    owned_urls.update(prop.image_url for prop in project.props if prop.image_url)
    owned_urls.update(shot.keyframe_url for shot in project.shots if shot.keyframe_url)
    if media_url not in owned_urls:
        raise HTTPException(404, "图片不属于此项目")

    source = db.query(ImageSource).filter_by(local_url=media_url).first()
    if source and source.prompt:
        return {"available": True, "prompt": source.prompt, "model": source.model or "",
                "reconstructed": False, "message": ""}

    prompt = _reconstruct_legacy_image_prompt(project, media_url, db)
    if prompt:
        return {
            "available": True,
            "prompt": prompt,
            "model": source.model if source else "",
            "reconstructed": True,
            "message": "历史调用没有保存提示词；以下文本根据当前资产设定重建，可能与当时提交内容存在差异。",
        }
    return {
        "available": False,
        "prompt": "",
        "model": "",
        "reconstructed": False,
        "message": "这张图片没有可还原的项目提示词，可能是外部导入素材。",
    }


@router.get("/{project_id}/asset-image-prompt")
def get_asset_image_prompt(project_id: int, kind: str = Query(...), asset_id: int = Query(..., gt=0),
                           variant: str = Query("base"), db: Session = Depends(get_db)):
    """Show the exact external-image prompt for an analyzed project asset."""
    from models.drama import Character, Scene, Prop
    from services.image_service import build_asset_prompt
    models = {"character": Character, "scene": Scene, "prop": Prop}
    model = models.get(kind)
    if not model:
        raise HTTPException(400, "不支持的资产类型")
    asset = db.query(model).filter_by(id=asset_id, project_id=project_id).first()
    if not asset:
        raise HTTPException(404, "资产不存在")
    from services.gpt_service import GPTError
    try:
        prompt = build_asset_prompt(kind, asset, variant)
    except GPTError as exc:
        raise HTTPException(exc.status_code, exc.message)
    return {"available": bool(prompt), "prompt": prompt, "model": "", "reconstructed": False, "message": ""}


def _reconstruct_legacy_image_prompt(project, media_url: str, db: Session) -> str:
    """Rebuild a useful prompt for old assets created before prompt history was stored."""
    for character in project.characters:
        design = character.design or {}
        variant = next((name for name, url in (character.reference_images or {}).items()
                        if url == media_url), None)
        if variant:
            prompt = ""
            if variant in ("front", "side", "back", "three_quarter"):
                prompt = (design.get("views") or {}).get(variant, "")
            elif variant == "turnaround":
                prompt = design.get("turnaround_prompt", "")
            elif variant == "expressions":
                prompt = design.get("expression_sheet_prompt", "")
            elif variant.startswith("expression_"):
                try:
                    expression = (design.get("expressions") or [])[int(variant.split("_")[1])]
                    prompt = expression.get("prompt", "") + "。避免：" + expression.get("negative_prompt", "")
                except (ValueError, IndexError, KeyError, TypeError):
                    prompt = ""
            if prompt:
                return (prompt + f"\n角色身份锁定：{character.description}。{design.get('identity', '')}。"
                        f"服装：{design.get('wardrobe', '')}。避免：{design.get('negative_prompt', '')}。"
                        "同一人物，保持五官比例、发型、服装一致，不添加水印。")

        if media_url == character.base_image_url or media_url in (character.extra_images or []):
            prompt = (design.get("views") or {}).get("front") or (
                f"Cinematic character reference for '{character.name}': {character.description}. "
                "Full body, front view, neutral pose, plain dark background, "
                "soft even studio lighting, photorealistic, high detail."
            )
            return prompt + "\n这是全剧固定身份主参考：单人正面全身站姿，眼睛与面部清楚可见；眉眼、嘴角与下颌自然放松，保持中性表情。柔和均匀棚拍光，干净简洁的纯色背景，服装和发型完整可辨。不要动作瞬间、夸张情绪、剧情场景、其他人物、拼图、文字或水印。"

    for scene in project.scenes:
        if media_url == scene.image_url or media_url in (scene.image_versions or []):
            prompt = (scene.design or {}).get("reference_prompt") or (
                f"Cinematic establishing shot of '{scene.name}': {scene.description}. "
                "Wide angle, no characters, atmospheric lighting, photorealistic environment, high detail."
            )
            return prompt + "\n这是全剧固定场景主参考：独立空间定景图，无人物、无临时表演；入口、出口、主要道具位置、活动轴线、光源方向和材质清楚可辨，供后续镜头保持空间布局一致。不要拼图、文字或水印。"

    for prop in project.props:
        if media_url == prop.image_url:
            return (f"Product/prop reference for '{prop.name}': {prop.description}. "
                    "Centered on neutral dark background, studio lighting, photorealistic, high detail.")

    for shot in project.shots:
        if media_url != shot.keyframe_url:
            continue
        from services.director_design import direction_prompt
        from services.generation_design import effective_options, format_prompt, reference_items
        characters = [character for character in project.characters
                      if character.name in (shot.character_names or [])]
        scene = next((item for item in project.scenes if item.name == shot.scene_name), None)
        identities = "\n".join(
            f"{c.name}：{c.description}；{(c.design or {}).get('identity', '')}；{(c.design or {}).get('wardrobe', '')}"
            for c in characters
        )
        prompt = (f"生成单一分镜开场关键帧，不是拼图、不是多格漫画。\n{shot.keyframe_prompt}\n"
                  f"{direction_prompt(shot.direction, still=True)}\n人物设定：{identities}\n"
                  f"场景：{scene.description if scene else shot.scene_name}\n"
                  f"全片视觉：{project.outline.video_style if project.outline else ''}\n"
                  "保持人物面容和服饰一致，无字幕、文字、水印。")
        options = effective_options(project, shot)
        prompt = format_prompt(prompt, options["aspect_ratio"])
        try:
            bound = reference_items(db, project, shot, options)
            roles = [f"参考图{index} = {item['name']}（{item['kind']}），保持相应外貌、服装、空间或道具一致"
                     for index, item in enumerate((r for r in bound if r.get("url")), start=1)]
        except Exception:
            roles = []
        return prompt + ("\n" + "\n".join(roles) if roles else "")
    return ""


@router.post("")
def create_project(body: ProjectCreate, db: Session = Depends(get_db)):
    p = Project(name=body.name, script_text=body.script_text, status="draft", generation_settings={"aspect_ratio":body.aspect_ratio,"resolution":"720P","project_type":body.project_type})
    db.add(p)
    db.commit()
    db.refresh(p)
    ensure_project_directory(p.id)
    return {"id": p.id, "name": p.name, "status": p.status}


@router.post("/upload/{project_id}")
async def upload_script(project_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    p = db.query(Project).get(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")

    original_name = (file.filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    filename = f"{uuid.uuid4().hex}_{original_name}"
    target_dir = project_directory(project_id) / "scripts"
    target_dir.mkdir(parents=True, exist_ok=True)
    filepath = target_dir / filename
    content = await file.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(413, "剧本文件不能超过 10 MB")

    # 支持 txt
    if original_name.lower().endswith(".txt"):
        text = content.decode("utf-8", errors="ignore")
    # 支持 docx
    elif original_name.lower().endswith(".docx"):
        try:
            import docx
            from io import BytesIO
            doc = docx.Document(BytesIO(content))
            text = "\n".join([para.text for para in doc.paragraphs])
        except ImportError:
            raise HTTPException(500, "未安装 python-docx，请 pip install python-docx")
        except Exception:
            raise HTTPException(400, "无法读取 docx 文件，请检查文件是否损坏")
    else:
        raise HTTPException(400, f"不支持的文件格式: {file.filename}")

    if len(text) > 100000:
        raise HTTPException(400, "剧本不能超过10万字")
    if not text.strip():
        raise HTTPException(400, "剧本内容为空")

    with open(filepath, "wb") as f:
        f.write(content)

    p.script_text = text
    p.script_file = str(filepath)
    db.commit()
    return {"project_id": project_id, "chars": len(text), "file": filename}


def _project_media_urls(project: Project) -> set[str]:
    urls: set[str] = set()
    def add(value):
        if isinstance(value, str) and value.startswith("/storage/"):
            urls.add(value.split("?", 1)[0])
    for character in project.characters:
        add(character.base_image_url)
        for url in character.extra_images or []: add(url)
        for url in (character.reference_images or {}).values(): add(url)
    for scene in project.scenes:
        add(scene.image_url)
        for url in scene.image_versions or []: add(url)
    for prop in project.props:
        add(prop.image_url)
    for shot in project.shots:
        add(shot.keyframe_url); add(shot.video_url)
        for item in shot.history or []:
            if not isinstance(item, dict): continue
            add(item.get("video_url"))
            manifest = item.get("manifest") or {}
            add(manifest.get("first_frame"))
            for reference in manifest.get("references") or []:
                if isinstance(reference, dict): add(reference.get("url"))
        manifest = shot.generation_manifest or {}
        add(manifest.get("first_frame"))
        for reference in manifest.get("references") or []:
            if isinstance(reference, dict): add(reference.get("url"))
    return urls


def _safe_storage_file(url: str, project_id: int) -> Path | None:
    if not url.startswith("/storage/"):
        return None
    relative = url.removeprefix("/storage/").split("?", 1)[0]
    candidate = (STORAGE_DIR / relative).resolve()
    roots = (project_directory(project_id).resolve(), SCRIPTS_DIR.resolve(),
             IMAGES_DIR.resolve(), VIDEOS_DIR.resolve())
    if not candidate.is_relative_to(STORAGE_DIR.resolve()):
        return None
    if not any(candidate.is_relative_to(root) for root in roots):
        return None
    return candidate


def _safe_script_file(value: str, project_id: int) -> Path | None:
    if not value:
        return None
    candidate = Path(value).resolve()
    roots = (project_directory(project_id).resolve(), SCRIPTS_DIR.resolve())
    if not candidate.is_relative_to(STORAGE_DIR.resolve()):
        return None
    if not any(candidate.is_relative_to(root) for root in roots):
        return None
    return candidate


def _remove_empty_parents(path: Path, stop: Path) -> None:
    stop = stop.resolve()
    parent = path.parent
    while parent != stop and parent.is_relative_to(stop):
        try: parent.rmdir()
        except OSError: break
        parent = parent.parent


@router.post("/{project_id}/open-folder")
def open_project_folder(project_id: int, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    if project.status in ("analyzing", "producing") or db.query(Shot).filter_by(
        project_id=project_id, video_status="processing"
    ).first():
        raise HTTPException(409, "项目任务正在运行，请完成后再整理素材文件夹")
    from services.project_storage import organize_project_files
    result = organize_project_files(db, project)
    folder = ensure_project_directory(project_id)
    try:
        os.startfile(str(folder))
    except Exception as e:
        raise HTTPException(500, f"无法打开项目文件夹: {e}")
    return {"ok": True, "path": str(folder), **result}


@router.delete("/{project_id}")
def delete_project(project_id: int, db: Session = Depends(get_db)):
    p = db.query(Project).get(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    if p.status in ("analyzing", "producing") or db.query(Shot).filter_by(project_id=project_id, video_status="processing").first():
        raise HTTPException(409, "请等待当前任务完成后再删除项目")

    project_urls = _project_media_urls(p)
    project_image_prefix = f"/storage/projects/{project_id}/images/"
    project_image_rows = db.query(ImageSource).filter(
        ImageSource.local_url.like(project_image_prefix + "%")
    ).all()
    project_urls.update(
        row.local_url for row in project_image_rows
        if row.local_url and row.local_url.startswith(project_image_prefix)
    )
    other_projects = db.query(Project).filter(Project.id != project_id).all()
    other_urls = set().union(*(_project_media_urls(other) for other in other_projects)) if other_projects else set()
    removable_urls = project_urls - other_urls

    project_script = _safe_script_file(p.script_file or "", project_id)
    other_scripts = set()
    for other in other_projects:
        if not other.script_file: continue
        try:
            candidate = Path(other.script_file).resolve()
            if candidate.is_relative_to(STORAGE_DIR.resolve()) and (
                candidate.is_relative_to(SCRIPTS_DIR.resolve()) or candidate.is_relative_to(PROJECTS_DIR.resolve())
            ):
                other_scripts.add(candidate)
        except (OSError, ValueError):
            pass
    image_rows = db.query(ImageSource).filter(ImageSource.local_url.in_(removable_urls)).all() if removable_urls else []
    other_image_rows = db.query(ImageSource).filter(ImageSource.local_url.in_(other_urls)).all() if other_urls else []
    shared_remote_urls = {row.remote_url for row in other_image_rows if row.remote_url}
    remote_images = [row.remote_url for row in image_rows if row.remote_url and row.remote_url not in shared_remote_urls]

    legacy_files = {
        path for url in removable_urls
        if (path := _safe_storage_file(url, project_id)) is not None
        and path != project_directory(project_id).resolve()
    }
    if project_script and project_script not in other_scripts:
        legacy_files.add(project_script)

    # Old exports were written into the shared videos folder; their filename embeds this project ID.
    legacy_exports = []
    if VIDEOS_DIR.exists():
        pattern = re.compile(rf"^export_ep(?:all|\d+)_{project_id}_[a-f0-9]+\.mp4$", re.IGNORECASE)
        for path in VIDEOS_DIR.iterdir():
            if path.is_file() and pattern.fullmatch(path.name): legacy_exports.append(path.resolve())
            elif path.is_dir() and re.fullmatch(rf"export_parts_{project_id}_[a-f0-9]+", path.name, re.IGNORECASE):
                legacy_exports.append(path.resolve())

    root = project_directory(project_id).resolve()
    if root.parent != PROJECTS_DIR.resolve() or root == STORAGE_DIR.resolve():
        raise HTTPException(500, "项目文件夹路径无效，已取消删除")
    shared_project_files = {
        path for url in project_urls & other_urls
        if (path := _safe_storage_file(url, project_id)) is not None
        and path.is_relative_to(root)
    }
    if project_script and project_script in other_scripts and project_script.is_relative_to(root):
        shared_project_files.add(project_script)
    quarantine = None
    if root.exists() and not shared_project_files:
        quarantine = PROJECTS_DIR / f".deleting_{project_id}_{uuid.uuid4().hex}"
        root.rename(quarantine)

    try:
        db.delete(p)
        for row in image_rows:
            db.delete(row)
        db.commit()
    except Exception:
        db.rollback()
        if quarantine and quarantine.exists(): quarantine.rename(root)
        raise

    deleted_files = 0
    warnings = []
    if quarantine and quarantine.exists():
        try:
            deleted_files += sum(1 for path in quarantine.rglob("*") if path.is_file())
            shutil.rmtree(quarantine)
        except OSError as exc:
            warnings.append(f"项目目录未能完全清理：{exc}")
    elif root.exists():
        for path in sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
            if path.is_file() and path.resolve() not in shared_project_files:
                try: path.unlink(); deleted_files += 1
                except OSError as exc: warnings.append(f"文件未能删除：{path.name}")
            elif path.is_dir():
                try: path.rmdir()
                except OSError: pass

    for path in legacy_files | set(legacy_exports):
        try:
            if path.is_dir():
                deleted_files += sum(1 for item in path.rglob("*") if item.is_file())
                shutil.rmtree(path)
            elif path.is_file():
                path.unlink()
                deleted_files += 1
            for root_dir in (SCRIPTS_DIR, IMAGES_DIR, VIDEOS_DIR):
                if path.is_relative_to(root_dir.resolve()): _remove_empty_parents(path, root_dir)
        except OSError as exc:
            warnings.append(f"旧素材未能清理：{path.name}")

    from services.media_host import delete_published_image
    for remote_url in set(remote_images):
        try: delete_published_image(remote_url)
        except Exception: warnings.append("本地素材已清理，但部分云端参考图未能删除")

    response = {"ok": True, "id": project_id, "files_deleted": deleted_files}
    if warnings: response["cleanup_warning"] = "；".join(dict.fromkeys(warnings))
    return response
