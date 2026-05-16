"""Command line entry point for the mock AlphaWorkbench demo."""

from __future__ import annotations

import argparse
import json

from alpha_workbench.workflows.demo_workflow import DEFAULT_INPUT, run_demo_workflow


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the AlphaWorkbench mock demo workflow.")
    parser.add_argument("--input", default=DEFAULT_INPUT, help="Investment idea text.")
    parser.add_argument("--save-trace", action="store_true", help="Persist the trace under runs/.")
    args = parser.parse_args()

    trace = run_demo_workflow(args.input, save_trace=args.save_trace)
    print(json.dumps(trace, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
