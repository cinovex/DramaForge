"""Shared DramaForge model settings and Toonflow canvas compatibility.

API credentials and selected model IDs live in the encrypted DramaForge settings
table. Toonflow's settings document remains for canvas preferences/provider
metadata, with duplicated API URLs and keys stripped after migration.
"""

from __future__ import annotations

import copy
import json
import os
import tempfile
from pathlib import Path

from sqlalchemy.orm import Session

from config import BASE_DIR, DEFAULT_SETTINGS, STORAGE_DIR
from database import SessionLocal
from models.drama import Setting
from services.crypto import encrypt, decrypt

TOONFLOW_SETTINGS_PATH = STORAGE_DIR / "canvasData" / "settings.json"
TEXT_PROVIDER_ID = "dramaForgeOpenAI"
TEXT_PROTOCOL = "openai-responses"


def _read_canvas_document() -> dict:
    try:
        document = json.loads(TOONFLOW_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"settings": {}}
    if not isinstance(document, dict):
        return {"settings": {}}
    settings = document.get("settings")
    if not isinstance(settings, dict):
        document["settings"] = {}
    return document


def _write_canvas_document(document: dict) -> None:
    TOONFLOW_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="settings-", suffix=".json", dir=TOONFLOW_SETTINGS_PATH.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(document, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, TOONFLOW_SETTINGS_PATH)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _rows_by_stage(db: Session) -> dict[str, Setting]:
    return {row.stage: row for row in db.query(Setting).all()}


def ensure_default_settings():
    """Create defaults, import the former Toonflow credentials, then scrub duplicates."""
    db = SessionLocal()
    try:
        rows = _rows_by_stage(db)
        for stage, cfg in DEFAULT_SETTINGS.items():
            if stage not in rows:
                row = Setting(stage=stage, provider=cfg["provider"], base_url=cfg["base_url"],
                              model=cfg["model"], api_key_enc=encrypt(cfg.get("api_key", "")))
                db.add(row)
                rows[stage] = row
        db.flush()

        document = _read_canvas_document()
        settings = document["settings"]
        providers = settings.get("customProviders")
        text_provider = next((p for p in providers or [] if isinstance(p, dict)), None)
        migrated = False

        # Import the current Toonflow credentials once. The database already
        # has the selected text model; keep it unless the old provider had a
        # model list and the selection is no longer valid.
        script = rows.get("script")
        if script and isinstance(text_provider, dict):
            api_key = text_provider.get("apiKey")
            api_url = text_provider.get("apiUrl")
            models = text_provider.get("models") or []
            model_ids = [m.get("id") for m in models if isinstance(m, dict) and isinstance(m.get("id"), str)]
            if isinstance(api_key, str) and api_key:
                script.api_key_enc = encrypt(api_key)
                migrated = True
            if isinstance(api_url, str) and api_url:
                script.base_url = api_url
                migrated = True
            if model_ids and script.model not in model_ids:
                script.model = model_ids[0]

        media_configs = settings.get("mediaProviderConfigs")
        if isinstance(media_configs, dict):
            for stage in ("image", "video"):
                row = rows.get(stage)
                config = media_configs.get(row.provider) if row else None
                if not isinstance(config, dict):
                    continue
                api_key, api_url = config.get("apiKey"), config.get("apiUrl")
                if isinstance(api_key, str) and api_key:
                    row.api_key_enc = encrypt(api_key)
                    migrated = True
                if isinstance(api_url, str) and api_url:
                    row.base_url = api_url
                    migrated = True

        db.commit()
        # Erase legacy copies only after the encrypted DB copy is committed and
        # verified. The JSON retains non-credential canvas preferences.
        if migrated and _credentials_are_persisted(rows):
            _strip_migrated_credentials(settings, rows)
            settings["dramaForgeConfigMigrated"] = True
            document["settings"] = settings
            _write_canvas_document(document)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _credentials_are_persisted(rows: dict[str, Setting]) -> bool:
    document = _read_canvas_document()
    settings = document.get("settings", {})
    text_provider = next((p for p in settings.get("customProviders", []) if isinstance(p, dict)), None)
    script = rows.get("script")
    if text_provider and text_provider.get("apiKey"):
        if not script or decrypt(script.api_key_enc) != text_provider.get("apiKey"):
            return False
    configs = settings.get("mediaProviderConfigs", {})
    for stage in ("image", "video"):
        row = rows.get(stage)
        config = configs.get(row.provider, {}) if row else {}
        if config.get("apiKey") and (not row or decrypt(row.api_key_enc) != config.get("apiKey")):
            return False
    return True


def _strip_migrated_credentials(settings: dict, rows: dict[str, Setting]) -> None:
    text_provider = next((p for p in settings.get("customProviders", []) if isinstance(p, dict)), None)
    if text_provider:
        text_provider.pop("apiKey", None)
        text_provider.pop("apiUrl", None)
    media_configs = settings.get("mediaProviderConfigs")
    if isinstance(media_configs, dict):
        ids = {rows[stage].provider for stage in ("image", "video") if stage in rows}
        for provider_id in ids:
            config = media_configs.get(provider_id)
            if isinstance(config, dict):
                config.pop("apiKey", None)
                config.pop("apiUrl", None)


