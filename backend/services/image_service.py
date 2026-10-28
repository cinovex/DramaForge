"""图片生成（用 image 环节配置，默认 GPT gpt-image-1），保存到所属项目目录。"""
import base64
import uuid
from pathlib import Path
import httpx
from sqlalchemy.orm import Session
from services.settings_service import get_stage_config
from services.gpt_service import GPTError
from config import IMAGES_DIR, PROJECTS_DIR, STORAGE_DIR, project_directory


def _image_extension(data: bytes) -> str:
    if data.startswith(b'\xff\xd8\xff'): return 'jpg'
    if data.startswith(b'RIFF') and data[8:12] == b'WEBP': return 'webp'
    return 'png'

def _save_image(b64: str, project_id: int, subdir: str) -> str:
    """保存 b64 图片，返回相对 URL。"""
    data = base64.b64decode(b64)
    ext = _image_extension(data)
    target_dir = project_directory(project_id) / "images" / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{uuid.uuid4().hex}.{ext}"
    (target_dir / fname).write_bytes(data)
    return f"/storage/projects/{project_id}/images/{subdir}/{fname}"

def _store_image_prompt(db: Session, local_url: str, prompt: str, model: str) -> None:
    """Keep the exact generation prompt beside each saved image version."""
    from models.drama import ImageSource
    row = db.query(ImageSource).filter_by(local_url=local_url).first()
    if row:
        row.prompt = prompt
        row.model = model
    else:
        db.add(ImageSource(local_url=local_url, remote_url="", prompt=prompt, model=model))
    db.flush()


def build_asset_prompt(kind: str, asset, variant: str = "base") -> str:
    prompt = buildAssetPromptBase(kind, asset, variant)
    project = asset.project
    preferences = (project.generation_settings or {}).get("creativePreferences") or {}
    style = preferences.get("stylePrompt")
    if style:
        if preferences.get("styleId") in {"anime", "ink", "animation"}:
            import re
            prompt = re.sub(r"photorealistic(?: environment)?", "", prompt, flags=re.IGNORECASE)
        prompt += f"\n项目选定视觉风格（保持全剧一致）：{style}。既有默认风格词与此冲突时，以此项目风格为准。"
    return prompt


def buildAssetPromptBase(kind: str, asset, variant: str = "base") -> str:
    """Build the exact prompt used for a generated or externally uploaded asset image."""
    if kind == "character":
        design = asset.design or {}
        if variant == "base":
            prompt = (design.get("views", {}).get("front") or
                      f"Cinematic character reference for '{asset.name}': {asset.description}. "
                      "Full body, front view, neutral pose, plain dark background, "
                      "soft even studio lighting, photorealistic, high detail.")
            return prompt + "\n这是全剧固定身份主参考：单人正面全身站姿，眼睛与面部清楚可见；眉眼、嘴角与下颌自然放松，保持中性表情。柔和均匀棚拍光，干净简洁的纯色背景，服装和发型完整可辨。不要动作瞬间、夸张情绪、剧情场景、其他人物、拼图、文字或水印。"
        prompt = ""
        if variant in ("front", "side", "back", "three_quarter"):
            prompt = (design.get("views") or {}).get(variant, "")
        elif variant == "detail_sheet":
            prompt = "制作同一角色的精细2×2设定图：左上正面头肩近景，右上严格侧面头肩近景，左下正面全身，右下背面全身。头肩图清晰展示五官、发际线、皮肤质感；全身图完整展示固定服装、身形和鞋子。所有格子同一人物、同一套服装、中性表情、柔和中性光、干净背景，无文字、无水印，不新增伤疤、配饰或剧情动作。"
        elif variant == "turnaround":
            prompt = design.get("turnaround_prompt", "")
        elif variant == "expressions":
            prompt = design.get("expression_sheet_prompt", "")
        elif variant.startswith("expression_"):
            try:
                index = int(variant.split("_")[1])
                expression = (design.get("expressions") or [])[index]
                prompt = expression.get("prompt", "") + "。避免：" + expression.get("negative_prompt", "")
            except (ValueError, IndexError, KeyError, TypeError):
                prompt = ""
        if not prompt:
            raise GPTError("该参考提示词尚未填写，请先完成剧本分析", 400)
        return (prompt + f"\n角色身份锁定：{asset.description}。{design.get('identity', '')}。服装：{design.get('wardrobe', '')}。避免：{design.get('negative_prompt', '')}。同一人物，保持五官比例、发型、服装一致，不添加水印。")

    if variant != "base":
        raise GPTError("场景与道具只支持主参考图", 400)
    if kind == "scene":
        prompt = ((asset.design or {}).get("reference_prompt") or
                  f"Cinematic establishing shot of '{asset.name}': {asset.description}. "
                  "Wide angle, no characters, atmospheric lighting, photorealistic environment, high detail.")
        return prompt + "\n这是全剧固定场景主参考：独立空间定景图，无人物、无临时表演；入口、出口、主要道具位置、活动轴线、光源方向和材质清楚可辨，供后续镜头保持空间布局一致。不要拼图、文字或水印。"
    if kind == "prop":
        return (f"Product/prop reference for '{asset.name}': {asset.description}. "
                "Centered on neutral dark background, studio lighting, photorealistic, high detail.")
    raise GPTError("不支持的资产类型", 400)


