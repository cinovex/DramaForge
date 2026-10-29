"""Project-owned Dreamina jobs backed by the official CLI, without a separate canvas UI."""
import asyncio
import hashlib
import json
from uuid import uuid4, UUID
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from database import get_db
from models.drama import Project
from config import STORAGE_DIR
from api.dreaminaCanvas import runCli
from api.pippit import targetAsset
from services.director_design import ensure_project_idle
from services.image_service import build_asset_prompt

router = APIRouter(prefix="/api/dreamina", tags=["dreamina"])
projectLocks = {}

class GenerationRequest(BaseModel):
    projectId: int
    kind: Literal["character", "scene", "prop", "video"]
    targetId: int
    model: str = Field(min_length=1, max_length=160)
    variant: str = Field(default="base", pattern=r"^(base|front|side|back|three_quarter|turnaround|detail_sheet|expressions)$")
    ratio: str = "9:16"
    resolution: str = "2K"

class RunRequest(BaseModel):
    creditCeiling: int = Field(ge=0)

def saveTask(db, project, jobId, job):
    db.refresh(project, ["generation_settings"])
    settings = dict(project.generation_settings or {})
    settings.setdefault("dreaminaProviderProjectId", job["projectId"])
    jobs = dict(settings.get("dreaminaJobs", {}))
    jobs[jobId] = dict(job)
    project.generation_settings = {**settings, "dreaminaJobs": jobs}
    db.commit()

def readTask(db, projectId, jobId):
    project = db.get(Project, projectId)
    job = (project.generation_settings or {}).get("dreaminaJobs", {}).get(jobId) if project else None
    if not job: raise HTTPException(404, "即梦任务不存在")
    return project, dict(job)

@router.get("/models")
async def models():
    result = {}
    for kind in ("image", "video"):
        result[kind] = (await runCli("model", "list", "--type", kind)).get("data", {}).get("items", [])
    return result

