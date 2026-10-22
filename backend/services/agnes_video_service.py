"""
Agnes Video 2.5 视频生成服务（OpenAI Videos 兼容接口）
POST {base_url}/videos 创建任务 → 轮询 GET {root}/agnesapi?video_id=xxx 获取结果

官方文档要点（wiki.agnes-ai.com）：
- 必填: model / prompt / mode ("text"|"keyframe"|"reference")
- seconds: 字符串 "4"-"12"；size: "720P"/"1080P"/"1K"/"2K"
- aspect_ratio: "21:9","16:9","4:3","1:1","3:4","9:16"
- 参考图必须为公网可达 URL（本地文件不能直接传 data URI）
- 轮询地址为站点根路径 /agnesapi（不带 /v1）
"""
import asyncio
from collections import deque
from threading import Lock
from time import monotonic
import uuid
import httpx
from sqlalchemy.orm import Session
from services.settings_service import get_stage_config
from services.gpt_service import GPTError
from config import VIDEOS_DIR, project_directory

_submit_lock=Lock()
_submit_slots=deque()

async def _limit_submit_rate():
    """单进程内所有单镜头及批量请求共享每分钟五次的提交额度。"""
    with _submit_lock:
        now=monotonic()
        while _submit_slots and _submit_slots[0]<=now-60:
            _submit_slots.popleft()
        scheduled=now if len(_submit_slots)<5 else max(now,_submit_slots[-5]+60)
        _submit_slots.append(scheduled)
    wait=scheduled-now
    if wait>0: await asyncio.sleep(wait)


def _to_public_reference(url: str | None, db: Session | None = None) -> str | None:
    """本地路径映射到生成提供商的原图地址，避免悄悄忽略参考图"""
    if not url:
        return None
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if db is not None:
        from models.drama import ImageSource
        source = db.query(ImageSource).filter_by(local_url=url).first()
        if source and source.remote_url.startswith("https://"): return source.remote_url
    return None


async def create_video_task(
    db: Session,
    prompt: str,
    duration: float = 7.0,
    aspect_ratio: str = "9:16",
    reference_image_url: str | None = None,
    model: str | None = None,
    use_keyframe: bool = False,
    generation: dict | None = None,
) -> str:
    """
    创建 Agnes Video 任务，返回 video_id (task_id)
    reference_image_url: 仅公网 http(s) URL 可用作参考图；本地路径通过原图地址映射解析，缺少原图映射时明确报错
    """
    cfg = get_stage_config(db, "video")
    if not cfg:
        raise GPTError("未配置视频生成环节", 400)
    if not cfg.get("api_key"):
        raise GPTError("未配置视频生成环节的 API Key，请到设置中心填写", 400)

    base_url = cfg["base_url"].rstrip("/")
    model = model or (generation or {}).get("model") or cfg.get("model", "agnes-video-2.5")
    headers = {"Authorization": f"Bearer {cfg['api_key']}"}

    if not 4 <= duration <= 12 or float(duration) != int(duration):
        raise GPTError("当前视频模型需要4–12秒的整数时长，请调整镜头时长与动作时间线", 400)
    payload: dict = {
        "model": model, "prompt": generation["prompt"] if generation else prompt,
        "mode": generation["mode"] if generation else "text",
        "seconds": str(int(duration)),
        "size": generation["resolution"] if generation else "720P",
        "aspect_ratio": generation["aspect_ratio"] if generation else aspect_ratio,
    }
    if generation:
        from services.media_host import video_image_input
        if generation["mode"] == "keyframe":
            payload["first_frame"] = video_image_input(db, generation["first_frame"])
        elif generation["mode"] == "reference":
            payload["images"] = [
                video_image_input(db, r.get("public_url") if (r.get("public_url") or "").startswith("https://") else r.get("url"))
                for r in generation["references"]
            ]
    else:
        ref_url = _to_public_reference(reference_image_url, db)
        if reference_image_url and not ref_url:
            from services.media_host import video_image_input
            ref_url = video_image_input(db, reference_image_url)
        if ref_url:
            if use_keyframe:
                payload["mode"]="keyframe";payload["first_frame"]=ref_url
            else:
                payload["mode"]="reference";payload["images"]=[ref_url]
                payload["prompt"]="使用 <Picture 1> 保持参考主体与视觉一致。"+prompt
    if model.endswith("-flash") and payload["size"] != "720P":
        raise GPTError("当前 Flash 视频模型仅支持720P",400)

    # 在扣费任务提交前确认每张图片仍可读取；提供商临时 URL 可能过期。
    media_urls=([payload["first_frame"]] if payload.get("first_frame") else []) + payload.get("images",[])
    if media_urls:
        from services.media_host import validate_video_image_payload
        validate_video_image_payload(media_urls)
        async with httpx.AsyncClient(timeout=12,follow_redirects=True) as probe:
            for media_url in media_urls:
                if media_url.startswith("data:image/"):
                    continue
                if not media_url.startswith("https://"):
                    raise GPTError('参考图必须使用公网 HTTPS 地址',400)
                try:
                    check=await probe.head(media_url)
                    if check.status_code in (403,405,501):
                        check=await probe.get(media_url,headers={"Range":"bytes=0-0"})
                    if check.status_code>=400:
                        raise GPTError(f'参考图已失效（HTTP {check.status_code}），请重新发布或生成参考图',400)
                except httpx.HTTPError as exc:
                    raise GPTError(f'参考图地址不可访问：{type(exc).__name__}',400) from exc

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            backoff = [5, 15, 30]
            attempts = 0
            while True:
                attempts += 1
                await _limit_submit_rate()
                resp = await client.post(f"{base_url}/videos", headers=headers, json=payload)
                # 免费模型队列常满，自动退避重试
                if resp.status_code in (429, 503) and attempts <= len(backoff):
                    await asyncio.sleep(backoff[attempts - 1])
                    continue
                break
            if resp.status_code == 401:
                raise GPTError("视频 API Key 无效（401）", 401)
            if resp.status_code == 402:
                raise GPTError("视频 API 余额/积分不足（402）", 402)
            if resp.status_code == 403:
                try:
                    d = resp.json()
                    msg = d.get("message") or d.get("error") or resp.text[:300]
                except Exception:
                    msg = resp.text[:300]
                raise GPTError(f"视频生成被拒绝（403）: {msg}", 403)
            if resp.status_code == 404:
                raise GPTError(f"视频模型 {model} 不存在（404），请检查模型名", 404)
            if resp.status_code == 400:
                raise GPTError(f"参数错误（400）: {resp.text[:300]}", 400)
            if resp.status_code == 422:
                raise GPTError(f"参数错误（422）: {resp.text[:300]}", 422)
            if resp.status_code in (429, 503):
                try:
                    d = resp.json()
                    msg = d.get("message") or d.get("error") or resp.text[:300]
                except Exception:
                    msg = resp.text[:300]
                raise GPTError(f"Agnes 服务繁忙（HTTP {resp.status_code}）: {msg}", 503)
            resp.raise_for_status()
            data = resp.json()
            video_id = data.get("video_id") or data.get("id") or data.get("task_id")
            if not video_id:
                raise GPTError(f"Agnes 未返回 video_id，响应: {data}", 502)
            return video_id
    except GPTError:
        raise
    except httpx.ConnectError:
        raise GPTError(f"无法连接到 Agnes {base_url}（视频生成）", 502)
    except httpx.TimeoutException:
        raise GPTError("Agnes 创建任务超时", 504)
    except Exception as e:
        raise GPTError(f"创建视频任务异常: {type(e).__name__}: {e}", 502)


