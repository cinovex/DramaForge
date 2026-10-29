"""Durable sequential video generation; uncertain submissions are queried, never resubmitted."""
import asyncio
import hashlib
import json
import time
from uuid import uuid4, UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from database import get_db, SessionLocal
from models.drama import Project, Shot, videoQueueRecord
from services.director_design import ensure_project_idle

router = APIRouter(prefix="/api/projects", tags=["video-queues"])
workers = {}
queueLocks = {}

class QueueRequest(BaseModel):
    requestId: UUID
    episode: int = Field(gt=0)
    shotIds: list[int] = Field(min_length=1, max_length=200)
    model: str = Field(min_length=1, max_length=160)
    creditCeiling: int | None = Field(default=None, ge=0)

class ControlRequest(BaseModel):
    action: str = Field(pattern="^(pause|resume|stop)$")

def sourceSignature(project, shot):
    refs = [(c.id, c.base_image_url, c.reference_images) for c in project.characters if c.name in (shot.character_names or [])]
    refs += [(sc.id, sc.image_url) for sc in project.scenes if sc.name == shot.scene_name]
    refs += [(prop.id, prop.image_url) for prop in project.props]
    return hashlib.sha256(json.dumps({"prompt": shot.prompt, "duration": shot.duration, "settings": shot.generation_settings, "projectSettings": {k: v for k, v in (project.generation_settings or {}).items() if k in {"aspect_ratio", "resolution", "mode", "references"}}, "keyframe": shot.keyframe_url, "refs": refs}, sort_keys=True).encode()).hexdigest()

def snapshot(queue):
    return {"id": queue.id, "episode": queue.episode_no, "model": queue.model, "status": queue.status, "items": queue.items, "message": queue.message, "pauseRequested": bool(queue.pause_requested), "completed": sum(item["status"] in {"done", "skipped"} for item in queue.items), "total": len(queue.items), "creditCeiling": queue.credit_ceiling, "reservedCredits": queue.reserved_credits}

def startWorker(queueId):
    if queueId not in workers or workers[queueId].done(): workers[queueId] = asyncio.create_task(processQueue(queueId))

@router.get("/{projectId}/video-queues")
def listQueues(projectId: int, db: Session = Depends(get_db)):
    return [snapshot(q) for q in db.query(videoQueueRecord).filter_by(project_id=projectId).order_by(videoQueueRecord.created_at.desc()).limit(10).all()]

@router.post("/{projectId}/video-queues")
async def createQueue(projectId: int, body: QueueRequest, db: Session = Depends(get_db)):
    async with queueLocks.setdefault(projectId, asyncio.Lock()):
        existing = db.get(videoQueueRecord, str(body.requestId))
        if existing:
            if existing.project_id != projectId: raise HTTPException(409, "队列编号冲突")
            return snapshot(existing)
        ensure_project_idle(projectId, db)
        if db.query(videoQueueRecord).filter(videoQueueRecord.project_id == projectId, videoQueueRecord.status.in_(["queued", "running", "paused"])).first():
            raise HTTPException(409, "已有未结束队列，请先处理原队列")
        if body.model.startswith("dreamina:") and body.creditCeiling is None: raise HTTPException(422, "即梦批量必须指定本次总积分上限")
        shots = db.query(Shot).filter(Shot.project_id == projectId, Shot.episode_no == body.episode, Shot.id.in_(body.shotIds)).order_by(Shot.shot_no).all()
        if len(shots) != len(set(body.shotIds)): raise HTTPException(422, "所选分镜不属于当前集")
        project = db.get(Project, projectId)
        pending = [s for s in shots if not s.video_url and s.video_status != "processing"]
        if not pending: raise HTTPException(409, "所选片段均已完成或正在生成，本次未创建任务")
        queue = videoQueueRecord(id=str(body.requestId), project_id=projectId, episode_no=body.episode, model=body.model, credit_ceiling=body.creditCeiling, reserved_credits=0, status="queued", items=[{"shotId": s.id, "shotNo": s.shot_no, "status": "pending", "signature": sourceSignature(project, s)} for s in pending])
        db.add(queue); db.commit()
        startWorker(queue.id)
        return snapshot(queue)

@router.post("/{projectId}/video-queues/{queueId}/control")
async def controlQueue(projectId: int, queueId: UUID, body: ControlRequest, db: Session = Depends(get_db)):
    queue = db.get(videoQueueRecord, str(queueId))
    if not queue or queue.project_id != projectId: raise HTTPException(404, "队列不存在")
    if queue.status not in {"queued", "running", "paused"}: raise HTTPException(409, "队列已经结束，未重复提交")
    if body.action == "stop":
        if queue.status != "paused": raise HTTPException(409, "请先暂停并等待当前片段结束，再结束队列")
        queue.status = "stopped"; queue.message = "已结束后续队列，已生成素材保留"; db.commit()
        return snapshot(queue)
    if body.action == "pause":
        queue.pause_requested = 1
        queue.message = "完成当前片段后暂停后续提交"
    else:
        queue.pause_requested = 0
        queue.status = "queued"
        queue.message = "继续原队列，未重新提交已受理片段"
    db.commit()
    startWorker(queue.id)
    return snapshot(queue)

def saveItem(db, queue, index, item):
    items = [dict(value) for value in queue.items]
    items[index] = dict(item)
    queue.items = items
    db.commit()

