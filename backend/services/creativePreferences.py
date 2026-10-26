"""Local style presets; these are creative instructions, not vendor model IDs."""
from typing import Literal
from pydantic import BaseModel, Field

stylePresets = [
    {"id": "none", "name": "无预设", "category": "全部", "description": "按剧本内容确定视觉风格", "colors": ["#d7d5d0", "#96958f", "#434845"], "prompt": ""},
    {"id": "cinematic", "name": "写实电影", "category": "真人实拍", "description": "自然肤质、电影布光、克制色彩", "colors": ["#c9a67c", "#465c62", "#17252e"], "prompt": "真人电影质感，自然肤质与真实材质，明确主光方向，克制的电影色彩；人物身份、服装与场景保持一致。"},
    {"id": "costume", "name": "古装写实", "category": "真人实拍", "description": "古典服饰、柔和逆光、层次空间", "colors": ["#e6c6b4", "#9a7272", "#353c48"], "prompt": "古装真人实拍风格，符合故事时代的服饰和建筑，柔和逆光、细腻材质和有层次的空间；不擅自改动原文年代与人物设定。"},
    {"id": "romance", "name": "清新爱情", "category": "真人实拍", "description": "柔和日光、清透色调、自然表演", "colors": ["#f4e1d7", "#9fbdb3", "#526b69"], "prompt": "清新写实爱情片视觉，柔和自然光、清透色调、细腻克制的表演；不改变原剧情和人物关系。"},
    {"id": "suspense", "name": "悬疑冷调", "category": "真人实拍", "description": "冷暖对比、环境阴影、写实质感", "colors": ["#b5cbd0", "#3e5c67", "#16232d"], "prompt": "写实悬疑视觉，冷调环境与局部暖光对比，保留阴影层次和真实材质，不用抽象情绪替代具体镜头。"},
    {"id": "anime", "name": "日系 2D", "category": "2D", "description": "清晰线条、赛璐璐色块、柔和背景", "colors": ["#edd6cb", "#a9bfe0", "#5a6c99"], "prompt": "二维动画风格，清晰线条、赛璐璐色块、柔和细腻的背景，固定人物比例与服装轮廓；保持原剧情。"},
    {"id": "ink", "name": "国风水墨", "category": "2D", "description": "留白、墨色层次、东方构图", "colors": ["#eee9da", "#a8aea2", "#3f514d"], "prompt": "国风水墨视觉，适度留白、墨色层次和东方构图，保证人物、道具和动作清晰可辨，不以画风牺牲叙事连续性。"},
    {"id": "animation", "name": "3D 动画", "category": "3D", "description": "立体造型、柔和材质、清晰轮廓", "colors": ["#f2c298", "#89bcb7", "#3e6875"], "prompt": "三维动画视觉，统一立体角色造型、柔和材质与清晰轮廓，保持角色比例、服装和场景一致。"},
]


class creativeOptions(BaseModel):
    styleId: str = Field(default="none", max_length=60)
    customStyle: str = Field(default="", max_length=2000)
    aspectRatio: Literal["9:16", "16:9", "1:1", "3:4", "4:3", "21:9"] = "9:16"
    episodes: int = Field(default=10, ge=1, le=100)


def resolveCreativeOptions(options):
    preset = next((item for item in stylePresets if item["id"] == options.styleId), None)
    if options.styleId == "custom":
        if not options.customStyle.strip(): raise ValueError("请填写自定义风格")
        name, prompt = "自定义风格", options.customStyle.strip()
    elif preset:
        name, prompt = preset["name"], preset["prompt"]
    else:
        raise ValueError("风格预设不存在，请重新选择")
    return {**options.model_dump(), "styleName": name, "stylePrompt": prompt, "presetVersion": 1}