@router.post("/prepare")
async def prepare(body: GenerationRequest, db: Session = Depends(get_db)):
    async with projectLocks.setdefault(body.projectId, asyncio.Lock()):
        ensure_project_idle(body.projectId, db)
        project = db.get(Project, body.projectId)
        asset = targetAsset(db, {"project_id": body.projectId, "kind": body.kind, "target_id": body.targetId})
        if body.kind == "video" and asset.video_status == "processing": raise HTTPException(409, "当前片段正在生成")
        prompt = asset.prompt if body.kind == "video" else build_asset_prompt(body.kind, asset, body.variant)
        fingerprint = hashlib.sha256(json.dumps({**body.model_dump(), "prompt": prompt, "references": [(c.id, c.base_image_url, c.reference_images) for c in project.characters] + [(sc.id, sc.image_url) for sc in project.scenes]}, sort_keys=True).encode()).hexdigest()
        jobs = (project.generation_settings or {}).get("dreaminaJobs", {})
        for jobId, job in jobs.items():
            if job["kind"] == body.kind and job["targetId"] == body.targetId and job.get("variant") == body.variant and job["status"] in {"preparing", "quoted", "submitting", "running", "unknown"}:
                if job.get("fingerprint") != fingerprint:
                    if job["status"] != "quoted": raise HTTPException(409, "即梦原任务结果未确认，请先查询原任务，不能切模型重复提交")
                    continue
                return {"jobId": jobId, **job}
        kind = "video" if body.kind == "video" else "image"
        catalog = (await runCli("model", "list", "--type", kind)).get("data", {}).get("items", [])
        model = next((item for item in catalog if item["model"] == body.model), None)
        if not model: raise HTTPException(422, "所选即梦模型已不可用，请刷新模型目录")
        references = []
        if kind == "video":
            from services.generation_design import reference_items, effective_options
            references = [item["url"] for item in reference_items(db, project, asset, effective_options(project, asset))]
            if any(not url for url in references): raise HTTPException(409, "请先生成或上传当前片段的参考图")
            prompt = asset.prompt
        else:
            prompt = build_asset_prompt(body.kind, asset, body.variant)
            if body.kind == "character" and body.variant != "base" and asset.base_image_url: references = [asset.base_image_url]
        modeName = "m2v" if kind == "video" and references else "t2v" if kind == "video" else "i2i" if references else "t2i"
        mode = next((item for item in model["modes"] if item["name"] == modeName), None)
        if not mode: raise HTTPException(422, "该模型不支持当前参考素材模式，请选择其他模型")
        limits = mode.get("references")
        if references and (not limits or not limits.get("min", 0) <= len(references) <= limits.get("max", 0)):
            raise HTTPException(422, "当前参考图数量不符合所选模型要求，未上传或生成")
        flags = {item["flag"]: item for item in mode["flags"]}
        args = []
        for flag, value in (("--ratio", body.ratio), ("--resolution", body.resolution)):
            spec = flags.get(flag)
            if not spec: continue
            selected = next((v for v in spec.get("values", []) if v.lower() == value.lower()), None)
            if not selected: raise HTTPException(422, f"所选模型不支持 {value}，可用值：{', '.join(spec.get('values', []))}")
            args += [flag, selected]
        if references and not any(item.get("mediaType") == "image" and item.get("max", 0) >= len(references) for item in (limits or {}).get("types", [])):
            raise HTTPException(422, "所选模型不支持当前图片参考，未上传或生成")
        promptSpec = flags.get("--prompt", {})
        if len(prompt) > promptSpec.get("maxLength", 100000): raise HTTPException(422, "提示词超过所选模型长度限制，请精简后重试，不会自动截断对白")
        if kind == "video" and "--duration" in flags:
            spec = flags["--duration"]
            duration = asset.duration
            if not spec.get("min", 0) <= duration <= spec.get("max", 100000): raise HTTPException(422, "片段时长不符合该模型要求")
            args += ["--duration", str(duration)]
        jobId = str(uuid4())
        cloudId = (project.generation_settings or {}).get("dreaminaProviderProjectId") or str(uuid4())
        project.generation_settings = {**(project.generation_settings or {}), "dreaminaProviderProjectId": cloudId}
        job = {"kind": body.kind, "targetId": body.targetId, "variant": body.variant, "model": body.model, "projectId": cloudId, "nodeId": "node_" + uuid4().hex, "updateId": str(uuid4()), "submitId": str(uuid4()), "status": "preparing", "prompt": prompt, "fingerprint": fingerprint}
        saveTask(db, project, jobId, job)
        try:
            await runCli("canvas", "create", "--project-id", cloudId, "--", project.name)
            for index, url in enumerate(dict.fromkeys(references)):
                if not url.startswith("/storage/"): raise HTTPException(422, "参考图须先保存到本地项目")
                path = (STORAGE_DIR / url.removeprefix("/storage/")).resolve()
                if not path.is_relative_to(STORAGE_DIR.resolve()) or not path.is_file(): raise HTTPException(422, "参考文件不存在")
                resourceId = str(uuid4())
                job["referenceResources"] = [*job.get("referenceResources", []), {"resourceId": resourceId, "localUrl": url, "reason": "本地资产尚无即梦来源节点，上传固定参考版本"}]
                saveTask(db, project, jobId, job)
                uploaded = (await runCli("resource", "upload", "--project-id", cloudId, "--file", str(path), "--type", "image", "--resource-id", resourceId, "--import-kind", "external_generated")).get("data", {})
                resourceId = uploaded.get("resourceId", resourceId)
                args += ["--ref", "res:" + resourceId]
            await runCli("node", "create", kind, "--project-id", cloudId, "--node-id", job["nodeId"], "--update-id", job["updateId"], "--title", f"{body.kind} {body.targetId}", "--mode", modeName, "--model", body.model, "--prompt", prompt, "--count", "1", *args)
            quote = (await runCli("node", "quote", "--project-id", cloudId, "--node-id", job["nodeId"])).get("data", {})
            if any(item.get("error") for item in quote.get("items", [])) or not isinstance(quote.get("totalMaxCredits"), int): raise HTTPException(409, "即梦未能给出完整积分报价，未提交生成")
            job.update(status="quoted", quote=quote["totalMaxCredits"])
            saveTask(db, project, jobId, job)
            return {"jobId": jobId, **job}
        except Exception:
            job["status"] = "prepare_failed"
            saveTask(db, project, jobId, job)
            raise

@router.post("/projects/{projectId}/jobs/{jobId}/run")
async def runGeneration(projectId: int, jobId: UUID, body: RunRequest, db: Session = Depends(get_db)):
    async with projectLocks.setdefault(projectId, asyncio.Lock()):
        project, job = readTask(db, projectId, str(jobId))
        if job["status"] != "quoted": return {"jobId": str(jobId), **job}
        ensure_project_idle(projectId, db)
        if body.creditCeiling < job["quote"]: raise HTTPException(409, "批准积分上限低于报价")
        approval = (await runCli("node", "confirm", "--project-id", job["projectId"], "--node-id", job["nodeId"], "--credit-ceiling", str(body.creditCeiling))).get("data", {})
        job.update(status="submitting", creditCeiling=body.creditCeiling)
        if job["kind"] == "video":
            asset = targetAsset(db, {"project_id": projectId, "kind": "video", "target_id": job["targetId"]})
            if asset.video_status == "processing": raise HTTPException(409, "片段正在生成，请查询原任务")
            asset.video_status = "processing"
            asset.provider_model = "dreamina:" + job["model"]
            asset.provider_task_id = job["submitId"]
            asset.last_error = ""
        saveTask(db, project, str(jobId), job)
        try:
            await runCli("node", "run", "--project-id", job["projectId"], "--node-id", job["nodeId"], "--submit-id", job["submitId"], "--credit-token", approval["creditConfirmationToken"])
            job["status"] = "running"
        except Exception:
            job["status"] = "unknown"
            saveTask(db, project, str(jobId), job)
            raise
        saveTask(db, project, str(jobId), job)
        return {"jobId": str(jobId), **job}

