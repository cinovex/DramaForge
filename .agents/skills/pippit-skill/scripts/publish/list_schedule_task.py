#!/usr/bin/env python3
"""List social publishing tasks: POST /api/biz/v1/publish/skill/list_schedule_task"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _common import LIST_SCHEDULE_TASK_PATH, api_post, default_list_window_ms, normalize_statuses, parse_publish_time, parse_response, platform_code


def main():
    parser = argparse.ArgumentParser(
        description="List Pippit social publishing tasks; --platform and --platform-user-id are required. The default time window is from 30 days ago to 31 days from now.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--start-time", default="", help="Start time; supports millisecond timestamp or ISO8601")
    parser.add_argument("--end-time", default="", help="End time; supports millisecond timestamp or ISO8601")
    parser.add_argument("--platform", choices=["tiktok", "facebook", "facebook-page", "instagram", "ins"], default="", help="Target platform")
    parser.add_argument("--platform-user-id", nargs="+", default=[], help="Platform account ID; may be repeated")
    parser.add_argument("--status", nargs="+", default=[], help="Task status, such as pending done failed")
    args = parser.parse_args()

    if not args.platform or not args.platform_user_id:
        print("Error: task queries require both --platform and --platform-user-id; time-window-only queries often return an empty array", file=sys.stderr)
        sys.exit(1)

    default_start, default_end = default_list_window_ms()
    body = {
        "start_time": parse_publish_time(args.start_time) if args.start_time else default_start,
        "end_time": parse_publish_time(args.end_time) if args.end_time else default_end,
    }
    body["platform_user_ids"] = {str(platform_code(args.platform)): args.platform_user_id}
    if args.status:
        body["status_list"] = normalize_statuses(args.status)

    data = parse_response(api_post(LIST_SCHEDULE_TASK_PATH, body))
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
