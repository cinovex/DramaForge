from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Float, JSON, DateTime, ForeignKey
)
from sqlalchemy.orm import relationship
from database import Base


class Setting(Base):
    """全局配置：每个环节(script/image/video)一行，实现可插拔"""
    __tablename__ = "settings"
    id = Column(Integer, primary_key=True)
    stage = Column(String(20), unique=True, index=True)  # script/image/video
    provider = Column(String(50))
    base_url = Column(String(300))
    model = Column(String(100))
    api_key_enc = Column(Text, default="")   # 加密存储
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True)
    name = Column(String(200))
    script_text = Column(Text, default="")       # 剧本原文
    script_file = Column(String(500), default="")
    status = Column(String(50), default="draft")  # draft/analyzing/ready/producing/done
    created_at = Column(DateTime, default=datetime.utcnow)
    generation_settings = Column(JSON, default=dict)
    canvas_state = Column(JSON, default=dict)
    analysis_state = Column(JSON, default=dict)

    outline = relationship("Outline", back_populates="project", uselist=False,
                           cascade="all, delete-orphan")
    characters = relationship("Character", back_populates="project",
                              cascade="all, delete-orphan")
    scenes = relationship("Scene", back_populates="project",
                          cascade="all, delete-orphan")
    props = relationship("Prop", back_populates="project",
                         cascade="all, delete-orphan")
    shots = relationship("Shot", back_populates="project",
                         cascade="all, delete-orphan")


class Outline(Base):
    __tablename__ = "outlines"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    title = Column(String(200), default="")
    synopsis = Column(Text, default="")
    video_style = Column(Text, default="")
    aspect_ratio = Column(String(10), default="9:16")
    story_type = Column(String(100), default="")
    target_audience = Column(String(200), default="")
    raw_data = Column(JSON, default=dict)
    project = relationship("Project", back_populates="outline")


class Character(Base):
    __tablename__ = "characters"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    name = Column(String(100))
    description = Column(Text, default="")
    base_image_url = Column(String(500), default="")
    design = Column(JSON, default=dict)
    reference_images = Column(JSON, default=dict)
    extra_images = Column(JSON, default=list)
    project = relationship("Project", back_populates="characters")


class Scene(Base):
    __tablename__ = "scenes"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    name = Column(String(100))
    description = Column(Text, default="")
    image_url = Column(String(500), default="")
    image_versions = Column(JSON, default=list)
    design = Column(JSON, default=dict)
    project = relationship("Project", back_populates="scenes")


class Prop(Base):
    __tablename__ = "props"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    name = Column(String(100))
    description = Column(Text, default="")
    image_url = Column(String(500), default="")
    project = relationship("Project", back_populates="props")


class Shot(Base):
    __tablename__ = "shots"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    episode_no = Column(Integer, default=1)
    shot_no = Column(Integer, default=1)
    title = Column(String(200), default="")
    duration = Column(Float, default=7.0)
    scene_name = Column(String(100), default="")
    character_names = Column(JSON, default=list)
    prompt = Column(Text, default="")
    generation_settings = Column(JSON, default=dict)
    direction = Column(JSON, default=dict)
    keyframe_prompt = Column(Text, default="")
    keyframe_url = Column(String(500), default="")
    video_url = Column(String(500), default="")
    video_status = Column(String(50), default="pending")  # pending/processing/done/failed
    provider_task_id = Column(String(200), default="")
    provider_model = Column(String(120), default="")
    generation_manifest = Column(JSON, default=dict)
    review_status = Column(String(30), default="unreviewed")
    review_note = Column(Text, default="")
    last_error = Column(String(500), default="")
    started_at = Column(DateTime, nullable=True)   # 提交生成的时间
    finished_at = Column(DateTime, nullable=True)  # 完成/失败的时间
    history = Column(JSON, default=list)   # 历史生成记录
    project = relationship("Project", back_populates="shots")


class ImageSource(Base):
    """记录提供商原图地址，使本地预览与视频参考使用同一张图片。"""
    __tablename__ = "image_sources"
    id = Column(Integer, primary_key=True)
    local_url = Column(String(500), unique=True, index=True)
    remote_url = Column(Text)
    prompt = Column(Text, default="")
    model = Column(String(120), default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class pippitTaskRecord(Base):
    __tablename__ = "pippit_tasks"
    id = Column(Integer, primary_key=True)
    run_id = Column(String(200), unique=True, index=True)
    thread_id = Column(String(200), index=True)
    message = Column(Text, default="")
    status = Column(String(50), default="submitted")
    web_thread_link = Column(Text, default="")
    result = Column(JSON, default=dict)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class videoQueueRecord(Base):
    __tablename__ = "video_queues"
    id = Column(String(36), primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), index=True)
    episode_no = Column(Integer)
    model = Column(String(160))
    status = Column(String(30), default="queued")
    items = Column(JSON, default=list)
    credit_ceiling = Column(Integer, nullable=True)
    reserved_credits = Column(Integer, default=0)
    pause_requested = Column(Integer, default=0)
    message = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class pippitAccountRecord(Base):
    __tablename__ = "pippit_accounts"
    id = Column(String(36), primary_key=True)
    label = Column(String(80))
    api_key_enc = Column(Text, default="")
    enabled = Column(Integer, default=1)
    exhausted = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
