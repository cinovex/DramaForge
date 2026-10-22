#!/usr/bin/env python3
"""List social content analytics data: POST /api/biz/v1/analytics/skill/videos"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _common import LIST_VIDEOS_PATH, api_post, build_account_list, load_json_args, parse_response


def main():
    parser = argparse.ArgumentParser(
        description="List Pippit social video analytics data; use --request-file for complex filters",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--request-json", default="", help="Pass the full request JSON directly")
    parser.add_argument("--request-file", default="", help="Read the full request JSON from a file")
    parser.add_argument("--start-time-sec", type=int, default=0, help="Start timestamp in seconds")
    parser.add_argument("--end-time-sec", type=int, default=0, help="End timestamp in seconds")
    parser.add_argument("--platform", choices=["tiktok", "facebook", "facebook-page", "instagram", "ins"], default="", help="Target platform")
    parser.add_argument("--platform-user-id", nargs="+", default=[], help="Platform account ID; may be repeated")
    parser.add_argument("--force-refresh", action="store_true", help="Force analytics data refresh")
    args = parser.parse_args()

    body = load_json_args(args.request_json, args.request_file)
    if not body:
        body = {}
        if args.start_time_sec:
            body["start_time_sec"] = args.start_time_sec
        if args.end_time_sec:
            body["end_time_sec"] = args.end_time_sec
        if args.platform and args.platform_user_id:
            body["account_list"] = build_account_list(args.platform, args.platform_user_id)
        if args.force_refresh:
            body["force_refresh"] = True

    data = parse_response(api_post(LIST_VIDEOS_PATH, body))
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
