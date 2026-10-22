"""Project-owned media paths and safe one-time migration from legacy shared folders."""
from __future__ import annotations

import filecmp
import re
import shutil
import uuid
from pathlib import Path

from config import (
    IMAGES_DIR,
    PROJECTS_DIR,
    SCRIPTS_DIR,
    STORAGE_DIR,
    VIDEOS_DIR,
    ensure_project_directory,
    project_directory,
)


def _storage_path(url: str) -> Path | None:
    if not isinstance(url, str) or not url.startswith("/storage/"):
        return None
    relative = url.removeprefix("/storage/").split("?", 1)[0]
    candidate = (STORAGE_DIR / relative).resolve()
    if not candidate.is_relative_to(STORAGE_DIR.resolve()):
        return None
    return candidate


def _unique_copy(source: Path, target: Path, created: list[Path]) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        try:
            if filecmp.cmp(source, target, shallow=False):
                return target
        except OSError:
            pass
        target = target.with_name(f"{target.stem}_{uuid.uuid4().hex[:8]}{target.suffix}")
    shutil.copy2(source, target)
    created.append(target)
    return target


def _referenced_urls(project) -> set[str]:
    urls: set[str] = set()

    def add(value):
        if isinstance(value, str) and value.startswith("/storage/"):
            urls.add(value.split("?", 1)[0])

    for character in project.characters:
        add(character.base_image_url)
        for value in character.extra_images or []: add(value)
        for value in (character.reference_images or {}).values(): add(value)
    for scene in project.scenes:
        add(scene.image_url)
        for value in scene.image_versions or []: add(value)
    for prop in project.props: add(prop.image_url)
    for shot in project.shots:
        add(shot.keyframe_url); add(shot.video_url)
        manifests = [shot.generation_manifest or {}]
        for item in shot.history or []:
            if isinstance(item, dict):
                add(item.get("video_url"))
                manifests.append(item.get("manifest") or {})
        for manifest in manifests:
            add(manifest.get("first_frame"))
            for reference in manifest.get("references") or []:
                if isinstance(reference, dict): add(reference.get("url"))
    return urls


def _rewrite_manifest(manifest: dict, image_url_map: dict[str, str]) -> dict:
    result = dict(manifest or {})
    first_frame = result.get("first_frame")
    if first_frame in image_url_map:
        result["first_frame"] = image_url_map[first_frame]
    references = result.get("references")
    if isinstance(references, list):
        result["references"] = [
            {**reference, "url": image_url_map.get(reference.get("url"), reference.get("url"))}
            if isinstance(reference, dict) else reference
            for reference in references
        ]
    return result


