#!/usr/bin/env bash
set -euo pipefail

uv run uvicorn alpha_workbench.api.main:app --host 0.0.0.0 --port 8000 --reload
