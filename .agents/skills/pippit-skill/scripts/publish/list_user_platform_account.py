#!/usr/bin/env python3
"""List the current user's bound platform accounts: POST /api/biz/v1/common/skill/list_user_platform_account"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _common import LIST_USER_PLATFORM_ACCOUNT_PATH, api_post, parse_response


def main():
    data = parse_response(api_post(LIST_USER_PLATFORM_ACCOUNT_PATH, {}))
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
