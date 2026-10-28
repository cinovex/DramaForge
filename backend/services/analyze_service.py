"""剧本 → 结构化大纲（调 GPT，写入库）"""
import json
from sqlalchemy.orm import Session
from models.drama import (
    Project, Outline, Character, Scene, Prop, Shot
)
from services import gpt_service
from services.analysisProgress import updateAnalysisProgress
from services.director_design import CharacterDesign, SceneDesign, ShotDirection, validate_character, validate_direction, fit_timeline, dramaticPerformanceRules
from services.image_prompt_skill import IMAGE_PROMPT_SKILL
from pydantic import ValidationError

SYSTEM_PROMPT = """你是专业短剧编剧兼分镜师。请把用户剧本解析为严格 JSON，
不要输出 JSON 以外的任何内容。JSON 结构如下：
{
  "title": "剧名",
  "synopsis": "剧情概要（150字内）",
  "story_analysis": {
    "logline": "一句话故事核",
    "central_conflict": "主角目标、主要阻碍和失败代价",
    "protagonist_arc": "主角在本剧中的选择与变化；原文未体现时写明未交代",
    "story_beats": [{"stage": "剧情阶段", "event": "原文事件", "dramatic_function": "该事件在故事中的作用"}],
    "themes": ["由原文支持的主题"],
    "continuity_risks": ["跨场/跨集需要核对的事实或设定冲突"]
  },
  "video_style": "视频风格（色调/摄影/氛围，用于统一全片）",
  "aspect_ratio": "9:16 或 16:9（默认9:16竖屏）",
  "story_type": "故事类型（如科幻悬疑/古风甜宠/都市逆袭）",
  "target_audience": "目标受众",
  "characters": [{"name": "角色名", "description": "外貌/性格/服装（用于生成形象图，需具体）"}],
  "scenes": [{"name": "场景名", "description": "场景视觉描述（用于生成场景图，需具体）"}],
  "props": [{"name": "道具名", "description": "道具稳定外观、材质、颜色、重要状态及可用于主参考图的视觉描述"}],
  "episodes": [{
    "ep_no": 1,
    "title": "集名",
    "summary": "本集事件与关系推进",
    "conflict": "本集核心冲突",
    "turning_point": "本集关键转折；原文没有则说明",
    "ending_hook": "本集原文结尾钩子；没有则说明",
    "estimated_duration": 60,
    "duration_basis": "依据对白、动作与停顿估算",
    "shots": [{
      "shot_no": 1,
      "title": "镜头标题",
      "duration": 7.0,
      "scene": "对应场景名",
      "characters": ["角色名"],
      "prompt": "视频生成提示词草稿；保留原文台词与事件，不压缩剧情"
    }]
  }]
}
注意：严格按剧本事实分析，不增删事件、不改台词、不替用户补结局；把导演建议与原文事实分开。story_beats按剧本结构选择3–8个有效节点，不强套三幕式，不为填字段虚构转折、主题或悬念。剧本含多集时逐集给出提要；未标集数时按场景/情节自然拆分，无法可靠拆分就保留为一集。角色、场景和道具使用稳定且唯一的名称，分镜引用必须与资产名称完全一致。每个镜头是一段连续拍摄，时长为4–12秒整数，单镜头不切换机位；按对白自然语速和动作停顿切镜，台词必须完整落在对应镜头中。"""


def _parse_json(raw: str) -> dict:
    """GPT 有时会在 JSON 外包裹说明，做鲁棒解析"""
    raw = raw.strip()
    # 去掉可能的 ```json ``` 包裹
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    try:
        parsed=json.loads(raw)
        # 某些兼容模型会把完整 JSON 再编码为一个 JSON 字符串。
        for _ in range(2):
            if not isinstance(parsed,str): break
            parsed=json.loads(parsed)
        return parsed
    except (ValueError, TypeError, AttributeError, ValidationError):
        # 尝试提取第一个 { 到最后一个 }
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            return json.loads(raw[start:end + 1])
        raise