async def processQueue(queueId):
    try:
        while True:
            with SessionLocal() as db:
                queue = db.get(videoQueueRecord, queueId)
                if not queue or queue.status not in {"queued", "running", "paused"}: return
                if queue.status == "paused" and not queue.pause_requested: return
                items = queue.items
                index = next((i for i, item in enumerate(items) if item["status"] not in {"done", "skipped"}), None)
                if index is None:
                    queue.status = "done"; queue.message = "批量生成完成"; db.commit(); return
                item = dict(items[index])
                shot = db.get(Shot, item["shotId"])
                if not shot or shot.project_id != queue.project_id: raise ValueError("分镜已删除，后续任务停止")
                if item["status"] == "pending":
                    if queue.pause_requested:
                        queue.status = "paused"; queue.message = "队列已暂停，尚未提交的片段保持不变"; db.commit(); return
                    if shot.video_url or shot.video_status == "processing":
                        item["status"] = "skipped"; saveItem(db, queue, index, item); continue
                    project = db.get(Project, queue.project_id)
                    ensure_project_idle(project.id, db)
                    if sourceSignature(project, shot) != item["signature"]: raise ValueError("分镜或参考素材已修改，队列停止，请重新确认生成范围")
                    item["status"] = "submitting"
                    item["startedAt"] = time.time()
                    queue.status = "running"; queue.message = f"正在提交片段 {shot.shot_no}"
                    saveItem(db, queue, index, item)
                    if queue.model == "pippit":
                        from api.pippit import generateTarget, TargetRequest
                        await generateTarget(TargetRequest(project_id=project.id, kind="video", target_id=shot.id, message=shot.prompt), db)
                    elif queue.model.startswith("dreamina:"):
                        from api.dreaminaGeneration import prepare, runGeneration, GenerationRequest, RunRequest
                        from services.generation_design import effective_options
                        opts = effective_options(project, shot)
                        job = await prepare(GenerationRequest(projectId=project.id, kind="video", targetId=shot.id, model=queue.model[9:], ratio=opts["aspect_ratio"], resolution=opts["resolution"]), db)
                        item["dreaminaJobId"] = job["jobId"]
                        if job["status"] == "quoted":
                            db.refresh(queue)
                            quote = job["quote"]
                            if quote > (queue.credit_ceiling or 0) - queue.reserved_credits: raise ValueError("即梦后续片段报价超过本次剩余积分上限，未提交该片段")
                            queue.reserved_credits += quote
                            saveItem(db, queue, index, item)
                            await runGeneration(project.id, UUID(job["jobId"]), RunRequest(creditCeiling=quote), db)
                    else:
                        from api.shots import generate_shot
                        await generate_shot(project.id, shot.id, queue.model, db)
                    db.refresh(shot)
                    item.update(status="waiting", providerTaskId=shot.provider_task_id)
                    saveItem(db, queue, index, item)
                else:
                    if time.time() - item.get("startedAt", time.time()) > 3600: raise ValueError("等待原任务超过一小时，后续队列已停止；远端未取消，请先核对原任务")
                    if item.get("dreaminaJobId"):
                        from api.dreaminaGeneration import queryGeneration
                        await queryGeneration(queue.project_id, UUID(item["dreaminaJobId"]), db)
                        db.refresh(shot)
                    if shot.video_url:
                        item["status"] = "done"; saveItem(db, queue, index, item); continue
                    if shot.video_status == "failed":
                        if queue.model == "pippit" and "积分不足" in (shot.last_error or ""):
                            from models.drama import pippitAccountRecord, pippitTaskRecord
                            task = db.query(pippitTaskRecord).filter_by(run_id=shot.provider_task_id).first()
                            binding = (task.result or {}).get("binding", {}) if task else {}
                            accountId = binding.get("accountId", "default")
                            account = db.get(pippitAccountRecord, accountId)
                            confirmed = task and task.status == "failed" and account and account.exhausted
                            nextAccount = db.query(pippitAccountRecord).filter(pippitAccountRecord.enabled == 1, pippitAccountRecord.exhausted == 0, pippitAccountRecord.id != accountId).order_by(pippitAccountRecord.created_at).first() if confirmed else None
                            attempts = list(item.get("exhaustedAccounts", []))
                            if nextAccount and nextAccount.id not in attempts:
                                item.update(status="pending", exhaustedAccounts=[*attempts, accountId])
                                shot.video_status = "pending"
                                queue.message = "原账号明确积分不足，切换下一个账号并复用同一套本地参考素材"
                                saveItem(db, queue, index, item)
                                continue
                        raise ValueError(shot.last_error or "片段生成失败，后续任务停止")
                    if not shot.provider_task_id: raise ValueError("提交结果未确认，队列已停止，请先核对原任务，禁止自动重提")
                    queue.status = "running"; queue.message = f"正在等待片段 {shot.shot_no}，已完成 {index}/{len(items)}"
                    db.commit()
            await asyncio.sleep(5)
    except Exception as error:
        with SessionLocal() as db:
            queue = db.get(videoQueueRecord, queueId)
            if queue:
                queue.status = "stopped"
                detail = getattr(error, "detail", str(error))
                queue.message = f"队列已停止：{detail}。未自动重复提交。"
                db.commit()

def restoreQueues():
    with SessionLocal() as db:
        for queue in db.query(videoQueueRecord).filter(videoQueueRecord.status.in_(["queued", "running"])).all(): startWorker(queue.id)
