#!/usr/bin/env python3
"""Download generated Pippit result URLs to local files."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import shutil
import urllib.error
import urllib.parse
import urllib.request


def download_file(url: str, filepath: str):
    req = urllib.request.Request(url, headers={"User-Agent": "Pippit-Nest-Skill/1.0"})
    tmp_path = filepath + ".tmp"
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            content_type = resp.headers.get("Content-Type", "")
            with open(tmp_path, "wb") as fp:
                shutil.copyfileobj(resp, fp, length=1024 * 1024)
        os.replace(tmp_path, filepath)
        final_path, normalized_from = normalize_downloaded_path(filepath, content_type)
        return {"file": final_path, "normalized_from": normalized_from}, None
    except Exception as exc:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        return {"file": filepath, "normalized_from": ""}, str(exc)


def extension_from_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)
    filenames = query.get("filename", [])
    if filenames:
        _, ext = os.path.splitext(filenames[0])
        if ext:
            return ext
    _, ext = os.path.splitext(parsed.path)
    return ext or ".bin"


def normalize_downloaded_path(filepath: str, content_type: str = ""):
    detected_ext = extension_from_file(filepath, content_type)
    if not detected_ext:
        return filepath, ""

    root, current_ext = os.path.splitext(filepath)
    current_ext = current_ext.lower()
    if current_ext == detected_ext:
        return filepath, ""

    if current_ext not in {".image", ".bin", ".download", ""}:
        return filepath, ""

    final_path = root + detected_ext
    os.replace(filepath, final_path)
    return final_path, filepath


def extension_from_file(filepath: str, content_type: str = "") -> str:
    content_type = (content_type or "").split(";", 1)[0].strip().lower()
    by_content_type = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "video/mp4": ".mp4",
        "video/quicktime": ".mov",
    }
    if content_type in by_content_type:
        return by_content_type[content_type]

    try:
        with open(filepath, "rb") as fp:
            header = fp.read(32)
    except OSError:
        return ""

    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if header.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if header.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return ".webp"
    if len(header) >= 12 and header[4:8] == b"ftyp":
        return ".mp4"
    return ""


def main():
    parser = argparse.ArgumentParser(
        description="Download generated image/video URLs to a local output directory.",
        epilog="""
Example:
  python3 download_results.py --urls URL1 URL2 URL3 --output-dir ./pippit_output --prefix artifact
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--urls", nargs="+", required=True, help="Result URLs to download")
    parser.add_argument("--output-dir", default="", help="Output directory. Defaults to ./pippit_output")
    parser.add_argument("--prefix", default="", help="Filename prefix, for example artifact -> artifact_01.mp4")
    parser.add_argument("--workers", type=int, default=5, help="Parallel download workers. Defaults to 5.")
    args = parser.parse_args()

    output_dir = args.output_dir or "./pippit_output"
    os.makedirs(output_dir, exist_ok=True)

    tasks = []
    for index, url in enumerate(args.urls, 1):
        ext = extension_from_url(url)
        filename = f"{args.prefix}_{index:02d}{ext}" if args.prefix else f"{index:02d}{ext}"
        tasks.append((url, os.path.join(output_dir, filename)))

    downloaded = []
    errors = []
    normalized = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(download_file, url, filepath): (url, filepath) for url, filepath in tasks}
        for future in as_completed(futures):
            result, error = future.result()
            filepath = result["file"]
            if error:
                errors.append({"file": filepath, "error": error})
            else:
                downloaded.append(filepath)
                if result["normalized_from"]:
                    normalized.append({"from": result["normalized_from"], "to": filepath})

    downloaded.sort()
    output = {
        "output_dir": output_dir,
        "downloaded": downloaded,
        "total": len(downloaded),
    }
    if normalized:
        output["normalized"] = normalized
    if errors:
        output["errors"] = errors
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
