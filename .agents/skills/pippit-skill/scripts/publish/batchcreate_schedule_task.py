#!/usr/bin/env python3
"""Batch create social publishing tasks: POST /api/biz/v1/publish/skill/batchcreate_schedule_task"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _common import (
    ACTION_TYPE_PUBLISH,
    BATCHCREATE_SCHEDULE_TASK_PATH,
    DEFAULT_ACTION_FROM,
    DEFAULT_FILE_TYPE,
    PUBLISH_TYPE_SCHEDULE,
    TASK_TYPE_PUBLISH_MEDIA,
    api_post,
    build_platform_params,
    parse_response,
    platform_code,
    require_schedule_time_ms,
)


def build_request_from_args(args) -> dict:
    if not args.platform_user_id:
        print("Error: at least one --platform-user-id is required", file=sys.stderr)
        sys.exit(1)
    if not args.asset_id and not args.url:
        print("Error: provide at least one --asset-id or --url", file=sys.stderr)
        sys.exit(1)
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
        "requests": [
            {
                "task_type": TASK_TYPE_PUBLISH_MEDIA,
                "publish_media_param": publish_media_param,
            }
        ]
    }


def build_debug_output(resp: dict, data) -> dict:
    responses = data.get("responses", []) if isinstance(data, dict) else []
    child_task_results = []
    for index, item in enumerate(responses):
        child_data = item.get("data") if isinstance(item, dict) else {}
        child_task_results.append(
            {
                "index": index,
                "ret": item.get("ret"),
                "errmsg": item.get("errmsg"),
                "child_task_log_id": item.get("log_id"),
                "task_id": (child_data or {}).get("id"),
            }
        )

    return {
        "request_log_id": resp.get("log_id"),
        "child_task_results": child_task_results,
        "responses": responses,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Create a Pippit scheduled social publishing task; sets publish_type=2, task_type=1, action_type=2, action_from=0, file_type=1, and requires --schedule-time",
        epilog="""
Examples:
  python3 batchcreate_schedule_task.py --platform tiktok --platform-user-id 123 --asset-id asset_xxx --title "hello" --schedule-time "2026-04-13T09:03:00+08:00"

  python3 batchcreate_schedule_task.py --platform tiktok --platform-user-id 123 --asset-id 7628276784362275344 --title "123" --schedule-time "2026-04-13T09:03:00+08:00" --disable-duet --disable-stitch

  python3 batchcreate_schedule_task.py --platform tiktok --platform-user-id 123 --asset-id 7628276784362275344 --title "123" --schedule-time "2026-04-13T09:03:00+08:00" --tiktok-json '{"anchors":[],"is_disclose_video_content":false,"is_promote_own_brand":false,"is_promote_other_brand":false}'
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--platform", choices=["tiktok", "facebook", "facebook-page", "instagram", "ins"], required=True, help="Target platform")
    parser.add_argument("--platform-user-id", nargs="+", default=[], help="Platform account ID; may be repeated")
    parser.add_argument("--asset-id", nargs="+", default=[], help="Video asset_id; may be repeated")
    parser.add_argument("--url", nargs="+", default=[], help="URL publishing parameter; lower priority than asset_id")
    parser.add_argument("--title", default="", help="Title or caption")
    parser.add_argument("--description", default="", help="Facebook Page description")
    parser.add_argument("--schedule-time", required=True, help="Publish time; required; supports millisecond timestamp or ISO8601")

    parser.add_argument("--disable-comment", action="store_true", help="TikTok: disable comments")
    parser.add_argument("--disable-duet", action="store_true", help="TikTok: disable duet")
    parser.add_argument("--disable-stitch", action="store_true", help="TikTok: disable stitch")
    parser.add_argument("--privacy-level", choices=["public", "mutual", "self", "followers"], default="public", help="TikTok privacy level; default: public")
    parser.add_argument("--disclose-video-content", action="store_true", help="TikTok: disclose video content")
    parser.add_argument("--promote-own-brand", action="store_true", help="TikTok: promote own brand")
    parser.add_argument("--promote-other-brand", action="store_true", help="TikTok: promote another brand")
    parser.add_argument("--is-branded-content", action="store_true", help="TikTok: branded content")
    parser.add_argument("--is-brand-organic", action="store_true", help="TikTok: brand organic content")
    parser.add_argument("--tiktok-json", default="", help="TikTok extension JSON for anchors and other complex fields")

    parser.add_argument("--instagram-media-type", choices=["reels", "video"], default="reels", help="Instagram video type")
    parser.add_argument("--audio-name", default="", help="Instagram Reels audio name")
    parser.add_argument("--collaborators", nargs="+", default=[], help="Instagram collaborator usernames")
    parser.add_argument("--share-to-feed", action="store_true", help="Share Instagram Reels to Feed")
    parser.add_argument("--instagram-json", default="", help="Instagram extension JSON for user_tags/product_tags and other complex fields")

    parser.add_argument("--facebook-media-type", choices=["reels", "video"], default="reels", help="Facebook video type")
    parser.add_argument("--facebook-json", default="", help="Facebook Page extension JSON for complex field overrides")
    parser.add_argument("--cover-timestamp-ms", type=int, default=None, help="Cover frame timestamp in milliseconds")
    args = parser.parse_args()

    body = build_request_from_args(args)
    resp = api_post(BATCHCREATE_SCHEDULE_TASK_PATH, body)
    data = parse_response(resp)
    print(json.dumps(build_debug_output(resp, data), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
