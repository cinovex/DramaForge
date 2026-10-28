"""可编辑的导演分析与角色参考设计，统一供分析、图片和视频生成使用。"""
import json
from pydantic import BaseModel, Field, model_validator, field_validator
from services.image_prompt_skill import IMAGE_PROMPT_SKILL

class Expression(BaseModel):
    name: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    negative_prompt: str = ""

class CharacterDesign(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def normalize_views(cls, value):
        if not isinstance(value, dict): return value
        data = dict(value)
        raw_views = dict(data.get("views") or {})
        for key in ("turnaround_prompt", "expressions", "expression_sheet_prompt", "negative_prompt", "director_notes"):
            if key in raw_views and not data.get(key): data[key] = raw_views[key]
        data["views"] = {key: raw_views[key] for key in ("front", "side", "back", "three_quarter") if key in raw_views}
        return data
    identity: str = ""
    wardrobe: str = ""
    views: dict[str, str] = Field(default_factory=dict)
    turnaround_prompt: str = ""
    expressions: list[Expression] = Field(default_factory=list, max_length=12)
    expression_sheet_prompt: str = ""
    negative_prompt: str = ""
    director_notes: str = ""

class SceneDesign(BaseModel):
    geography: str = ""
    lighting: str = ""
    palette: str = ""
    atmosphere: str = ""
    continuity: str = ""
    reference_prompt: str = ""
    director_notes: str = ""

def readable_text(value):
    if value is None: return ""
    if isinstance(value, str): return value
    if isinstance(value, list): return "；".join(readable_text(v) for v in value)
    if isinstance(value, dict):
        start = value.get("start", value.get("start_time"))
        end = value.get("end", value.get("end_time"))
        if start is not None and end is not None:
            content = value.get("action", value.get("description", value.get("content", "")))
            return f"{start}–{end}秒：{readable_text(content)}"
        return "；".join(f"{k}：{readable_text(v)}" for k, v in value.items())
    return str(value)

class ShotDirection(BaseModel):
    @field_validator("*", mode="before")
    @classmethod
    def normalize_text(cls, value): return readable_text(value)
    shot_size: str = ""
    camera_height: str = ""
    camera_angle: str = ""
    lens: str = ""
    camera_movement: str = ""
    composition: str = ""
    blocking: str = ""
    lighting: str = ""
    atmosphere: str = ""
    performance: str = ""
    timeline: str = ""
    continuity: str = ""
    sound: str = ""
    negative_prompt: str = ""
    director_notes: str = ""

LABELS = {
    "shot_size": "景别", "camera_height": "机位高度", "camera_angle": "拍摄角度",
    "lens": "焦段与景深", "camera_movement": "运镜", "composition": "构图",
    "blocking": "站位与视线", "lighting": "灯光", "atmosphere": "环境与色调",
    "performance": "表演与微表情", "timeline": "动作时间线", "continuity": "镜头连续性",
    "sound": "声音", "negative_prompt": "避免", "director_notes": "导演建议",
}

def direction_prompt(direction: dict | None, *, still: bool = False) -> str:
    fields = dict(direction or {})
    if still:
        for key in ("timeline", "camera_movement", "sound"):
            fields.pop(key, None)
    return "\n".join(f"{LABELS[k]}：{v}" for k, v in fields.items()
                     if k in LABELS and k != "director_notes" and v)

dramaticPerformanceRules = """
短剧表演与节奏设计必须在分析时完成，不能只写事件或笼统情绪。所有导演设计服从原文人物动机、事件顺序与完整台词，不添加原文没有的对白、反转、证据、人物或结局；建议明确标注，不伪称事实。
台词表演：逐句保留原文，标明说话者、听话者、潜台词（推断标为建议）、相对语速、音量、重读词和有时长的停顿。结合剧情选择低声、正常、提高音量、爆发或收声，快慢强弱有动机、有对比；不能所有人物同一语调，也不能每句都喊或强加哭泣。没有对白就写无对白，不补台词。
情绪递进：依据原文给出本镜头起始情绪、触发点、具体表演变化和结束情绪；结合相邻镜头安排压抑、挑衅、爆发、沉默等反差，不给每个镜头套同一种曲线。听者的反应与说话者区分，动作、视线、呼吸和微表情服务冲突。
镜头节奏：全段按冲突变化分配快慢，羞辱或反转安排有依据的反应镜头，揭露前允许短暂停顿，冲突推进可以加快；不全程匀速、不堆砌慢动作。每个镜头仍为单一连续拍摄，切换景别或反应特写应在拆镜阶段另建镜头。时长要容纳台词、停顿和动作，长对白跨相邻镜头自然分句，不靠极速念白塞满。
声音设计：对白前景清晰，说明本镜头音量与语速变化、环境声、关键动作音及其进入/退出时机；配乐压低、渐起或短暂抽掉须有情绪依据。无依据不加音乐，不让配乐盖过台词；区分角色沉默与整条音轨静音，避免全片音量一致。
开场与钩子：识别原文开场的矛盾和集尾未决问题；在原顺序内强化观看重点，说明如何通过表演、构图、停顿落到该点。普通中间镜头只承接推进，不每镜强造悬念；原文没有钩子就明确没有，不捏造一句门外喊话或身份揭露。
衔接：上一镜头的动作、情绪强度、对白或声音尾音如何接入，结束时的姿态、道具、视线、声音落点如何交给下一镜头；不同集的镜头不得当作直接连续的前后镜头。
"""

DIRECTOR_RULES = """
你是导演、摄影指导和角色设定师，输出严格 JSON。控制篇幅：单个视角和表情提示词约80–120中文字符，每角色4个表情；普通摄影字段约30–80字符；performance、timeline、sound、continuity 按实际对白和动作写全，不受该字数限制，保持具体且可执行。分析必须逐个角色、逐个场景、逐个镜头完成。
禁止以“电影级”“高级感”“生气的表情”“悲伤”等笼统词代替具体指令。
剧本事实必须保留；未写明的焦段、光源、外貌等是导演设计，逐项写入 director_notes，注明“建议”，不得伪称剧本事实。
角色：固定面部比例、发型、体型、服装、颜色与识别点；views 必须含 front、side、back、three_quarter 四个独立完整图像提示词。
turnaround_prompt 是同一个角色四视图拼图的完整提示词，统一比例、服装和光线，不混入表情。
根据剧情给每个角色 4–6 个表情参考，含中性基准；每项以可见肌肉/生理变化描述：眉间、上/下眼睑、眼球视线、泪水、鼻翼、嘴角、唇部、下颌。
不得对所有角色强加泪水或颤抖；结合剧情、表情强度和镜头可见性。expression_sheet_prompt 为统一脸部近景表情宫格提示词。
场景：空间布局、入口出口、人物活动轴线、道具位置、时间天气、光源来源/方向/软硬/色温关系，reference_prompt 是无人物场景参考图提示词。
镜头：shot_size、camera_height、camera_angle、lens、camera_movement、composition、blocking、lighting、atmosphere、performance、timeline、continuity、sound、negative_prompt、director_notes 都须具体填写。
机位可用高度与相对位置，焦段注明全画幅等效。光线写主光/补光/轮廓光来源、方向、光质、相对明暗及色温，不空写“电影灯光”。
performance 按出场角色分别写姿态、呼吸、视线、可见微表情及先后变化；远景优先身体动作，特写才强调面部细节。
timeline 的分段覆盖该镜头 duration，按“0–2秒：…；2–5秒：…”，时间不能超过总时长，动作数量符合时长，开场与结束姿态清晰。
continuity 记录与前后镜头的动作/视线/轴线/衣着/道具位置衔接。每个镜头是一个连续拍摄单位，不在同一镜头内隐式切换多个机位。
逐镜头检查前后交接：读取 adjacent_shots 中前一镜头的结束动作/视线/道具状态和后一镜头的开场动作；continuity 明确写“承接上一镜头的落点”以及本镜头结束时人物姿态、视线、道具位置、运动方向如何交给下一镜头。首镜头写清开场状态，末镜头写清收束状态；相邻镜头不得无缘由重置人物、服装、空间轴线或手中物件。不要虚构上下文未提供的剧情事实。
keyframe_prompt 描述开场单一静态画面（构图、人物身份、瞬间表情、光源和道具），不写连续动作、音效或多格分镜。
prompt 是直接发给视频模型的完整执行提示词：除动作与运镜，还必须写入原文逐句台词的说话者/听话者、语速音量重音停顿、情绪起落、声音时机及前后衔接，与 direction 一致；不能把这些只留在 director_notes，也不能只写“按上述设计”。不限150字，避免重复堆砌风格词。performance 写表演和逐句台词调度；timeline 写到具体秒段并同步台词/停顿；sound 写声音层次与时机；导演建议和原文存在钩子时的呈现依据写在 director_notes。
""" + dramaticPerformanceRules + IMAGE_PROMPT_SKILL

def schema_hint() -> str:
    character = CharacterDesign().model_dump()
    character["views"] = {k: "独立完整提示词" for k in ("front", "side", "back", "three_quarter")}
    character["expressions"] = [{"name": "表情名", "prompt": "可见微表情提示词"}]
    return json.dumps({"character_design": character, "scene_design": SceneDesign().model_dump(),
                       "shot_direction": ShotDirection().model_dump()}, ensure_ascii=False)


def validate_direction(direction: dict, duration: float):
    """拒绝缺失摄影设计或超出镜头时长的时间线。"""
    import re
    required = ("shot_size", "camera_height", "camera_angle", "lens", "camera_movement",
                "composition", "blocking", "lighting", "performance", "timeline", "continuity", "sound")
    if any(not str(direction.get(key, "")).strip() for key in required):
        raise ValueError("导演分析字段不完整")
    timeline = direction["timeline"]
    segments = [(float(a), float(b)) for a, b in re.findall(
        r"(\d+(?:\.\d+)?)\s*(?:秒|s)?\s*[-–—~～至到]\s*(\d+(?:\.\d+)?)\s*(?:秒|s)", timeline)]
    if not segments or abs(segments[0][0]) > .05 or abs(segments[-1][1] - duration) > .1:
        raise ValueError("时间线必须覆盖镜头时长")
    previous = 0.0
    for start, end in segments:
        if abs(start - previous) > .1 or end <= start or end > duration + .1:
            raise ValueError("时间线分段重叠或超出时长")
        previous = end

def fit_timeline(timeline: str, duration: float) -> str:
    """将模型给出的相对节奏映射到实际镜头时长，保留每段动作。"""
    import re
    pattern = re.compile(r"(\d+(?:\.\d+)?)\s*(?:秒|s)?\s*[-–—~～至到]\s*(\d+(?:\.\d+)?)\s*(?:秒|s)")
    matches = list(pattern.finditer(timeline))
    if not matches:
        return f"0–{duration:g}秒：{timeline.strip()}"
    starts_ends = [(float(m.group(1)), float(m.group(2))) for m in matches]
    total = starts_ends[-1][1]
    if total <= 0 or any(end <= start for start, end in starts_ends):
        return f"0–{duration:g}秒：{timeline.strip()}"
    if abs(starts_ends[0][0]) <= .05 and abs(total-duration) <= .1 and all(abs(starts_ends[i][0]-starts_ends[i-1][1]) <= .1 for i in range(1,len(matches))):
        return timeline
    boundaries = [0.0] + [round(end / total * duration, 2) for _,end in starts_ends[:-1]] + [duration]
    if any(b <= a for a,b in zip(boundaries,boundaries[1:])):
        return f"0–{duration:g}秒：{timeline.strip()}"
    parts=[]
    for i,m in enumerate(matches):
        action=timeline[m.end():matches[i+1].start() if i+1<len(matches) else len(timeline)].strip(" ：:；;，, ")
        parts.append(f"{boundaries[i]:g}–{boundaries[i+1]:g}秒：{action}")
    return "；".join(parts)

def validate_character(design: dict):
    if not all(design.get("views", {}).get(key) for key in ("front", "side", "back", "three_quarter")):
        raise ValueError("缺少角色视角提示词")
    if not design.get("turnaround_prompt") or not design.get("expression_sheet_prompt") or not design.get("expressions"):
        raise ValueError("缺少角色多视图或表情提示词")


def ensure_project_idle(project_id: int, db):
    from models.drama import Project
    from fastapi import HTTPException
    project = db.get(Project, project_id)
    if not project: raise HTTPException(404, "项目不存在")
    if project.status == "analyzing": raise HTTPException(409, "项目分析中，请完成后再修改或生成")