async def _generate_image(db: Session, prompt: str, project_id: int, subdir: str,
                          size: str = "1024x1024",
                          reference_image: bytes | None = None,
                          model: str | None = None,
                          reference_images: list[bytes] | None = None,
                          aspect_ratio: str | None = None) -> str:
    """生成单张图片，返回相对 URL。reference_image 用于一致性（可选）"""
    cfg = get_stage_config(db, "image")
    if not cfg or not cfg.get("api_key"):
        raise GPTError("未配置图片生成环节的 API Key，请到设置中心填写", 400)

    base_url = cfg["base_url"].rstrip("/")
    model = model or cfg.get("model", "gpt-image-1")
    headers = {"Authorization": f"Bearer {cfg['api_key']}"}

    try:
        async with httpx.AsyncClient(timeout=300) as client:
            if model.startswith("agnes-image-"):
                # Agnes 图生图使用 generations + extra_body.image，不能调用 images/edits。
                ratio = aspect_ratio or {"1024x1536": "2:3", "1536x1024": "3:2"}.get(size, "1:1")
                extra = {"response_format": "url"}
                refs = reference_images or ([reference_image] if reference_image else [])
                if refs: extra["image"] = ["data:image/png;base64," + base64.b64encode(ref).decode("ascii") for ref in refs]
                # Use the 2K tier for Agnes image generation: it keeps references
                # detailed while avoiding the much tighter 4K request-rate limit.
                resp = await client.post(f"{base_url}/images/generations",headers=headers,
                    json={"model": model, "prompt": prompt, "size": "2K", "ratio": ratio, "extra_body": extra})
            elif reference_images and len(reference_images)>1:
                raise GPTError('当前图片模型不支持多张角色/场景参考图，请切换支持多图输入的 Agnes 图片模型',400)
            elif reference_image or reference_images:
                # 基于参考图编辑（保持角色一致性）
                image_input=reference_image or reference_images[0]
                resp = await client.post(
                    f"{base_url}/images/edits",
                    headers=headers,
                    files={"image": ("ref.png", image_input, "image/png")},
                    data={"model": model, "prompt": prompt,
                          "size": size, "n": "1"},
                )
            else:
                resp = await client.post(
                    f"{base_url}/images/generations",
                    headers=headers,
                    json={"model": model, "prompt": prompt,
                          "size": size, "n": 1},
                )

            if resp.status_code == 401:
                raise GPTError("图片 API Key 无效（401）", 401)
            if resp.status_code == 402:
                raise GPTError("图片 API 余额不足（402）", 402)
            resp.raise_for_status()
            data = resp.json()

            item = data["data"][0]
            if item.get("b64_json"):
                local_url = _save_image(item["b64_json"], project_id, subdir)
                from services.media_host import publish_local_image
                publish_local_image(db,local_url)
                _store_image_prompt(db,local_url,prompt,model)
                return local_url
            if item.get("url"):
                # 从 url 下载并保存
                img_resp = await client.get(item["url"], timeout=60)
                img_resp.raise_for_status()
                ext = _image_extension(img_resp.content)
                target_dir = project_directory(project_id) / "images" / subdir
                target_dir.mkdir(parents=True, exist_ok=True)
                fname = f"{uuid.uuid4().hex}.{ext}"
                (target_dir / fname).write_bytes(img_resp.content)
                local_url = f"/storage/projects/{project_id}/images/{subdir}/{fname}"
                from models.drama import ImageSource
                from services.media_host import publish_local_image
                hosted=publish_local_image(db,local_url)
                if not hosted: db.add(ImageSource(local_url=local_url,remote_url=item["url"]))
                db.flush()
                _store_image_prompt(db,local_url,prompt,model)
                return local_url
            raise GPTError("图片 API 未返回图像数据", 502)
    except GPTError:
        raise
    except httpx.ConnectError:
        raise GPTError(f"无法连接到 {base_url}（图片生成）", 502)
    except httpx.TimeoutException:
        raise GPTError("图片生成超时（300s）", 504)
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        detail = ""
        code = ""
        try:
            body = e.response.json()
            error = body.get("error", {}) if isinstance(body, dict) else {}
            if isinstance(error, dict):
                detail = str(error.get("message") or "")[:300]
                code = str(error.get("code") or error.get("type") or "").lower()
        except Exception:
            detail = (e.response.text or "")[:300]
        if status == 429:
            retry_after = e.response.headers.get("retry-after", "")
            wait_hint = f"建议 {retry_after} 秒后重试" if retry_after.isdigit() else "请稍后再试，避免连续提交"
            if "quota" in code or "billing" in code or "insufficient" in code:
                message = "图片服务额度/计费余额不足（429），请检查图片服务账户额度或切换已可用的图片模型"
            else:
                message = f"图片服务触发请求限流（429），{wait_hint}；若持续出现，请检查供应商速率限制"
            if detail: message += f"。接口说明：{detail}"
            raise GPTError(message, status)
        raise GPTError(f"图片接口请求失败（HTTP {status}）" + (f"：{detail}" if detail else "，请检查模型、额度和接口配置"), status)
    except Exception as e:
        raise GPTError(f"图片生成异常: {type(e).__name__}: {e}", 502)


