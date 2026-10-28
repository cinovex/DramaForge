import asyncio
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime
from database import get_db, SessionLocal
from models.drama import Shot, Scene, Character, Outline
from services import agnes_video_service, gpt_service
from services.director_design import ensure_project_idle

router = APIRouter(prefix="/api/projects", tags=["shots"])


def _build_prompt(
    shot: Shot,
    scene: Scene | None,
    characters: list[Character] | None = None,
    aspect_ratio: str = "9:16",
) -> str:
    """
    组装喂给 Agnes 的完整 prompt：
    场景 + 角色描述（面容/服装一致性） + 镜头 + 全局约束
    """
    # 场景
    scene_part = (
        f"场景：{scene.name}（{scene.description}）"
        if scene and scene.description else
        f"场景：{scene.name}" if scene else
        "（无场景信息）"
    )

    # 角色（注入描述以保跨镜头一致性）
    if characters:
        char_descs = []
        for ch in characters:
            d = ch.description.strip() if ch.description else ""
            char_descs.append(f"{ch.name}（{d}）" if d else ch.name)
        char_part = "出场角色：" + "、".join(char_descs)
    elif shot.character_names:
        chars = "、".join(shot.character_names)
        char_part = f"出场角色：{chars}（保持面容服饰与参考图一致）"
    else:
        char_part = "无特定角色"

    # 全局约束
    orientation = (
        "竖屏（9:16）构图，画面中人物保持直立、正立，禁止横向倾斜构图。"
        if aspect_ratio in ("9:16", "3:4")
        else "横屏构图，画面保持水平。"
    )
    constraint = (
        f"。{orientation}"
        "视频全程不要出现字幕或屏幕文字；"
        "优先遵循本镜头声音设计：对白清晰，语速音量和停顿依照表演调度；配乐不得盖过对白，可按剧情压低或短暂抽掉，保留必要环境音，不强制全程铺满BGM。"
        "画面稳定，角色面容服饰全程保持一致。"
    )

    from services.director_design import direction_prompt
    detailed = direction_prompt(shot.direction)
    return f"{scene_part}。{char_part}。{shot.prompt}\n{detailed}{constraint}"


async def _background_generate(
    shot_id: int, provider_task_id: str, prompt: str, model: str | None = None
):
    """后台轮询 + 下载 + 更新 DB（独立 session）"""
    db = SessionLocal()
    try:
        shot = db.query(Shot).get(shot_id)
        if not shot:
            return
        shot.video_status = "processing"
        if not shot.started_at:
            shot.started_at = datetime.utcnow()
        db.commit()
        try:
            video_url = await agnes_video_service.poll_video(
                db, provider_task_id, model_name=model,
                project_id=shot.project_id, episode_no=shot.episode_no, shot_no=shot.shot_no,
            )
            # 记录历史
            hist = list(shot.history or [])
            hist.append({
                "video_url": video_url,
                "provider_task_id": provider_task_id,
                "prompt": prompt,
                "manifest": shot.generation_manifest or {},
            })
            shot.history = hist[-10:]
            shot.video_url = video_url
            shot.video_status = "done"
            shot.review_status = "needs_review"
            shot.review_note = ""
            shot.finished_at = datetime.utcnow()
        except gpt_service.GPTError as e:
            shot.video_status = "failed"
            shot.finished_at = datetime.utcnow()
            shot.last_error = e.message
        except Exception:
            shot.video_status = "failed"
            shot.finished_at = datetime.utcnow()
            shot.last_error = "视频处理失败，请重新生成"
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()


