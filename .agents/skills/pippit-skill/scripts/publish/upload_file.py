#!/usr/bin/env python3
"""Upload a video to Pippit: POST /api/biz/v1/skill/upload_file (multipart/form-data)"""

import argparse
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request
import uuid

sys.path.insert(0, os.path.dirname(__file__))
from _common import PIPPIT_BASE, UPLOAD_FILE_PATH, VIDEO_ASSET_TYPE, _headers, ensure_access_key, parse_response


def upload_file(file_path: str) -> dict:
    ensure_access_key()
    if not os.path.isfile(file_path):
        print(f"Error: file does not exist: {file_path}", file=sys.stderr)
        sys.exit(1)

    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type or not mime_type.startswith("video/"):
        print(f"Error: only video files are supported; current type: {mime_type or 'unknown'}", file=sys.stderr)
        sys.exit(1)

    boundary = f"----PippitUpload{uuid.uuid4().hex}"
    filename = os.path.basename(file_path)

    body_parts = []
    body_parts.append(f"--{boundary}\r\n".encode())
    body_parts.append(b'Content-Disposition: form-data; name="asset_type"\r\n\r\n')
    body_parts.append(f"{VIDEO_ASSET_TYPE}\r\n".encode())

    body_parts.append(f"--{boundary}\r\n".encode())
    body_parts.append(
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode()
    )
    body_parts.append(f"Content-Type: {mime_type}\r\n\r\n".encode())
    with open(file_path, "rb") as fp:
        body_parts.append(fp.read())
    body_parts.append(b"\r\n")
    body_parts.append(f"--{boundary}--\r\n".encode())

    url = f"{PIPPIT_BASE.rstrip('/')}{UPLOAD_FILE_PATH}"
    req = urllib.request.Request(
        url,
        data=b"".join(body_parts),
        method="POST",
        headers=_headers(f"multipart/form-data; boundary={boundary}"),
    )
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
        description="Upload a video file to the Pippit asset library",
        epilog="""
Environment variables:
  PIPPIT_ACCESS_KEY or PippitAccessKey  Optional; can reuse a locally saved PippitAccessKey
  PIPPIT_OPENAPI_BASE or PIPPIT_BASE_URL  Optional; defaults to https://www.pippit.ai

Example:
  python3 upload_file.py /path/to/video.mp4
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("file", help="Path to the video file to upload")
    args = parser.parse_args()

    data = upload_file(args.file)
    asset_id = data.get("asset_id", "")
    if not asset_id:
        print("Error: asset_id was not returned", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