async def generate_character(db: Session, project_id: int, char_id: int,
                            description: str, regenerate: bool = False,
                            model: str | None = None) -> str:
    """角色形象图（竖版 3:4）"""
    from models.drama import Character
    c = db.query(Character).filter_by(id=char_id, project_id=project_id).first()
    if not c:
        raise GPTError("角色不存在", 404)

    prompt = build_asset_prompt("character", c, "base")
    # 重新生成时若已有基础图，作为参考保持风格一致
    ref = None
    if regenerate and c.base_image_url:
        ref = _resolve_local_image(c.base_image_url)

    url = await _generate_image(db, prompt, project_id, "characters",
                                size="1024x1536", reference_image=ref,
                                model=model)
    if not c.base_image_url: c.base_image_url = url
    extra = list(c.extra_images or [])
    extra.append(url)
    c.extra_images = extra[-20:]
    db.commit()
    return url


async def generate_scene(db: Session, project_id: int, scene_id: int,
                         description: str, regenerate: bool = False,
                         model: str | None = None) -> str:
    """场景图（横版 3:2）"""
    from models.drama import Scene
    s = db.query(Scene).filter_by(id=scene_id, project_id=project_id).first()
    if not s:
        raise GPTError("场景不存在", 404)

    prompt = build_asset_prompt("scene", s, "base")
    url = await _generate_image(db, prompt, project_id, "scenes", size="1536x1024",
                                model=model)
    if not s.image_url: s.image_url = url
    s.image_versions = [*(s.image_versions or []),url][-20:]
    db.commit()
    return url


async def generate_prop(db: Session, project_id: int, prop_id: int,
                        description: str, regenerate: bool = False,
                        model: str | None = None) -> str:
    """道具图（方形）"""
    from models.drama import Prop
    p = db.query(Prop).filter_by(id=prop_id, project_id=project_id).first()
    if not p:
        raise GPTError("道具不存在", 404)

    prompt = build_asset_prompt("prop", p, "base")
    url = await _generate_image(db, prompt, project_id, "props", size="1024x1024",
                                model=model)
    p.image_url = url
    db.commit()
    return url


def _resolve_local_image(rel_url: str):
    """把本项目或旧版 /storage 图片相对路径解析为本地字节。"""
    try:
        if not rel_url.startswith("/storage/"):
            return None
        rel = rel_url.removeprefix("/storage/").split("?", 1)[0]
        p = (STORAGE_DIR / rel).resolve()
        project_parts = p.relative_to(PROJECTS_DIR.resolve()).parts if p.is_relative_to(PROJECTS_DIR.resolve()) else ()
        allowed = p.is_relative_to(IMAGES_DIR.resolve()) or (
            len(project_parts) >= 3 and project_parts[0].isdigit() and project_parts[1] == "images"
        )
        if allowed and p.is_file():
            return p.read_bytes()
    except Exception:
        pass
    return None

