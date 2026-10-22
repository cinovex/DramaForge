from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from models.drama import Character, Scene, Prop, Shot, Project, ImageSource

router = APIRouter(prefix="/api/library", tags=["library"])


@router.get("")
def listMedia(db: Session = Depends(get_db)):
    projects = {item.id: item for item in db.query(Project).all()}
    sources = {item.local_url: item for item in db.query(ImageSource).all()}
    items = []
    seen = set()

    def addMedia(url, name, kind, category, projectId, prompt=""):
        if not url or (projectId, url) in seen:
            return
        if not (url.startswith("/storage/") or url.startswith("https://")):
            return
        seen.add((projectId, url))
        source = sources.get(url)
        project = projects.get(projectId)
        items.append({"id": str(projectId) + ":" + str(len(items)), "url": url,
                      "name": name, "kind": kind, "category": category,
                      "projectId": projectId, "projectName": project.name if project else "",
                      "prompt": (source.prompt if source and source.prompt else prompt),
                      "createdAt": source.created_at.isoformat() if source and source.created_at else
                          project.created_at.isoformat() if project and project.created_at else ""})

    for character in db.query(Character).all():
        for url in [character.base_image_url, *(character.extra_images or []), *(character.reference_images or {}).values()]:
            if isinstance(url, str):
                addMedia(url, character.name, "image", "characters", character.project_id, character.description)
    for scene in db.query(Scene).all():
        for url in [scene.image_url, *(scene.image_versions or [])]:
            addMedia(url, scene.name, "image", "scenes", scene.project_id, scene.description)
    for prop in db.query(Prop).all():
        addMedia(prop.image_url, prop.name, "image", "props", prop.project_id, prop.description)
    for shot in db.query(Shot).all():
        name = "EP" + str(shot.episode_no) + " · 镜头 " + str(shot.shot_no)
        addMedia(shot.keyframe_url, name + " · 关键帧", "image", "works", shot.project_id, shot.keyframe_prompt)
        addMedia(shot.video_url, name + " · 视频", "video", "works", shot.project_id, shot.prompt)
    return {"items": items}
