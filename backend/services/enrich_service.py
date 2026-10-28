"""为已有作品补充导演设计，保留资产 ID 和生成结果。"""
import json
import hashlib
from pydantic import BaseModel, ValidationError, model_validator
from sqlalchemy.orm import Session
from models.drama import Project, Character, Scene, Prop, Shot
from services.analysisProgress import updateAnalysisProgress
from services import gpt_service
from services.analysisTasks import checkAnalysisPause, readAnalysisState, recordAnalysisUnit
from services.analyze_service import _parse_json
from services.director_design import DIRECTOR_RULES, schema_hint, CharacterDesign, SceneDesign, ShotDirection, validate_direction, validate_character, fit_timeline

class CharacterResult(BaseModel):
    id: int
    design: CharacterDesign
class SceneResult(BaseModel):
    id: int
    design: SceneDesign
class ShotResult(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def normalize_shot(cls, value):
        if not isinstance(value, dict): return value
        data = dict(value)
        nested = data.get("design", data)
        if isinstance(nested, dict):
            inner = nested.get("shot_direction", nested)
            if isinstance(inner, dict):
                if inner.get("id") is not None and data.get("id") != inner["id"]:
                    raise ValueError("嵌套镜头ID不一致")
                for key in ("direction", "keyframe_prompt", "prompt"):
                    if key not in data and key in inner: data[key] = inner[key]
                if "direction" not in data and "shot_size" in inner:
                    data["direction"] = {key: value for key, value in inner.items()
                                         if key in ShotDirection.model_fields}
        return data
    id: int
    direction: ShotDirection
    keyframe_prompt: str
    prompt: str
class DesignResult(BaseModel):
    characters: list[CharacterResult] = []
    scenes: list[SceneResult] = []
    shots: list[ShotResult] = []

def _asset_numeric_id(value):
    """Accept integer IDs and their JSON string form; reject booleans and guesses."""
    if isinstance(value, bool): return None
    if isinstance(value, int): return value
    if isinstance(value, str) and value.strip().isdigit(): return int(value.strip())
    return None

def _asset_design_kind(item):
    if not isinstance(item, dict): return None
    design = item.get("design", item)
    if not isinstance(design, dict): return None
    character_keys = {"identity", "wardrobe", "views", "turnaround_prompt", "expressions", "expression_sheet_prompt"}
    scene_keys = {"geography", "lighting", "palette", "atmosphere", "continuity", "reference_prompt"}
    has_character = bool(character_keys.intersection(design))
    has_scene = bool(scene_keys.intersection(design))
    if has_character and not has_scene: return "character"
    if has_scene and not has_character: return "scene"
    return None

def _normalize_asset_payload(payload, requested_chars, requested_scenes):
    """Repair category swaps and string IDs without ever inventing/merging asset IDs."""
    char_ids = {item["id"] for item in requested_chars}
    scene_ids = {item["id"] for item in requested_scenes}
    normalized = {"characters": [], "scenes": [], "shots": []}
    seen = {"character": set(), "scene": set()}
    for source_kind in ("character", "scene"):
        field = "characters" if source_kind == "character" else "scenes"
        for item in payload.get(field, []) if isinstance(payload.get(field), list) else []:
            if not isinstance(item, dict): continue
            asset_id = _asset_numeric_id(item.get("id"))
            if asset_id is None: continue
            char_match = asset_id in char_ids
            scene_match = asset_id in scene_ids
            shape_kind = _asset_design_kind(item)
            if char_match != scene_match:
                target_kind = "character" if char_match else "scene"
            elif char_match and scene_match and shape_kind:
                target_kind = shape_kind
            else:
                target_kind = source_kind
            target_ids = char_ids if target_kind == "character" else scene_ids
            if asset_id not in target_ids or asset_id in seen[target_kind]: continue
            item = dict(item)
            item["id"] = asset_id
            normalized["characters" if target_kind == "character" else "scenes"].append(item)
            seen[target_kind].add(asset_id)
    return normalized

async def enrich_project(db: Session, project_id: int, model: str | None = None, already_started: bool = False):
    project = db.get(Project, project_id)
    if not project: raise gpt_service.GPTError("项目不存在", 404)
    if project.status == "analyzing" and not already_started: raise gpt_service.GPTError("正在分析，请稍候", 409)
    shots = db.query(Shot).filter_by(project_id=project_id).order_by(Shot.episode_no, Shot.shot_no).all()
    if not shots: raise gpt_service.GPTError("请先分析剧本生成分镜", 400)
    if any(sh.video_status == "processing" for sh in shots):
        raise gpt_service.GPTError("请等待视频生成结束后再深化分析", 409)
    old_status = (project.analysis_state or {}).get("previous_status", "ready") if already_started else project.status
    project.status = "analyzing"
    db.commit()
    try:
        chars = db.query(Character).filter_by(project_id=project_id).all()
        scenes = db.query(Scene).filter_by(project_id=project_id).all()
        char_input = [{"id": c.id, "name": c.name, "description": c.description} for c in chars]
        scene_input = [{"id": s.id, "name": s.name, "description": s.description} for s in scenes]
        system = DIRECTOR_RULES + f"\n保持项目既有全片视觉风格：{project.outline.video_style if project.outline else '依照剧本'}；画幅：{project.outline.aspect_ratio if project.outline else '9:16'}。\n" + schema_hint() + "\n输出 {characters:[{id,design}], scenes:[{id,design}], shots:[{id,direction,keyframe_prompt,prompt}]}。只能使用输入ID，不新增、合并或删除分镜。"
        asset_schema = {k:v for k,v in json.loads(schema_hint()).items() if k != "shot_direction"}
        asset_system = DIRECTOR_RULES.split("镜头：",1)[0] + "\n本次只分析输入的角色与场景，不分析镜头，不输出shots字段。严格输出 {characters:[{id,design}],scenes:[{id,design}]}。每个ID必须与输入完全一致。\n" + json.dumps(asset_schema,ensure_ascii=False)
        # 资产独立分析，镜头按小批次分析，减少长输出被截断。
        source_signature = hashlib.sha256(json.dumps({
            "checkpointVersion": 3,
            "script": project.script_text,
            "visual": [project.outline.video_style if project.outline else "", project.outline.aspect_ratio if project.outline else ""],
            "cast": char_input,
            "scenes": scene_input,
            "shots": [(sh.id, sh.episode_no, sh.shot_no, sh.title, sh.duration, sh.scene_name,
                       sh.character_names) for sh in shots],
        }, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        state = project.analysis_state or {}
        staged = dict(state.get("staged", {})) if state.get("fingerprint") == source_signature else {}
        if state.get("fingerprint") == source_signature:
            for key, cachedResult in list(staged.items()):
                changed = any(db.get(Character, item["id"]).design != item["design"] for item in cachedResult.get("characters", []))
                changed |= any(db.get(Scene, item["id"]).design != item["design"] for item in cachedResult.get("scenes", []))
                changed |= any(any(getattr(db.get(Shot, item["id"]), field) != item[field] for field in ("direction", "prompt", "keyframe_prompt")) for item in cachedResult.get("shots", []))
                if changed: staged.pop(key)
        def checkpoint(key, result):
            recordAnalysisUnit(db, project, key, unitLabel, "done")
            staged[key] = result.model_dump()
            project.analysis_state = {**(project.analysis_state or {}), "fingerprint": source_signature, "staged": dict(staged)}
            for c in result.characters:
                db.get(Character, c.id).design = c.design.model_dump()
            for s in result.scenes:
                db.get(Scene, s.id).design = s.design.model_dump()
            for sh in result.shots:
                target = db.get(Shot, sh.id)
                target.direction = sh.direction.model_dump()
                target.keyframe_prompt = sh.keyframe_prompt
                target.prompt = sh.prompt
            db.commit()
        def progress(message, completed=0, total=0):
            if already_started:
                project.analysis_state = {**readAnalysisState(db, project), "progress": message,
                                          "phase": "design", "completed": completed, "total": total}
                db.commit()
        asset_batches = max(len(chars), len(scenes))
        total_batches = asset_batches + len(shots)
        updateAnalysisProgress(db, project, "正在准备角色、场景与分镜设计", "design", total=total_batches,
                               counts={"episodes": len({sh.episode_no for sh in shots}), "characters": len(chars),
                                       "scenes": len(scenes), "props": db.query(Prop).filter_by(project_id=project_id).count(), "shots": len(shots)})
        progress("分析角色多视图、表情与场景光线")
        for index in range(max(len(chars), len(scenes))):
            checkAnalysisPause(db, project)
            current_chars = chars[index:index+1]
            current_scenes = scenes[index:index+1]
            names = [f"角色 {c.name}" for c in current_chars] + [f"场景 {s.name}" for s in current_scenes]
            progress(f"正在生成{'、'.join(names)}的设计 · 资产批次 {index+1}/{asset_batches}", index, total_batches)
            cached = staged.get(f"assets-{index}")
            unitLabel = "、".join(names) + " · 文字设计"
            if not cached:
                recordAnalysisUnit(db, project, f"assets-{index}", unitLabel, "running")
                db.commit()
            raw = json.dumps(cached, ensure_ascii=False) if cached else await gpt_service.chat_completion(db, asset_system,
                json.dumps({"script": project.script_text,
                            "characters": char_input[index:index+1], "scenes": scene_input[index:index+1], "shots": []}, ensure_ascii=False),
                model=model, json_mode=True, max_tokens=6000)
            payload = _parse_json(raw)
            if not isinstance(payload,dict):
                raise ValueError('资产分析没有返回JSON对象')
            # 模型可能把场景放入 characters（或反之），或把 JSON 数字 ID 写成字符串。
            # 按请求资产 ID 及设计字段归类；绝不根据顺序猜测缺失 ID。
            payload = _normalize_asset_payload(payload, char_input[index:index+1], scene_input[index:index+1])
            expected_char_ids = {c.id for c in current_chars}
            expected_scene_ids = {s.id for s in current_scenes}
            got_char_ids = {_asset_numeric_id(c.get("id")) for c in payload["characters"]}
            got_scene_ids = {_asset_numeric_id(s.get("id")) for s in payload["scenes"]}
            if got_char_ids != expected_char_ids or got_scene_ids != expected_scene_ids:
                # 首次输出缺项时，只让模型修补缺失资产；已经正确生成的资产保留在内存中。
                missing_chars = [c for c in char_input[index:index+1] if c["id"] not in got_char_ids]
                missing_scenes = [s for s in scene_input[index:index+1] if s["id"] not in got_scene_ids]
                repair_system = asset_system + "\n修复输出规则：只返回本次输入中缺失的资产；characters 只放角色，scenes 只放场景；每项必须带输入给出的整数 id 和 design。不要返回其他ID、shots或解释。"
                repair_raw = await gpt_service.chat_completion(db, repair_system,
                    json.dumps({"script": project.script_text, "characters": missing_chars,
                                "scenes": missing_scenes, "shots": [],
                                "instruction": "只补齐上述缺失项，类别和ID必须完全正确。"}, ensure_ascii=False),
                    model=model, json_mode=True, max_tokens=4000)
                repair_payload = _parse_json(repair_raw)
                if isinstance(repair_payload, dict):
                    repaired = _normalize_asset_payload(repair_payload, missing_chars, missing_scenes)
                    payload["characters"].extend(repaired["characters"])
                    payload["scenes"].extend(repaired["scenes"])
            result = DesignResult.model_validate(payload)
            if {c.id for c in result.characters} != {c.id for c in current_chars} or {s.id for s in result.scenes} != {s.id for s in current_scenes} or result.shots:
                raise ValueError("资产ID不完整")
            if len(result.characters) != len(current_chars) or len(result.scenes) != len(current_scenes):
                raise ValueError("资产ID重复")
            for c in result.characters:
                validate_character(c.design.model_dump())
            checkpoint(f"assets-{index}", result)
            progress(f"角色与场景设计已完成 {index+1}/{asset_batches} 批", index+1, total_batches)
        for start in range(0, len(shots), 1):
            checkAnalysisPause(db, project)
            current_shot = shots[start]
            progress(f"正在生成第 {current_shot.episode_no} 集 · 镜头 {current_shot.shot_no} 的导演设计与提示词 · 分镜 {start+1}/{len(shots)}", asset_batches+start, total_batches)
            batch = shots[start:start+1]
            def describe(sh):
                return {"id": sh.id, "episode": sh.episode_no, "shot": sh.shot_no, "duration": sh.duration,
                        "title": sh.title, "scene": sh.scene_name, "characters": sh.character_names, "prompt": sh.prompt, "direction": sh.direction}
            cached = staged.get(f"shot-{start}")
            unitLabel = f"第 {current_shot.episode_no} 集 · 分镜 {current_shot.shot_no} 设计"
            if not cached:
                recordAnalysisUnit(db, project, f"shot-{start}", unitLabel, "running")
                db.commit()
            raw = json.dumps(cached, ensure_ascii=False) if cached else await gpt_service.chat_completion(db, system,
                json.dumps({"script": project.script_text, "cast": char_input, "locations": scene_input,
                            "characters": [], "scenes": [], "shots": [describe(sh) for sh in batch],
                            "adjacent_shots": [describe(sh) for sh in shots[max(0,start-1):start+4] if sh.episode_no == current_shot.episode_no],
                            "instruction": "只返回 shots 中的ID；cast和locations只作上下文，characters和scenes返回空列表。重点读取 adjacent_shots：当前镜头必须从上一镜头结束的姿态、视线、道具位置与运动方向自然接入，并说明当前镜头结束后如何交给下一镜头；首尾镜头分别写开场和收束状态，不得无依据重置连续性。把交接写进 direction.continuity，并让视频 prompt 开场动作与承接点一致。"}, ensure_ascii=False),
                model=model, json_mode=True, max_tokens=5000)
            payload = _parse_json(raw)
            requested_ids = {sh.id for sh in batch}
            # 模型偶尔把相邻镜头也一并返回；只采纳本批请求的镜头。
            if not isinstance(payload,dict):
                raise ValueError('分镜分析没有返回JSON对象')
            payload["shots"] = [item for item in payload.get("shots", []) if isinstance(item, dict) and item.get("id") in requested_ids] if isinstance(payload.get("shots"), list) else []
            payload["characters"] = []
            payload["scenes"] = []
            result = DesignResult.model_validate(payload)
            if {sh.id for sh in result.shots} != {sh.id for sh in batch} or len(result.shots) != len(batch) or result.characters or result.scenes:
                raise ValueError("镜头ID不完整")
            if any(not sh.direction.lighting or not sh.direction.performance or not sh.direction.timeline or not sh.keyframe_prompt for sh in result.shots):
                raise ValueError("导演分析不完整")
            for sh in result.shots:
                current = next(s for s in batch if s.id == sh.id)
                sh.direction.timeline = fit_timeline(sh.direction.timeline, current.duration)
                anatomy = ("眼睑", "眉", "鼻翼", "嘴角", "唇", "下颌", "泪", "眨眼", "eyelid", "brow", "nostril", "mouth", "lip", "jaw", "tear", "blink")
                is_wide = any(word in sh.direction.shot_size for word in ("全景", "远景"))
                if current.character_names and not is_wide and sum(word in sh.direction.performance.lower() for word in anatomy) < 2:
                    micro_raw = await gpt_service.chat_completion(db,
                        "你是演员表演指导，输出严格JSON {id:镜头ID,performance:中文表演描述}。按每个出场角色分别描述符合剧情的姿态、呼吸、视线和可见面部动作及变化顺序。每个角色至少描述眉/上或下眼睑/嘴角或嘴唇/下颌中的两处，避免只写微笑、悲伤、生气、眼神柔和。不要无故添加哭泣。远景优先身体动作，近景写符合本场冲突强度的表演，不能一律克制。完整保留输入 performance 已有的原文台词、说话者和听话者、语速、音量、重音、停顿及情绪递进；只补充可见动作，不删除或改写这些表演调度，不新增对白。",
                        json.dumps({"id": sh.id, "characters": current.character_names, "title": current.title,
                                    "shot_size": sh.direction.shot_size, "duration": current.duration,
                                    "timeline": sh.direction.timeline, "performance": sh.direction.performance, "action": sh.prompt},ensure_ascii=False),
                        model=model,json_mode=True,max_tokens=2000)
                    micro = _parse_json(micro_raw)
                    if not isinstance(micro, dict) or micro.get("id") != sh.id or not isinstance(micro.get("performance"), str):
                        raise ValueError("微表情分析ID或格式不符")
                    sh.direction.performance = micro["performance"]
                    # 可见面部细节属于质量检查；保留模型给出的表演分析，
                    # 不因措辞未包含固定关键词而废弃整个项目的有效结果。
                validate_direction(sh.direction.model_dump(), next(s.duration for s in batch if s.id == sh.id))
            checkpoint(f"shot-{start}", result)
            progress(f"分镜设计已完成 {start+1}/{len(shots)}", asset_batches+start+1, total_batches)
        progress("角色、场景和分镜设计已逐项保存", total_batches, total_batches)
        project.status = "done" if old_status == "done" else "ready"
        db.commit()
        return {"status": "ready", "characters": len(chars), "scenes": len(scenes), "shots": len(shots), "preserved": True}
    except Exception as error:
        from services.analysisTasks import analysisPaused
        if isinstance(error, analysisPaused):
            raise
        if not isinstance(error, gpt_service.GPTError):
            from config import BASE_DIR
            debug_dir = BASE_DIR / "work"
            debug_dir.mkdir(exist_ok=True)
            (debug_dir / f"analysis-debug-{project_id}.json").write_text(json.dumps({
                "error": str(error), "response": locals().get("raw", "")}, ensure_ascii=False), encoding="utf-8")
        db.rollback()
        db.refresh(project)
        if not already_started:
            project.status = old_status
            db.commit()
        if isinstance(error, gpt_service.GPTError): raise
        reason = "字段格式不符" if isinstance(error, ValidationError) else str(error)[:80]
        raise gpt_service.GPTError(f"深化分析结果不完整（{reason}），现有媒体保留，重试会跳过已完成批次", 502) from error