def _safe_stage_config(row: Setting) -> dict:
    """Use the single encrypted settings record as the API configuration source."""
    return {
        "stage": row.stage,
        "provider": row.provider,
        "base_url": row.base_url or "",
        "model": row.model,
        "api_key": decrypt(row.api_key_enc),
    }


def get_all_settings(db: Session):
    result = {}
    for row in db.query(Setting).all():
        config = _safe_stage_config(row)
        key = config["api_key"]
        result[row.stage] = {
            "stage": row.stage,
            "provider": row.provider,
            "base_url": row.base_url or "",
            "model": row.model,
            "api_key_set": bool(key),
            "api_key_masked": ("*" * 6 + key[-4:]) if key else "",
        }
    return result


def get_stage_config(db: Session, stage: str) -> dict | None:
    row = db.query(Setting).filter_by(stage=stage).first()
    return _safe_stage_config(row) if row else None


def update_setting(db: Session, stage: str, data: dict):
    row = db.query(Setting).filter_by(stage=stage).first()
    if not row:
        row = Setting(stage=stage, provider="", base_url="", model="", api_key_enc=encrypt(""))
        db.add(row)
    if data.get("provider") is not None:
        row.provider = data["provider"]
    if data.get("base_url") is not None:
        row.base_url = data["base_url"]
    if data.get("model") is not None:
        row.model = data["model"]
    if data.get("api_key"):
        row.api_key_enc = encrypt(data["api_key"])
    db.commit()
    db.refresh(row)
    return row


def get_toonflow_settings(db: Session) -> dict:
    """Build Toonflow's expected settings shape from the shared DramaForge rows."""
    document = _read_canvas_document()
    settings = copy.deepcopy(document["settings"])
    rows = _rows_by_stage(db)
    script = rows.get("script")
    providers = settings.get("customProviders")
    if not isinstance(providers, list):
        providers = []
    provider = next((p for p in providers if isinstance(p, dict)), None)
    if script:
        if provider is None:
            provider = {"id": TEXT_PROVIDER_ID, "label": "DramaForge 文本模型", "protocol": TEXT_PROTOCOL}
            providers.insert(0, provider)
        provider["apiUrl"] = script.base_url
        provider["apiKey"] = decrypt(script.api_key_enc)
        models = provider.get("models") if isinstance(provider.get("models"), list) else []
        if not any(isinstance(m, dict) and m.get("id") == script.model for m in models):
            models = [{"id": script.model, "label": script.model}, *models]
        provider["models"] = models
    settings["customProviders"] = providers

    configs = settings.get("mediaProviderConfigs")
    if not isinstance(configs, dict):
        configs = {}
    for stage in ("image", "video"):
        row = rows.get(stage)
        if not row:
            continue
        config = configs.get(row.provider)
        if not isinstance(config, dict):
            config = {}
        config["apiUrl"] = row.base_url
        config["apiKey"] = decrypt(row.api_key_enc)
        configs[row.provider] = config
    settings["mediaProviderConfigs"] = configs
    return settings


def save_toonflow_settings(db: Session, value: dict) -> dict:
    """Persist canvas preferences to JSON and model/API fields to the DB."""
    if not isinstance(value, dict):
        raise ValueError("设置格式不正确")
    rows = _rows_by_stage(db)
    providers = value.get("customProviders")
    text_provider = next((p for p in providers or [] if isinstance(p, dict)), None)
    script = rows.get("script")
    if script and text_provider:
        if isinstance(text_provider.get("apiUrl"), str):
            script.base_url = text_provider["apiUrl"]
        if isinstance(text_provider.get("apiKey"), str) and text_provider["apiKey"]:
            script.api_key_enc = encrypt(text_provider["apiKey"])
        model_ids = [m.get("id") for m in text_provider.get("models", []) if isinstance(m, dict) and isinstance(m.get("id"), str)]
        if model_ids and script.model not in model_ids:
            script.model = model_ids[0]

    configs = value.get("mediaProviderConfigs")
    if isinstance(configs, dict):
        for stage in ("image", "video"):
            row = rows.get(stage)
            config = configs.get(row.provider) if row else None
            if not isinstance(config, dict):
                continue
            if isinstance(config.get("apiUrl"), str):
                row.base_url = config["apiUrl"]
            if isinstance(config.get("apiKey"), str) and config["apiKey"]:
                row.api_key_enc = encrypt(config["apiKey"])

    db.commit()
    # Store non-model preferences and provider metadata only. Credentials and
    # API URLs are reconstructed from the one DramaForge settings table.
    document = _read_canvas_document()
    stored = copy.deepcopy(value)
    _strip_migrated_credentials(stored, rows)
    stored["dramaForgeConfigMigrated"] = True
    document["settings"] = stored
    _write_canvas_document(document)
    return get_toonflow_settings(db)
