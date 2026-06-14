"""Run helper for role3 to invoke the Agno workflow (development).

This script mirrors `scripts/run_role3_huawei.py` but runs the local Role 3
Agno workflow so the workflow boundary stays stable.
"""

from __future__ import annotations

import argparse
import os
import json
import sys

from role3.workflow import run_role3_workflow


def main() -> int:
    p = argparse.ArgumentParser(description="Run the Role 3 Agno workflow for idea extraction")
    p.add_argument("--url", required=True, help="Full model invocation URL from Huawei API doc")
    p.add_argument("--input", required=True, help="Input text describing the investment idea")
    p.add_argument("--token", default=None, help="Bearer token (fallback to HUAWEI_TOKEN env var)")
    args = p.parse_args()

    token = args.token or os.environ.get("HUAWEI_TOKEN")
    if not token:
        print("Error: token must be provided via --token or HUAWEI_TOKEN environment variable", file=sys.stderr)
        return 2

    try:
        resp = run_role3_workflow(input_text=args.input, api_url=args.url, token=token)
    except Exception as e:
        print("Call failed:", e, file=sys.stderr)
        return 3

    print(json.dumps(resp, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