async def generate_character_reference(db: Session, project_id: int, char_id: int,
                                       variant: str, model: str | None = None) -> str:
    from models.drama import Character
    c = db.query(Character).filter_by(id=char_id, project_id=project_id).first()
    if not c: raise GPTError("角色不存在", 404)
    prompt = build_asset_prompt("character", c, variant)
    references = dict(c.reference_images or {})
    source = c.base_image_url or references.get("front")
    # 单人物主参考锁定身份；拼图只作为展示，不作为视频主体参考。
    ref = _resolve_local_image(source) if source else None
    size = "1536x1024" if variant in ("turnaround", "expressions", "detail_sheet") else "1024x1536"
    url = await _generate_image(db, prompt, project_id, "characters", size=size, reference_image=ref, model=model)
    references[variant] = url
    c.reference_images = references
    if variant == "front" and not c.base_image_url: c.base_image_url = url
    db.commit()
    return url

async def generate_keyframe(db: Session, project_id: int, shot_id: int, model: str | None = None) -> str:
    from models.drama import Shot, Character, Scene, Outline
    from services.director_design import direction_prompt
    shot = db.query(Shot).filter_by(id=shot_id, project_id=project_id).first()
    if not shot: raise GPTError("分镜不存在", 404)
    if shot.video_status == "processing": raise GPTError("视频生成中，暂时不能更改关键帧", 409)
    if not shot.keyframe_prompt: raise GPTError("请先填写关键帧提示词或深化分析", 400)
    chars = db.query(Character).filter(Character.project_id == project_id, Character.name.in_(shot.character_names or [])).all()
    scene = db.query(Scene).filter_by(project_id=project_id, name=shot.scene_name).first()
    outline = db.query(Outline).filter_by(project_id=project_id).first()
    identities = "\n".join(f"{c.name}：{c.description}；{(c.design or {}).get('identity','')}；{(c.design or {}).get('wardrobe','')}" for c in chars)
    source = next((c.base_image_url or (c.reference_images or {}).get("front") for c in chars
                   if c.base_image_url or (c.reference_images or {}).get("front")), None)
    source = source or (scene.image_url if scene else None)
    from services.generation_design import effective_options, reference_items
    from models.drama import Project
    project=db.get(Project,project_id)
    unknown_characters=set(shot.character_names or [])-{c.name for c in project.characters}
    unknown_scene=shot.scene_name and not any(s.name==shot.scene_name for s in project.scenes)
    if unknown_characters or unknown_scene:
        absent='、'.join([*sorted(unknown_characters),*([shot.scene_name] if unknown_scene else [])])
        raise GPTError('分镜中的角色或场景没有对应参考资产：'+absent,400)
    bound=reference_items(db,project,shot,effective_options(project,shot))
    missing=[item['name'] for item in bound if not item['url']]
    if missing:
        raise GPTError('请先生成本镜头的角色与场景参考图：'+'、'.join(missing),400)
    references=[];reference_roles=[]
    for item in bound:
        image=_resolve_local_image(item['url']) if item['url'] else None
        if image:
            references.append(image)
            reference_roles.append(f"参考图{len(references)} = {item['name']}（{item['kind']}），保持相应外貌、服装、空间或道具一致")
    prompt = f"生成单一分镜开场关键帧，不是拼图、不是多格漫画。\n{shot.keyframe_prompt}\n{direction_prompt(shot.direction, still=True)}\n人物设定：{identities}\n场景：{scene.description if scene else shot.scene_name}\n全片视觉：{outline.video_style if outline else ''}\n保持人物面容和服饰一致，无字幕、文字、水印。"
    from services.generation_design import effective_options, format_prompt
    from models.drama import Project
    ratio = effective_options(db.get(Project,project_id),shot)["aspect_ratio"]
    prompt = format_prompt(prompt,ratio) + "\n" + "\n".join(reference_roles)
    size = "1024x1024" if ratio=="1:1" else "1024x1536" if ratio in ("9:16", "3:4") else "1536x1024"
    shot.keyframe_url = await _generate_image(db, prompt, project_id, "keyframes", size=size,
                                              reference_image=_resolve_local_image(source) if source else None, model=model,
                                              reference_images=references[:8], aspect_ratio=ratio)
    db.commit()
    return shot.keyframe_url
