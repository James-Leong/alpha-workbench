"""CLI helper for running the isolated Role3 workflow."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from role3.workflow import run_role3_workflow


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Role3 idea extraction.")
    parser.add_argument("--input", required=True, help="Input idea text or PDF path.")
    parser.add_argument("--url", default=None, help="Model invocation URL.")
    parser.add_argument("--token", default=None, help="Bearer token; defaults to HUAWEI_TOKEN.")
    parser.add_argument("--source-type", choices=["text", "pdf"], default="text")
    args = parser.parse_args()

    result = run_role3_workflow(
        input_text=args.input,
        source_meta={"source_type": args.source_type},
        api_url=args.url,
        token=args.token or os.environ.get("HUAWEI_TOKEN"),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
