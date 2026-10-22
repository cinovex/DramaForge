#!/usr/bin/env python3
"""Update social publishing tasks: POST /api/biz/v1/publish/skill/update_schedule_task"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _common import (
    ACTION_TYPE_PUBLISH,
    DEFAULT_ACTION_FROM,
    DEFAULT_FILE_TYPE,
    PUBLISH_TYPE_SCHEDULE,
    TASK_TYPE_PUBLISH_MEDIA,
    UPDATE_SCHEDULE_TASK_PATH,
    api_post,
    build_platform_params,
    parse_response,
    platform_code,
    require_schedule_time_ms,
)


def build_request_from_args(args) -> dict:
    schedule_time = require_schedule_time_ms(args.schedule_time)
    publish_media_param = {
        "platform_type": platform_code(args.platform),
        "publish_type": PUBLISH_TYPE_SCHEDULE,
        "platform_user_ids": args.platform_user_id,
        "file_type": DEFAULT_FILE_TYPE,
        "schedule_time": schedule_time,
        "action_type": ACTION_TYPE_PUBLISH,
        "action_from": DEFAULT_ACTION_FROM,
    }
    if args.asset_id:
        publish_media_param["asset_id_list"] = args.asset_id
    if args.url:
        publish_media_param["urls"] = args.url
    publish_media_param.update(build_platform_params(args, args.asset_id, schedule_time))

    return {
        "task_type": TASK_TYPE_PUBLISH_MEDIA,
        "update_media_param": {
            "id": int(args.id),
            "publish_media_param": publish_media_param,
        },
    }


def main():
    parser = argparse.ArgumentParser(
        description="Update a Pippit scheduled social publishing task; sets publish_type=2, task_type=1, action_type=2, action_from=0, file_type=1, and requires --schedule-time",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--id", required=True, help="Task ID")
    parser.add_argument("--platform", choices=["tiktok", "facebook", "facebook-page", "instagram", "ins"], required=True, help="Target platform")
    parser.add_argument("--platform-user-id", nargs="+", default=[], help="Platform account ID; may be repeated")
    parser.add_argument("--asset-id", nargs="+", default=[], help="Video asset_id; may be repeated")
    parser.add_argument("--url", nargs="+", default=[], help="URL publishing parameter")
    parser.add_argument("--title", default="", help="Title or caption")
    parser.add_argument("--description", default="", help="Facebook Page description")
    parser.add_argument("--schedule-time", required=True, help="Publish time; required; supports millisecond timestamp or ISO8601")

    parser.add_argument("--disable-comment", action="store_true")
    parser.add_argument("--disable-duet", action="store_true")
    parser.add_argument("--disable-stitch", action="store_true")
    parser.add_argument("--privacy-level", choices=["public", "mutual", "self", "followers"], default="public")
    parser.add_argument("--disclose-video-content", action="store_true")
    parser.add_argument("--promote-own-brand", action="store_true")
    parser.add_argument("--promote-other-brand", action="store_true")
    parser.add_argument("--is-branded-content", action="store_true")
    parser.add_argument("--is-brand-organic", action="store_true")
    parser.add_argument("--tiktok-json", default="", help="TikTok extension JSON for anchors and other complex fields")

    parser.add_argument("--instagram-media-type", choices=["reels", "video"], default="reels")
    parser.add_argument("--audio-name", default="")
    parser.add_argument("--collaborators", nargs="+", default=[])
    parser.add_argument("--share-to-feed", action="store_true")
    parser.add_argument("--instagram-json", default="", help="Instagram extension JSON for user_tags/product_tags and other complex fields")

    parser.add_argument("--facebook-media-type", choices=["reels", "video"], default="reels")
    parser.add_argument("--facebook-json", default="", help="Facebook Page extension JSON for complex field overrides")
    parser.add_argument("--cover-timestamp-ms", type=int, default=None)
    args = parser.parse_args()

    if not args.platform_user_id:
        print("Error: at least one --platform-user-id is required", file=sys.stderr)
        sys.exit(1)
    if not args.asset_id and not args.url:
        print("Error: provide at least one --asset-id or --url", file=sys.stderr)
        sys.exit(1)
    body = build_request_from_args(args)
    data = parse_response(api_post(UPDATE_SCHEDULE_TASK_PATH, body))
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