async def poll_video(
    db: Session,
    video_id: str,
    max_wait: int = 3600,
    interval: int = 10,
    model_name: str | None = None,
    *,
    project_id: int,
    episode_no: int = 1,
    shot_no: int = 1,
) -> str:
    """
    轮询 Agnes 视频生成进度，完成后按集数和分镜号保存到项目目录。
    超时 60 分钟（免费模型排队可能较久）
    """
    cfg = get_stage_config(db, "video")
    base_url = cfg["base_url"].rstrip("/")
    # 轮询端点在站点根路径 /agnesapi（官方示例不带 /v1）
    poll_base = base_url[:-3] if base_url.endswith("/v1") else base_url
    model = model_name or cfg.get("model", "agnes-video-2.5")
    headers = {"Authorization": f"Bearer {cfg['api_key']}"}

    last_status = "unknown"
    for _ in range(max_wait // interval):
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(f"{poll_base}/agnesapi", headers=headers,
                                        params={"video_id": video_id, "model_name": model})
                if resp.status_code == 404 and poll_base != base_url:
                    resp = await client.get(f"{base_url}/agnesapi", headers=headers,
                                            params={"video_id": video_id, "model_name": model})
                if resp.status_code == 429:
                    # 查询过于频繁，加倍等待后继续
                    last_status = "HTTP 429"
                    await asyncio.sleep(interval * 2)
                    continue
                if resp.status_code != 200:
                    last_status = f"HTTP {resp.status_code}"
                    await asyncio.sleep(interval)
                    continue
                data = resp.json()
                status = data.get("status", "unknown")
                last_status = status

                if status == "completed" or status == "succeeded":
                    # 获取视频 URL
                    video_url = data.get("url") or data.get("video_url") or ""
                    if not video_url and isinstance(data.get("data"), list) and data["data"]:
                        video_url = data["data"][0].get("url", "")
                    if not video_url:
                        raise GPTError(f"Agnes 返回 completed 但无视频 URL: {data}", 502)
                    # 下载到本地
                    dl = await client.get(video_url, timeout=120)
                    dl.raise_for_status()
                    target_dir = project_directory(project_id) / "videos"
                    target_dir.mkdir(parents=True, exist_ok=True)
                    task_suffix = "".join(ch for ch in str(video_id) if ch.isalnum())[-8:] or uuid.uuid4().hex[:8]
                    fname = f"EP{max(1, int(episode_no or 1)):02d}_第{max(1, int(shot_no or 1)):03d}段_{task_suffix}.mp4"
                    (target_dir / fname).write_bytes(dl.content)
                    return f"/storage/projects/{project_id}/videos/{fname}"

                elif status == "failed" or status == "error":
                    err = data.get("error") or data.get("message") or str(data)
                    if isinstance(err, dict):
                        err = err.get("message") or str(err)
                    raise GPTError(f"Agnes 视频生成失败: {err}", 500)

                # pending / processing / queued
                await asyncio.sleep(interval)

        except GPTError:
            raise
        except httpx.ConnectError:
            await asyncio.sleep(interval)
        except httpx.TimeoutException:
            await asyncio.sleep(interval)

    raise GPTError(f"视频生成超时（{max_wait}s），最后状态: {last_status}", 504)


async def generate_shot_video(
    db: Session,
    prompt: str,
    project_id: int,
    duration: float = 7.0,
    aspect_ratio: str = "9:16",
    reference_image_url: str | None = None,
    episode_no: int = 1,
    shot_no: int = 1,
) -> str:
    """一键：创建 + 轮询 + 下载，返回本地视频相对 URL"""
    video_id = await create_video_task(
        db, prompt, duration, aspect_ratio, reference_image_url
    )
    return await poll_video(db, video_id, project_id=project_id,
                            episode_no=episode_no, shot_no=shot_no)
