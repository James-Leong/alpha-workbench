#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required. Install it first: https://docs.astral.sh/uv/getting-started/installation/"
  exit 1
fi

uv sync
uv run streamlit run alpha_workbench/app/streamlit_app.py \
  --server.address 127.0.0.1 \
  --server.port "${ALPHA_WORKBENCH_PORT:-8501}" \
  --server.headless true
