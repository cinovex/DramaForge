#!/usr/bin/env python3
"""Save a Pippit access key to the local reusable skill cache."""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _common import ACCESS_KEY_STORAGE_KEY, DEFAULT_ACCESS_KEY_FILE, save_access_key


def main():
    parser = argparse.ArgumentParser(
        description="Save a Pippit access key locally under the PippitAccessKey key.",
        epilog="""
Priority:
  1. --access-key
  2. PIPPIT_ACCESS_KEY
  3. PippitAccessKey

Examples:
  python3 save_access_key.py --access-key 'ak_xxx'
  PIPPIT_ACCESS_KEY='ak_xxx' python3 save_access_key.py
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--access-key", default="", help="Access key to save")
    parser.add_argument(
        "--path",
        default=DEFAULT_ACCESS_KEY_FILE,
        help="Cache file path. Defaults to $CODEX_HOME/pippit-skill/secrets.json",
    )
    args = parser.parse_args()

    access_key = (
        args.access_key.strip()
        or os.environ.get("PIPPIT_ACCESS_KEY", "").strip()
        or os.environ.get(ACCESS_KEY_STORAGE_KEY, "").strip()
    )
    if not access_key:
        print("Error: provide an access key through --access-key or an environment variable", file=sys.stderr)
        sys.exit(1)

    path = save_access_key(access_key, args.path)
    print(
        json.dumps(
            {
                "saved": True,
                "key_name": ACCESS_KEY_STORAGE_KEY,
                "path": path,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