@router.post("/{project_id}/shots/{shot_id}/generate")
async def generate_shot(
    project_id: int,
    shot_id: int,
    model: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """
    生成单个分镜视频（非阻塞）：
    1. 立即创建 Agnes task 拿到 video_id
    2. 后台轮询完成下载
    3. 返回 video_status=processing + provider_task_id
    """
    shot = db.query(Shot).filter_by(id=shot_id, project_id=project_id).first()
    if not shot:
        raise HTTPException(404, "分镜不存在")

    if shot.video_status == "processing":
        raise HTTPException(409, "分镜正在生成，请等待当前任务完成")

    ensure_project_idle(project_id, db)
    # 组装 prompt + 参考图
    scene = db.query(Scene).filter(
        Scene.project_id == project_id, Scene.name == shot.scene_name
    ).first() if shot.scene_name else None
    # 获取角色描述用于一致性
    char_list = []
    if shot.character_names:
        for cname in shot.character_names:
            ch = db.query(Character).filter(
                Character.project_id == project_id, Character.name == cname
            ).first()
            if ch:
                char_list.append(ch)
    from models.drama import Project
    from services.generation_design import compile_generation, generation_manifest
    try:
        generation=compile_generation(db,db.get(Project,project_id),shot,model)
        prompt=generation["prompt"]
        claimed = db.query(Shot).filter(Shot.id == shot_id, Shot.project_id == project_id,
            Shot.video_status != "processing").update({
                Shot.video_status: "processing", Shot.provider_task_id: "",
                Shot.started_at: datetime.utcnow(), Shot.finished_at: None,
                Shot.last_error: ""}, synchronize_session=False)
        db.commit()
        if not claimed: raise HTTPException(409, "分镜正在生成，请等待当前任务完成")
        provider_task_id=await agnes_video_service.create_video_task(
            db,prompt,duration=shot.duration,model=model,generation=generation)
    except gpt_service.GPTError as e:
        db.rollback()
        if 'claimed' in locals() and claimed:
            db.query(Shot).filter_by(id=shot_id).update({Shot.video_status:"failed",Shot.last_error:e.message},synchronize_session=False)
            db.commit()
        raise HTTPException(e.status_code,e.message)
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        if 'claimed' in locals() and claimed:
            db.query(Shot).filter_by(id=shot_id).update({Shot.video_status:"failed",Shot.last_error:"视频任务提交失败"},synchronize_session=False)
            db.commit()
        raise HTTPException(502,"视频任务提交失败，请重试")
    reference_image_url=shot.keyframe_url if generation["mode"]=="keyframe" else (generation["references"][0]["url"] if generation["references"] else None)

    # 2. 存状态 + 后台轮询
    db.refresh(shot)
    shot.provider_task_id = provider_task_id
    shot.provider_model = generation["model"]
    shot.generation_manifest = generation_manifest(generation)
    shot.started_at = datetime.utcnow()
    shot.finished_at = None
    shot.last_error = ""
    db.commit()
    asyncio.create_task(
        _background_generate(shot_id, provider_task_id, prompt, model=generation["model"])
    )
    return {
        "shot_id": shot_id,
        "video_status": "processing",
        "provider_task_id": provider_task_id,
        "reference_image_url": reference_image_url,
        "message": "视频生成任务已提交，后台处理中，请轮询状态接口",
    }


from pydantic import BaseModel, Field


class ShotUpdate(BaseModel):
    """自然语言修改分镜 prompt（可局部替换）"""
    prompt: str
    duration: int | None = Field(default=None, ge=4, le=12)
    scene_name: str | None = None
    character_names: list[str] | None = None


@router.put("/{project_id}/shots/{shot_id}")
def update_shot(project_id: int, shot_id: int, body: ShotUpdate, db: Session = Depends(get_db)):
    """
    编辑分镜（支持自然语言修改）：
    - 只改 prompt（最常见：用口语说"把光线改暗一点"）
    - 可改 duration / scene / characters
    """
    shot = db.query(Shot).filter_by(id=shot_id, project_id=project_id).first()
    if not shot:
        raise HTTPException(404, "分镜不存在")

    if shot.video_status == "processing":
        raise HTTPException(409, "分镜正在生成，暂时不能编辑")

    ensure_project_idle(project_id, db)
    if body.prompt is not None:
        shot.prompt = body.prompt
    if body.duration is not None:
        shot.duration = body.duration
    if body.scene_name is not None:
        shot.scene_name = body.scene_name
    if body.character_names is not None:
        shot.character_names = body.character_names

    # 重置视频状态（prompt 改了需要重新生成）
    shot.video_status = "pending"
    shot.video_url = ""
    db.commit()
    db.refresh(shot)
    return {
        "shot_id": shot_id,
        "prompt": shot.prompt,
        "video_status": shot.video_status,
        "message": "已更新，需重新生成视频",
    }


@router.get("/{project_id}/shots/{shot_id}/status")
def shot_status(project_id: int, shot_id: int, db: Session = Depends(get_db)):
    shot = db.query(Shot).filter_by(id=shot_id, project_id=project_id).first()
    if not shot:
        raise HTTPException(404, "分镜不存在")
    return {
        "shot_id": shot_id,
        "video_status": shot.video_status,
        "video_url": shot.video_url,
        "provider_task_id": shot.provider_task_id,
        "started_at": shot.started_at.isoformat() if shot.started_at else None,
        "finished_at": shot.finished_at.isoformat() if shot.finished_at else None,
        "history": shot.history or [],
    }