@router.get("/projects/{projectId}/jobs/{jobId}")
async def queryGeneration(projectId: int, jobId: UUID, db: Session = Depends(get_db)):
    async with projectLocks.setdefault(projectId, asyncio.Lock()):
        project, job = readTask(db, projectId, str(jobId))
        if job["status"] not in {"running", "submitting", "unknown"}: return {"jobId": str(jobId), **job}
        data = (await runCli("operation", "status", job["submitId"], "--project-id", job["projectId"])).get("data", {})
        resources = data.get("resources", [])
        ready = next((item for item in resources if item.get("state") == "success"), None)
        if ready:
            folder = STORAGE_DIR / "projects" / str(projectId) / "dreamina" / str(jobId)
            folder.mkdir(parents=True, exist_ok=True)
            extension = ".mp4" if job["kind"] == "video" else ".png"
            output = folder / ("result" + extension)
            if not output.exists():
                await runCli("resource", "download", ready["resourceId"], "--project-id", job["projectId"], "--output", str(output))
            if not output.is_file() or not output.stat().st_size: raise HTTPException(502, "即梦结果尚未保存，请刷新原任务")
            if job["kind"] == "video":
                from api.batch import FFPROBE
                import subprocess, json
                probe = await asyncio.to_thread(subprocess.run, [FFPROBE, "-v", "error", "-show_streams", "-of", "json", str(output)], capture_output=True, timeout=30)
                if probe.returncode or not any(stream.get("codec_type") == "video" for stream in json.loads(probe.stdout).get("streams", [])):
                    raise HTTPException(502, "即梦下载结果未通过视频校验，未绑定片段")
            url = "/storage/" + output.relative_to(STORAGE_DIR).as_posix()
            if job["kind"] != "video":
                from PIL import Image
                with Image.open(output) as image: image.verify()
            asset = targetAsset(db, {"project_id": projectId, "kind": job["kind"], "target_id": job["targetId"]})
            if job["kind"] == "video" and asset.provider_task_id != job["submitId"]:
                job.update(status="superseded", url=url)
                saveTask(db, project, str(jobId), job)
                return {"jobId": str(jobId), **job}
            if job["kind"] == "video": asset.video_url = url; asset.video_status = "done"; asset.provider_model = "dreamina:" + job["model"]
            elif job["kind"] == "character":
                if job["variant"] == "base": asset.base_image_url = url
                else: asset.reference_images = {**(asset.reference_images or {}), job["variant"]: url}
            else: asset.image_url = url
            job.update(status="done", url=url, resourceId=ready["resourceId"], sha256=hashlib.sha256(output.read_bytes()).hexdigest())
        elif data.get("state") in {"failed", "canceled"} or any(item.get("state") in {"failed", "canceled"} for item in resources):
            job.update(status="failed", error="即梦任务未完成，请核对账号权益及原任务状态")
            if job["kind"] == "video":
                asset = targetAsset(db, {"project_id": projectId, "kind": "video", "target_id": job["targetId"]})
                if asset.provider_task_id == job["submitId"]: asset.video_status = "failed"; asset.last_error = job["error"]
        job["operationState"] = data.get("state", "unknown")
        saveTask(db, project, str(jobId), job)
        return {"jobId": str(jobId), **job}


@router.post("/projects/{projectId}/jobs/{jobId}/stop-waiting")
async def stopWaiting(projectId: int, jobId: UUID, db: Session = Depends(get_db)):
    async with projectLocks.setdefault(projectId, asyncio.Lock()):
        project, job = readTask(db, projectId, str(jobId))
        if job["status"] not in {"running", "submitting", "unknown"}: raise HTTPException(409, "任务已结束或尚未提交")
        job["status"] = "local_stopped"
        if job["kind"] == "video":
            asset = targetAsset(db, {"project_id": projectId, "kind": "video", "target_id": job["targetId"]})
            if asset.provider_task_id == job["submitId"]:
                asset.video_status = "failed"
                asset.last_error = "已停止即梦本地等待，远端未取消，可能仍消耗积分；重新生成前请核对原任务。"
        saveTask(db, project, str(jobId), job)
        return {"status": job["status"]}
