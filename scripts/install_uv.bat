@echo off
REM 中国国内环境 uv 安装脚本 (Windows)
setlocal enabledelayedexpansion

echo.
echo ========================================
echo uv 安装脚本 (中国国内环境 - Windows)
echo ========================================
echo.

REM 检查是否已安装 uv
where uv >nul 2>nul
if errorlevel 1 (
  echo uv 未安装，开始安装...
) else (
  for /f "tokens=*" %%i in ('uv --version') do set CURRENT_VERSION=%%i
  echo ✓ uv 已安装: !CURRENT_VERSION!
  set /p REINSTALL="是否要重新安装? (y/n): "
  if /i not "!REINSTALL!"=="y" (
    echo 已跳过安装
    exit /b 0
  )
)

echo.
echo 开始安装 uv (使用国内镜像源)...
echo.

REM 检查 Python
python --version >nul 2>nul
if errorlevel 1 (
  echo ✗ 找不到 Python，请先安装 Python
  exit /b 1
)

for /f "tokens=*" %%i in ('python --version') do set PYTHON_VERSION=%%i
echo 使用 Python: !PYTHON_VERSION!
echo.

REM 使用国内镜像安装 uv
echo 配置国内镜像源安装 uv (清华大学镜像源)...
python -m pip install -i https://pypi.tsinghua.edu.cn/simple uv

REM 验证安装
where uv >nul 2>nul
if errorlevel 1 (
  echo.
  echo ✗ uv 安装失败，请检查网络连接
  echo.
  echo 其他镜像源选项:
  echo   - 阿里云: https://mirrors.aliyun.com/pypi/simple
  echo   - 豆瓣: https://pypi.doubanio.com/simple
  echo.
  echo 手动安装命令:
  echo   python -m pip install -i https://mirrors.aliyun.com/pypi/simple uv
  exit /b 1
) else (
  echo.
  echo ✓ uv 安装成功!
  echo.
  uv --version
)

endlocal