ANALYSIS_FLOW_RULES = """
把一次“分析剧本”当作完整制作分析任务的入口：先提取故事结构与分集摘要，再由同一后台任务自动补全角色/场景连续性、资产提示词、逐镜导演设计、首帧提示词和视频提示词。不要要求用户重新点一次深化分析，也不要在分析阶段调用图片或视频生成。
分析结果须保留原文事件顺序与台词；故事节拍、类型判断、集尾钩子和时长均须有输入依据。每集预计时长依据写入 duration_basis；没有足够依据时明确标为估算。角色/场景/道具名称必须稳定，镜头引用只能使用已提取的真实资产名称。逐镜头写成可独立制作的连续拍摄单位，并让静态首帧提示与视频动作提示各自适配用途，不互相混写。
"""

BASE_SYSTEM_PROMPT = SYSTEM_PROMPT + "\n" + IMAGE_PROMPT_SKILL + "\n" + ANALYSIS_FLOW_RULES + dramaticPerformanceRules


async def analyze_project(db: Session, project_id: int, model: str | None = None, already_started: bool = False) -> dict:
    import hashlib
    from services.analysisTasks import splitAnalysisScript, checkAnalysisPause, readAnalysisState
    p = db.get(Project, project_id)
    if not p or not (p.script_text or "").strip():
        raise gpt_service.GPTError("项目不存在或剧本为空", 400)
    fingerprint = hashlib.sha256(json.dumps({"script": p.script_text, "ratio": (p.generation_settings or {}).get("aspect_ratio"), "style": (p.generation_settings or {}).get("creativePreferences")}, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    state = readAnalysisState(db, p)
    legacyFingerprint = hashlib.sha256(json.dumps({"script": p.script_text, "ratio": (p.generation_settings or {}).get("aspect_ratio")}, ensure_ascii=False).encode()).hexdigest()
    if state.get("structureFingerprint") == legacyFingerprint and not (p.generation_settings or {}).get("creativePreferences"):
        state["structureFingerprint"] = fingerprint
        p.analysis_state = state
        db.commit()
    if state.get("structureFingerprint") != fingerprint:
        if db.query(Shot).filter_by(project_id=project_id).first():
            raise gpt_service.GPTError("剧本、比例或风格已修改，不能复用旧分析进度；现有成果保留", 409)
        plan = splitAnalysisScript(p.script_text)
        p.analysis_state = {**state, "structureFingerprint": fingerprint, "structurePlan": plan, "structureNext": 0}
        db.commit()
    else:
        plan = state.get("structurePlan") or splitAnalysisScript(p.script_text)
    result = {}
    for index, segment in enumerate(plan):
        checkAnalysisPause(db, p)
        if index < (p.analysis_state or {}).get("structureNext", 0):
            continue
        result = await analyzeSegment(db, project_id, model, segment, index, len(plan))
    return result


async def analyzeSegment(db: Session, project_id: int, model, segment, segmentIndex, segmentTotal) -> dict:
    from services.analysisTasks import recordAnalysisUnit, readAnalysisState
    p = db.query(Project).get(project_id)
    if not p:
        raise gpt_service.GPTError("项目不存在", 404)
    if not p.script_text:
        raise gpt_service.GPTError("该项目没有剧本内容，无法解析", 400)

    p.status = "analyzing"
    unitKey = f"structure-{segmentIndex}"
    recordAnalysisUnit(db, p, unitKey, f"第 {segment['episode']} 集 · 剧本段 {segmentIndex+1}/{segmentTotal}", "running")
    db.commit()

    phase = "请求剧本结构分析"
    raw = ""
    try:
        updateAnalysisProgress(db, p, f"正在分析剧本段 {segmentIndex+1}/{segmentTotal} · 第 {segment['episode']} 集，已完成部分已保存", "structure", segmentIndex, segmentTotal)
        known = {"characters": [c.name for c in p.characters], "scenes": [s.name for s in p.scenes], "props": [pr.name for pr in p.props]}
        selectedStyle = ((p.generation_settings or {}).get("creativePreferences") or {}).get("stylePrompt", "")
        raw = await gpt_service.chat_completion(
            db, BASE_SYSTEM_PROMPT + f"\n用户选定输出画幅：{(p.generation_settings or {}).get('aspect_ratio','9:16')}。用户选定视觉风格：{selectedStyle or '根据原文确定'}。本次只分析第 {segment['episode']} 集的一段原文，episodes 必须只返回一个对象；不要补写片段前后剧情。已有资产仅供复用，并非允许使用的完整清单：{json.dumps(known, ensure_ascii=False)}。本段出现的新角色、场景、道具必须追加到对应资产数组，不能因为未登记就省略。未在本段出现的既有资产不要返回。分镜的 scene 必须完全等于已有或本次新增场景的 name，不得添加“未登记”等说明性括号。对白必须完整，不压缩剧情，按自然语速安排4–12秒整数镜头。",
            segment["text"],
            stage="script", model=model, json_mode=True, max_tokens=128000,
        )
        phase = "解析模型返回的剧本结构"
        updateAnalysisProgress(db, p, "模型已返回，正在读取故事与分集结构", "structure")
        data = _parse_json(raw)
        if not isinstance(data, dict) or not data.get("episodes"):
            raise ValueError("模型返回了空对象或缺少 episodes 分镜列表")
        if len(data["episodes"]) != 1:
            raise ValueError("本段必须返回一个分集对象，避免改变原剧本集序")
        for field in ("characters", "scenes", "props"):
            items = data.get(field, [])
            if not isinstance(items, list) or any(not isinstance(item, dict) or not isinstance(item.get("name"), str) or not item["name"].strip() for item in items):
                raise ValueError(f"{field} 资产名称不完整")
            if len({item["name"].strip() for item in items}) != len(items):
                raise ValueError(f"{field} 资产名称重复")
            for item in items: item["name"] = item["name"].strip()
        characterNames = set(known["characters"]) | {item["name"] for item in data.get("characters", [])}
        sceneNames = set(known["scenes"]) | {item["name"] for item in data.get("scenes", [])}
        unresolvedScenes = {shot.get("scene") for episode in data["episodes"] for shot in episode.get("shots", []) if isinstance(shot, dict) and isinstance(shot.get("scene"), str) and shot["scene"] and shot["scene"] not in sceneNames}
        if unresolvedScenes:
            phase = "补全本段新场景及引用"
            updateAnalysisProgress(db, p, f"正在核对 {len(unresolvedScenes)} 个新增场景引用，已完成分镜保持不变", "validation")
            sceneRepairRaw = await gpt_service.chat_completion(
                db,
                "你负责校对剧本场景登记。根据原文核实未登记引用，只返回严格 JSON："
                '{"scenes":[{"name":"场景名","description":"原文支持的地点与视觉事实；未交代的细节不得编造"}],"scene_references":{"原引用名":"校正后的场景名"}}。'
                "已有地点沿用原名；新地点必须在 scenes 登记。去掉场景名中的说明性备注。不同空间不能强行合并；无依据的地点不要猜测，不要补剧情。",
                json.dumps({"script": segment["text"], "existingScenes": known["scenes"], "declaredScenes": data.get("scenes", []), "unregisteredReferences": sorted(unresolvedScenes)}, ensure_ascii=False),
                stage="script", model=model, json_mode=True, max_tokens=8192,
            )
            sceneRepair = _parse_json(sceneRepairRaw)
            if not isinstance(sceneRepair, dict) or not isinstance(sceneRepair.get("scenes", []), list) or not isinstance(sceneRepair.get("scene_references", {}), dict):
                raise ValueError("新增场景校对结果格式不正确")
            for scene in sceneRepair.get("scenes", []):
                if not isinstance(scene, dict) or not isinstance(scene.get("name"), str) or not scene["name"].strip() or not isinstance(scene.get("description"), str) or not scene["description"].strip():
                    raise ValueError("新增场景缺少名称或原文描述")
                scene["name"] = scene["name"].strip()
                if scene["name"] not in sceneNames:
                    data.setdefault("scenes", []).append(scene)
                    sceneNames.add(scene["name"])
            references = sceneRepair.get("scene_references", {})
            for original in unresolvedScenes:
                destination = references.get(original, original)
                if not isinstance(destination, str) or destination not in sceneNames:
                    raise ValueError(f"场景“{original}”仍未登记，已保存分镜保留")
            for episode in data["episodes"]:
                for shot in episode.get("shots", []):
                    if isinstance(shot, dict) and shot.get("scene") in unresolvedScenes:
                        shot["scene"] = references.get(shot["scene"], shot["scene"])
        phase = "校验角色、场景和分镜字段"
        updateAnalysisProgress(db, p, f"正在校验 {len(data['episodes'])} 集剧本、角色、场景和分镜", "validation")
        for c in data.get("characters", []):
            c["design"] = CharacterDesign.model_validate(c.get("design", {})).model_dump()
            if c.get("design") and c["design"].get("turnaround_prompt"): validate_character(c["design"])
        for scene in data.get("scenes", []):
            scene["design"] = SceneDesign.model_validate(scene.get("design", {})).model_dump()
        for ep in data["episodes"]:
            if not ep.get("shots"): raise ValueError("分镜为空")
            normalized=[]
            for shot in ep["shots"]:
                if not isinstance(shot, dict) or not isinstance(shot.get("prompt"), str) or not shot["prompt"].strip():
                    raise ValueError("分镜提示词不完整")
                if not isinstance(shot.get("characters", []), list) or any(name not in characterNames for name in shot.get("characters", [])):
                    raise ValueError("分镜引用了未登记角色")
                if shot.get("scene") and shot["scene"] not in sceneNames:
                    raise ValueError(f"分镜引用了未登记场景：{shot['scene']}")
                duration=round(float(shot.get("duration",7)))
                if duration < 4 or duration > 120: raise ValueError("无效时长")
                parts=max(1,(duration+11)//12)
                lengths=[duration//parts + (1 if i<duration%parts else 0) for i in range(parts)]
                if min(lengths)<4: raise ValueError("镜头时长无法拆分到4–12秒")
                for index,length in enumerate(lengths):
                    part=dict(shot)
                    part["duration"]=length
                    if parts>1:
                        part["title"]=f"{shot.get('title','镜头')} · {index+1}/{parts}"
                        part["prompt"]=f"连续动作第{index+1}/{parts}段：{shot.get('prompt','')}"
                    normalized.append(part)
            ep["shots"]=normalized
            for shot_no,shot in enumerate(ep["shots"],1):
                shot["shot_no"]=shot_no
                shot["direction"] = ShotDirection.model_validate(shot.get("direction", {})).model_dump()
                duration = float(shot.get("duration", 7))
                shot["direction"]["timeline"] = fit_timeline(shot["direction"]["timeline"],duration) if shot["direction"].get("timeline") else ""
                if shot["direction"].get("lighting"): validate_direction(shot["direction"], duration)
    except gpt_service.GPTError:
        raise
    except (ValueError, TypeError, AttributeError, ValidationError) as error:
        if isinstance(error, json.JSONDecodeError):
            reason = "JSON 不完整，可能是模型输出被截断" if error.pos >= max(0, len(raw)-2) else f"JSON 格式错误（第 {error.lineno} 行）"
        elif isinstance(error, ValidationError):
            first=error.errors()[0] if error.errors() else {}
            reason=f"字段 {'.'.join(str(x) for x in first.get('loc',[]))} 不符合要求"
        else:
            reason=str(error) or type(error).__name__
        from config import BASE_DIR
        debug_dir=BASE_DIR/"work";debug_dir.mkdir(exist_ok=True)
        (debug_dir/f"analysis-debug-{project_id}.json").write_text(json.dumps({
            "phase":phase,"error":reason,"response":raw},ensure_ascii=False),encoding="utf-8")
        raise gpt_service.GPTError(f"{phase}失败：{reason}。现有媒体不会被删除",502) from error

    # ---- 写大纲 ----
    outline = db.query(Outline).filter_by(project_id=project_id).first()
    if not outline:
        outline = Outline(project_id=project_id)
        db.add(outline)
    outline.title = outline.title or data.get("title", p.name)
    outline.synopsis = "\n".join(filter(None, [outline.synopsis, data.get("synopsis", "")]))
    outline.video_style = selectedStyle or outline.video_style or data.get("video_style", "")
    outline.aspect_ratio = (p.generation_settings or {}).get("aspect_ratio") or data.get("aspect_ratio", "9:16")
    outline.story_type = data.get("story_type", "")
    outline.target_audience = data.get("target_audience", "")
    existingData = dict(outline.raw_data or {})
    episodes = [dict(ep) for ep in existingData.get("episodes", [])]
    incomingEpisode = {**data["episodes"][0], "ep_no": segment["episode"]}
    existingEpisode = next((ep for ep in episodes if ep.get("ep_no") == segment["episode"]), None)
    shotOffset = len(existingEpisode.get("shots", [])) if existingEpisode else 0
    for index, shot in enumerate(incomingEpisode["shots"], shotOffset+1): shot["shot_no"] = index
    if existingEpisode:
        existingEpisode["shots"] = [*existingEpisode.get("shots", []), *incomingEpisode["shots"]]
        existingEpisode["summary"] = "\n".join(filter(None, [existingEpisode.get("summary"), incomingEpisode.get("summary")]))
        existingEpisode["ending_hook"] = incomingEpisode.get("ending_hook", "")
        existingEpisode["estimated_duration"] = sum(sh["duration"] for sh in existingEpisode["shots"])
    else:
        episodes.append(incomingEpisode)
    merged = {**data, **existingData, "episodes": episodes,
              "analysis_segments": [*existingData.get("analysis_segments", []), {"index": segmentIndex, "episode": segment["episode"], "story_analysis": data.get("story_analysis", {})}]}
    for field in ("characters", "scenes", "props"):
        merged[field] = list({item["name"]: item for item in [*data.get(field, []), *existingData.get(field, [])]}.values())
    outline.raw_data = merged

    # ---- 角色 ----
    char_count = 0
    for c in data.get("characters", []):
        if db.query(Character).filter_by(project_id=project_id, name=c["name"]).first(): continue
        db.add(Character(project_id=project_id,
                         name=c.get("name", ""),
                         description=c.get("description", ""), design=c["design"]))
        char_count += 1

    # ---- 场景 ----
    scene_count = 0
    for s in data.get("scenes", []):
        if db.query(Scene).filter_by(project_id=project_id, name=s["name"]).first(): continue
        db.add(Scene(project_id=project_id,
                     name=s.get("name", ""),
                     description=s.get("description", ""), design=s["design"]))
        scene_count += 1

    # ---- 道具 ----
    prop_count = 0
    for pr in data.get("props", []):
        if db.query(Prop).filter_by(project_id=project_id, name=pr["name"]).first(): continue
        db.add(Prop(project_id=project_id,
                    name=pr.get("name", ""),
                    description=pr.get("description", "")))
        prop_count += 1

    # ---- 分镜 ----
    shot_count = 0
    for ep in data.get("episodes", []):
        ep_no = segment["episode"]
        for sh in ep.get("shots", []):
            db.add(Shot(
                project_id=project_id,
                episode_no=ep_no,
                shot_no=sh.get("shot_no", shot_count + 1),
                title=sh.get("title", ""),
                duration=float(sh.get("duration", 7.0)),
                scene_name=sh.get("scene", ""),
                character_names=sh.get("characters", []),
                prompt=sh.get("prompt", ""),
                direction=sh["direction"],
                keyframe_prompt=sh.get("keyframe_prompt", ""),
                video_status="pending",
            ))
            shot_count += 1

    recordAnalysisUnit(db, p, unitKey, f"第 {segment['episode']} 集 · 剧本段 {segmentIndex+1}/{segmentTotal}", "done")
    # recordAnalysisUnit reloads state; advance the checkpoint in the same result transaction.
    p.analysis_state = {**p.analysis_state, "structureNext": segmentIndex+1}
    p.status = "analyzing"
    db.commit()
    counts = {"episodes": len(episodes), "characters": db.query(Character).filter_by(project_id=project_id).count(),
              "scenes": db.query(Scene).filter_by(project_id=project_id).count(), "props": db.query(Prop).filter_by(project_id=project_id).count(),
              "shots": db.query(Shot).filter_by(project_id=project_id).count()}
    updateAnalysisProgress(db, p, f"剧本段已保存 {segmentIndex+1}/{segmentTotal}，已提取 {counts['shots']} 个分镜", "structure", segmentIndex+1, segmentTotal, counts)

    return {
        "project_id": project_id,
        "title": outline.title,
        "characters": char_count,
        "scenes": scene_count,
        "props": prop_count,
        "shots": shot_count,
        "status": "ready",
    }