def organize_project_files(db, project) -> dict:
    """Move this project's referenced legacy media into its own folder.

    Copies first, commits rewritten references, then removes only legacy files
    that no remaining project references. Calling this repeatedly is safe.
    """
    project_id = int(project.id)
    project_root = ensure_project_directory(project_id).resolve()
    image_dir = project_root / "images"
    video_dir = project_root / "videos"
    script_dir = project_root / "scripts"
    export_dir = project_root / "exports"
    created: list[Path] = []
    image_url_map: dict[str, str] = {}
    old_paths_to_remove: set[Path] = set()
    old_image_urls: set[str] = set()
    project_script_source: Path | None = None

    def move_image(url: str) -> str:
        source = _storage_path(url)
        if source is None or not source.is_file(): return url
        if source.is_relative_to(image_dir.resolve()): return url
        if not source.is_relative_to(IMAGES_DIR.resolve()): return url
        old_url = url.split("?", 1)[0]
        if old_url in image_url_map: return image_url_map[old_url]
        relative = source.relative_to(IMAGES_DIR.resolve())
        target = _unique_copy(source, image_dir / relative, created)
        new_url = "/storage/" + target.relative_to(STORAGE_DIR.resolve()).as_posix()
        image_url_map[old_url] = new_url
        old_image_urls.add(old_url)
        old_paths_to_remove.add(source)
        return new_url

    def move_video(url: str, episode_no: int, shot_no: int) -> str:
        source = _storage_path(url)
        if source is None or not source.is_file(): return url
        if source.is_relative_to(video_dir.resolve()): return url
        if not source.is_relative_to(VIDEOS_DIR.resolve()): return url
        suffix = re.sub(r"[^A-Za-z0-9_-]", "", source.stem.rsplit("_", 1)[-1])[-10:]
        suffix = suffix or uuid.uuid4().hex[:8]
        target = _unique_copy(
            source,
            video_dir / f"EP{max(1, int(episode_no or 1)):02d}_第{max(1, int(shot_no or 1)):03d}段_{suffix}.mp4",
            created,
        )
        old_paths_to_remove.add(source)
        return "/storage/" + target.relative_to(STORAGE_DIR.resolve()).as_posix()

    # Populate the image URL map before rewriting manifests, which may hold a
    # reference to an older image no longer present in the asset's current list.
    for existing_url in _referenced_urls(project):
        move_image(existing_url)

    # Assets and keyframes retain their former category and filename under the project root.
    for character in project.characters:
        character.base_image_url = move_image(character.base_image_url)
        character.extra_images = [move_image(url) for url in (character.extra_images or [])]
        character.reference_images = {
            key: move_image(url) for key, url in (character.reference_images or {}).items()
        }
    for scene in project.scenes:
        scene.image_url = move_image(scene.image_url)
        scene.image_versions = [move_image(url) for url in (scene.image_versions or [])]
    for prop in project.props:
        prop.image_url = move_image(prop.image_url)
    for shot in project.shots:
        shot.keyframe_url = move_image(shot.keyframe_url)
        shot.video_url = move_video(shot.video_url, shot.episode_no, shot.shot_no)
        history = []
        for item in shot.history or []:
            if not isinstance(item, dict):
                history.append(item)
                continue
            entry = dict(item)
            entry["video_url"] = move_video(entry.get("video_url", ""), shot.episode_no, shot.shot_no)
            entry["manifest"] = _rewrite_manifest(entry.get("manifest") or {}, image_url_map)
            history.append(entry)
        shot.history = history
        shot.generation_manifest = _rewrite_manifest(shot.generation_manifest or {}, image_url_map)

    if project.script_file:
        try:
            source_script = Path(project.script_file).resolve()
            if source_script.is_relative_to(SCRIPTS_DIR.resolve()) and source_script.is_file():
                project_script_source = source_script
                target_script = _unique_copy(source_script, script_dir / source_script.name, created)
                project.script_file = str(target_script)
                old_paths_to_remove.add(source_script)
        except (OSError, ValueError):
            pass

    legacy_exports: list[tuple[Path, Path]] = []
    if VIDEOS_DIR.exists():
        pattern = re.compile(rf"^export_ep(all|\d+)_{project_id}_([a-f0-9]+)\.mp4$", re.IGNORECASE)
        for source in VIDEOS_DIR.iterdir():
            if not source.is_file(): continue
            match = pattern.fullmatch(source.name)
            if not match: continue
            label = "全集" if match.group(1).lower() == "all" else f"EP{int(match.group(1)):02d}"
            target = _unique_copy(source, export_dir / f"{label}_成片_{match.group(2)}.mp4", created)
            legacy_exports.append((source.resolve(), target))

    # Duplicate the lookup row for each new local image URL; the remote provider URL stays stable.
    if image_url_map:
        from models.drama import ImageSource
        for old_url, new_url in image_url_map.items():
            source_row = db.query(ImageSource).filter_by(local_url=old_url).first()
            if not source_row or db.query(ImageSource).filter_by(local_url=new_url).first(): continue
            db.add(ImageSource(local_url=new_url, remote_url=source_row.remote_url,
                               prompt=source_row.prompt, model=source_row.model))

    try:
        db.commit()
    except Exception:
        db.rollback()
        for path in created:
            path.unlink(missing_ok=True)
        raise

    # Remove the original only once no other project still points at it.
    from models.drama import Project, ImageSource
    remaining_projects = db.query(Project).all()
    remaining_urls = set().union(*(_referenced_urls(item) for item in remaining_projects))
    remaining_scripts = set()
    for item in remaining_projects:
        if item.script_file:
            try: remaining_scripts.add(Path(item.script_file).resolve())
            except (OSError, ValueError): pass
    for old_url in old_image_urls:
        if old_url not in remaining_urls:
            db.query(ImageSource).filter_by(local_url=old_url).delete(synchronize_session=False)
    if old_image_urls:
        db.commit()

    warnings = []
    for source in old_paths_to_remove | {pair[0] for pair in legacy_exports}:
        if source in created: continue
        if project_script_source is not None and source == project_script_source and source in remaining_scripts:
            continue
        if source.is_relative_to(IMAGES_DIR.resolve()) and any(
            url for url in remaining_urls if (_storage_path(url) == source)
        ):
            continue
        if source.is_relative_to(VIDEOS_DIR.resolve()) and any(
            url for url in remaining_urls if (_storage_path(url) == source)
        ):
            continue
        try:
            source.unlink(missing_ok=True)
        except OSError:
            warnings.append(f"旧文件未能移走：{source.name}")

    return {
        "files_moved": len(created),
        "project_folder": str(project_root),
        "cleanup_warning": "；".join(warnings) if warnings else "",
    }
