import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # D:\DramaForge
STORAGE_DIR = BASE_DIR / "storage"
DB_PATH = BASE_DIR / "dramaforge.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

# 存储子目录
SCRIPTS_DIR = STORAGE_DIR / "scripts"
IMAGES_DIR = STORAGE_DIR / "images"
VIDEOS_DIR = STORAGE_DIR / "videos"
PROJECTS_DIR = STORAGE_DIR / "projects"
for d in (SCRIPTS_DIR, IMAGES_DIR, VIDEOS_DIR, PROJECTS_DIR):
    d.mkdir(parents=True, exist_ok=True)


def project_directory(project_id: int) -> Path:
    """Return the stable local storage root owned by one project."""
    safe_id = int(project_id)
    if safe_id <= 0:
        raise ValueError("project_id must be positive")
    return PROJECTS_DIR / str(safe_id)


def ensure_project_directory(project_id: int) -> Path:
    root = project_directory(project_id)
    for child in ("scripts", "images", "videos", "exports"):
        (root / child).mkdir(parents=True, exist_ok=True)
    return root

# 用于加密存储 API key 的密钥（生产环境应放环境变量）
SECRET_KEY = os.getenv("DRAMAFORGE_SECRET", "dramaforge-local-dev-secret-key-change-me")

# 默认 API 配置（可在设置中心覆盖）
DEFAULT_SETTINGS = {
    "script": {   # 剧本分析
        "provider": "openai",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o",
        "api_key": "",
    },
    "image": {    # 图片生成
        "provider": "openai",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-image-1",
        "api_key": "",
    },
    "video": {    # 视频生成
        "provider": "agnes",
        "base_url": "https://api.agnes-ai.cn/v1",
        "model": "agnes-video-2.5",
        "api_key": "",
    },
}
