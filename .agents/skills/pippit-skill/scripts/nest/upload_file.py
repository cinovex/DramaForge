#!/usr/bin/env python3
"""Upload one image or video to Pippit: POST /api/biz/v1/skill/upload_file."""

import argparse
import json
import mimetypes
import os
import sys
import uuid
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))
from _common import ACCESS_KEY, PIPPIT_BASE, UPLOAD_FILE_PATH, _headers, ensure_access_key, parse_response

ALLOWED_PREFIXES = ("image/", "video/")
MAX_FILE_SIZE = 200 * 1024 * 1024
ASSET_TYPE_VIDEO = 1
ASSET_TYPE_IMAGE = 2


def upload_file(file_path: str) -> dict:
    ensure_access_key()
    if not os.path.isfile(file_path):
        print(f"Error: file does not exist: {file_path}", file=sys.stderr)
        sys.exit(1)

    file_size = os.path.getsize(file_path)
    if file_size > MAX_FILE_SIZE:
        print("Error: file exceeds the 200 MB limit", file=sys.stderr)
        sys.exit(1)

    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type or not any(mime_type.startswith(prefix) for prefix in ALLOWED_PREFIXES):
        print(f"Error: unsupported file type: {mime_type or 'unknown'}. Only images and videos are supported.", file=sys.stderr)
        sys.exit(1)

    asset_type = ASSET_TYPE_VIDEO if mime_type.startswith("video/") else ASSET_TYPE_IMAGE
    boundary = f"----PippitNestUpload{uuid.uuid4().hex}"
    filename = os.path.basename(file_path)

    body_parts = []
    body_parts.append(f"--{boundary}\r\n".encode())
    body_parts.append(b'Content-Disposition: form-data; name="asset_type"\r\n\r\n')
    body_parts.append(f"{asset_type}\r\n".encode())

    body_parts.append(f"--{boundary}\r\n".encode())
    body_parts.append(f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode())
    body_parts.append(f"Content-Type: {mime_type}\r\n\r\n".encode())
    with open(file_path, "rb") as fp:
        body_parts.append(fp.read())
    body_parts.append(b"\r\n")
    body_parts.append(f"--{boundary}--\r\n".encode())

    url = f"{PIPPIT_BASE.rstrip('/')}{UPLOAD_FILE_PATH}"
    headers = _headers(f"multipart/form-data; boundary={boundary}")
    headers["Authorization"] = f"Bearer {ACCESS_KEY}"
    req = urllib.request.Request(url, data=b"".join(body_parts), method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return parse_response(json.loads(resp.read().decode("utf-8")))
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8") if exc.fp else ""
        print(f"API error {exc.code}: {err_body}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as exc:
        print(f"Network error: {exc.reason}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Upload one local image or video to Pippit and return a normalized asset_id.",
        epilog="""
Environment:
  PIPPIT_ACCESS_KEY or PippitAccessKey  Optional if a local PippitAccessKey is already saved
  PIPPIT_OPENAPI_BASE or PIPPIT_BASE_URL  Optional, default https://www.pippit.ai

Examples:
  python3 upload_file.py /path/to/reference.png
  python3 upload_file.py /path/to/reference.mp4
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("file", help="Local image or video path")
    args = parser.parse_args()

    data = upload_file(args.file)
    pippit_asset_id = data.get("pippit_asset_id", "")
    everphoto_asset_id = data.get("asset_id", "")
    asset_id = pippit_asset_id or everphoto_asset_id
    if not asset_id:
        print("Error: response did not include pippit_asset_id or asset_id", file=sys.stderr)
        sys.exit(1)

    output = {"asset_id": asset_id}
    reference_asset_ids = []
    if pippit_asset_id:
        output["pippit_asset_id"] = pippit_asset_id
        reference_asset_ids.append(pippit_asset_id)
    if everphoto_asset_id:
        output["everphoto_asset_id"] = everphoto_asset_id
        if everphoto_asset_id not in reference_asset_ids:
            reference_asset_ids.append(everphoto_asset_id)
    if reference_asset_ids:
        output["reference_asset_ids"] = reference_asset_ids
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
