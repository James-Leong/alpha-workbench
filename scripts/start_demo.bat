@echo off
setlocal

set ROOT_DIR=%~dp0..
cd /d "%ROOT_DIR%"

where uv >nul 2>nul
if errorlevel 1 (
  echo uv is required. Install it first: https://docs.astral.sh/uv/getting-started/installation/
  exit /b 1
)

if "%ALPHA_WORKBENCH_PORT%"=="" set ALPHA_WORKBENCH_PORT=8501

uv sync
uv run streamlit run alpha_workbench/app/streamlit_app.py --server.address 127.0.0.1 --server.port %ALPHA_WORKBENCH_PORT% --server.headless true

endlocal
