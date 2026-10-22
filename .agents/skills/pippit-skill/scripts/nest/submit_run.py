#!/usr/bin/env python3
"""Submit a Pippit Nest Agent run: POST /api/biz/v1/skill/submit_run."""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _common import build_web_thread_link, submit_run


def main():
    parser = argparse.ArgumentParser(
        description="Create a new Pippit Nest Agent thread/run or append a message to an existing thread.",
        epilog="""
Environment:
  PIPPIT_ACCESS_KEY or PippitAccessKey  Optional if a local PippitAccessKey is already saved
  PIPPIT_OPENAPI_BASE or PIPPIT_BASE_URL  Optional, default https://www.pippit.ai
  PIPPIT_HOME_URL  Optional, default https://www.pippit.ai/home?

Examples:
  python3 submit_run.py --message "Create a cinematic product video"
  python3 submit_run.py --thread-id THREAD_ID --message "Make it faster"
  python3 submit_run.py --message "Use these references" --asset-ids asset123 asset456
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--message", required=True, help="User's original creative request")
    parser.add_argument("--thread-id", default="", help="Existing thread ID. Omit to create a new thread.")
    parser.add_argument("--asset-ids", nargs="+", default=[], help="Reference asset IDs returned by upload_file.py")
    args = parser.parse_args()

    data = submit_run(
        thread_id=args.thread_id or "",
        message=args.message or "",
        asset_ids=args.asset_ids if args.asset_ids else None,
    )
    run_data = data.get("run", {})
    thread_id = run_data.get("thread_id", "")
    run_id = run_data.get("run_id", "")
    web_thread_link = data.get("web_thread_link", "") or build_web_thread_link(thread_id)

    if not thread_id:
        print("Error: response did not include run.thread_id", file=sys.stderr)
        sys.exit(1)
    if not run_id:
        print("Error: response did not include run.run_id", file=sys.stderr)
        sys.exit(1)

    print(
        json.dumps(
            {
                "thread_id": thread_id,
                "run_id": run_id,
                "web_thread_link": web_thread_link,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
