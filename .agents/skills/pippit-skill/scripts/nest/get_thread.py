#!/usr/bin/env python3
"""Poll Pippit Nest Agent progress: POST /api/biz/v1/skill/get_thread."""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _common import (
    extract_download_urls_from_messages,
    extract_entries_from_run,
    extract_generated_assets_from_messages,
    extract_interactions_from_messages,
    get_run_status,
    get_thread,
)


def main():
    parser = argparse.ArgumentParser(
        description="Fetch messages and artifacts for a Pippit Nest Agent run.",
        epilog="""
Environment:
  PIPPIT_ACCESS_KEY or PippitAccessKey  Optional if a local PippitAccessKey is already saved
  PIPPIT_OPENAPI_BASE or PIPPIT_BASE_URL  Optional, default https://www.pippit.ai

Example:
  python3 get_thread.py --thread-id THREAD_ID --run-id RUN_ID --after-seq 0
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--thread-id", required=True, help="Thread ID returned by submit_run.py")
    parser.add_argument("--run-id", required=True, help="Run ID returned by submit_run.py")
    parser.add_argument(
        "--after-seq",
        type=int,
        default=0,
        help="Return entries at or after this sequence cursor. Defaults to 0.",
    )
    args = parser.parse_args()

    run = get_thread(args.thread_id, run_id=args.run_id, after_seq=args.after_seq)
    messages = extract_entries_from_run(run)
    downloads = extract_download_urls_from_messages(messages)
    generated_assets = extract_generated_assets_from_messages(messages)
    status = get_run_status(run)
    output = {
        "status": status,
        "messages": messages,
        "download_urls": [item["url"] for item in downloads],
    }
    if status == "requires_action":
        output["status_detail"] = "clarification_or_interaction_required"
    if downloads:
        output["downloads"] = downloads
    if generated_assets:
        output["generated_assets"] = generated_assets
    interactions = extract_interactions_from_messages(messages)
    if interactions:
        output["interactions"] = interactions
    elif status == "requires_action":
        hints = extract_requires_action_hints(messages)
        if hints:
            output["requires_action_hints"] = hints
    print(json.dumps(output, ensure_ascii=False, indent=2))


def extract_requires_action_hints(messages):
    hints = {"assistant_texts": [], "pending_tool_calls": []}
    for message in messages:
        if message.get("role") != "assistant":
            continue
        for content in message.get("content", []) or []:
            if not isinstance(content, dict):
                continue
            content_type = content.get("type", "")
            sub_type = content.get("sub_type") or content.get("subtype") or ""
            data = content.get("data")
            if content_type == "text" and isinstance(data, str) and data.strip():
                hints["assistant_texts"].append(data.strip())
            if sub_type == "tool_call_req" and isinstance(data, str):
                try:
                    decoded = json.loads(data)
                except json.JSONDecodeError:
                    decoded = {}
                tool_name = decoded.get("tool_name")
                if tool_name:
                    hints["pending_tool_calls"].append(tool_name)
    hints["assistant_texts"] = dedupe_keep_order(hints["assistant_texts"])[-5:]
    hints["pending_tool_calls"] = dedupe_keep_order(hints["pending_tool_calls"])
    return {key: value for key, value in hints.items() if value}


def dedupe_keep_order(values):
    output = []
    seen = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


if __name__ == "__main__":
    main()
