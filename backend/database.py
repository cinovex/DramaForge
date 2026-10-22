from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from config import DATABASE_URL

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    import models.drama  # noqa: ensure models are registered
    Base.metadata.create_all(bind=engine)
    _migrate_legacy()


def _migrate_legacy():
    """为已存在的 SQLite 库补充后加列（create_all 不会修改旧表）"""
    with engine.begin() as conn:
        cols = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(shots)")]
        if "started_at" not in cols:
            conn.exec_driver_sql("ALTER TABLE shots ADD COLUMN started_at DATETIME")
        if "finished_at" not in cols:
            conn.exec_driver_sql("ALTER TABLE shots ADD COLUMN finished_at DATETIME")

        additions = {
            "projects": {"canvas_state": "JSON", "analysis_state": "JSON", "generation_settings": "JSON"},
            "characters": {"design": "JSON", "reference_images": "JSON"},
            "scenes": {"design": "JSON", "image_versions": "JSON"},
            "shots": {"direction": "JSON", "keyframe_prompt": "TEXT", "generation_settings": "JSON", "provider_model": "VARCHAR(120)", "generation_manifest": "JSON", "review_status": "VARCHAR(30)", "review_note": "TEXT"},
            "image_sources": {"prompt": "TEXT", "model": "VARCHAR(120)"},
        }
        for table, fields in additions.items():
            existing = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
            for field, sql_type in fields.items():
                if field not in existing:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {field} {sql_type}")
