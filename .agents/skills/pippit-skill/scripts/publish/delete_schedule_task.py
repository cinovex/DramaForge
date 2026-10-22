#!/usr/bin/env python3
"""Delete social publishing tasks: POST /api/biz/v1/publish/skill/delete_schedule_task"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _common import DELETE_SCHEDULE_TASK_PATH, TASK_TYPE_PUBLISH_MEDIA, api_post, load_json_args, parse_response


def main():
    parser = argparse.ArgumentParser(description="Delete Pippit social publishing tasks")
    parser.add_argument("--request-json", default="", help="Pass the full request JSON directly")
    parser.add_argument("--request-file", default="", help="Read the full request JSON from a file")
    parser.add_argument("--ids", nargs="+", default=[], help="Task IDs; may be repeated")
    args = parser.parse_args()

    body = load_json_args(args.request_json, args.request_file)
    if not body:
        if not args.ids:
            print("Error: at least one --ids value is required", file=sys.stderr)
            sys.exit(1)
        body = {"task_type": TASK_TYPE_PUBLISH_MEDIA, "ids": args.ids}

    data = parse_response(api_post(DELETE_SCHEDULE_TASK_PATH, body))
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
