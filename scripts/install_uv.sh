#!/usr/bin/env bash
# 中国国内环境 uv 安装脚本
set -euo pipefail

echo "========================================"
echo "uv 安装脚本 (中国国内环境)"
echo "========================================"

# 检查是否已安装 uv
if command -v uv >/dev/null 2>&1; then
  CURRENT_VERSION=$(uv --version)
  echo "✓ uv 已安装: $CURRENT_VERSION"
  read -p "是否要重新安装? (y/n) " -n 1 -r
  echo
  if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "已跳过安装"
    exit 0
  fi
fi

echo "开始安装 uv..."
echo ""

# 方案1: 使用 GitHub 代理加速官方安装脚本
echo "方案1: 使用 ghproxy 加速下载官方安装脚本..."
if curl -fsSL https://ghproxy.com/https://raw.githubusercontent.com/astral-sh/uv/main/scripts/install/install.sh | sh; then
  echo ""
  echo "✓ uv 安装成功!"
  
  # 添加 $HOME/.cargo/bin 到 PATH（如果需要）
  if [[ ":$PATH:" != *":$HOME/.cargo/bin:"* ]]; then
    echo ""
    echo "提示: 请将以下内容添加到 ~/.bashrc 或 ~/.zshrc:"
    echo "  export PATH=\"\$HOME/.cargo/bin:\$PATH\""
    echo ""
    echo "或运行: source \$HOME/.cargo/env"
  fi
  
  source $HOME/.cargo/env 2>/dev/null || true
  
  echo "验证安装..."
  uv --version
  exit 0
fi

# 方案2: 使用 pip + 国内镜像
echo ""
echo "方案1 失败，尝试方案2: 使用 pip (国内镜像)..."

# 检查 Python 和 pip
if ! command -v python3 >/dev/null 2>&1; then
  echo "✗ 找不到 Python 3，请先安装 Python"
  exit 1
fi

PYTHON_CMD="python3"
PIP_CMD="$PYTHON_CMD -m pip"

echo "使用 Python: $($PYTHON_CMD --version)"
echo ""

# 配置国内镜像源并安装 uv
echo "配置国内镜像源安装 uv..."
$PIP_CMD install -i https://pypi.tsinghua.edu.cn/simple uv

if command -v uv >/dev/null 2>&1; then
  echo ""
  echo "✓ uv 安装成功!"
  uv --version
else
  echo "✗ uv 安装失败，请检查网络连接或尝试手动安装"
  echo "参考: https://docs.astral.sh/uv/getting-started/installation/"
  exit 1
fi
