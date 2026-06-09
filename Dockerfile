# 多阶段构建：builder 阶段用于安装依赖
FROM python:3.12-slim AS builder

# 设置工作目录
WORKDIR /app

# 环境变量：确保 pipx 安装的可执行文件在 PATH 中
ENV PATH="/root/.local/bin:$PATH"

# 配置阿里云源
RUN echo "deb https://mirrors.aliyun.com/debian bookworm main non-free non-free-firmware contrib" > /etc/apt/sources.list && \
    echo "deb https://mirrors.aliyun.com/debian bookworm-updates main non-free non-free-firmware contrib" >> /etc/apt/sources.list && \
    echo "deb https://mirrors.aliyun.com/debian-security bookworm-security main non-free non-free-firmware contrib" >> /etc/apt/sources.list

# 安装 pipx 和 uv
RUN \
    apt-get update && \
    apt-get install -y --no-install-recommends pipx && \
    pipx ensurepath && \
    rm -rf /var/lib/apt/lists/* && \
    pipx install uv

# 复制项目文件
COPY pyproject.toml uv.lock* ./
COPY alpha_workbench/ ./alpha_workbench/
COPY tests/ ./tests/

# 使用 uv 安装依赖到虚拟环境
# RUN uv sync --no-dev --frozen --no-cache
RUN uv sync --no-dev --no-cache

# 最终阶段：运行镜像
FROM python:3.12-slim

# 配置阿里云源
RUN echo "deb https://mirrors.aliyun.com/debian bookworm main non-free non-free-firmware contrib" > /etc/apt/sources.list && \
    echo "deb https://mirrors.aliyun.com/debian bookworm-updates main non-free non-free-firmware contrib" >> /etc/apt/sources.list && \
    echo "deb https://mirrors.aliyun.com/debian-security bookworm-security main non-free non-free-firmware contrib" >> /etc/apt/sources.list

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PATH="/app/.venv/bin:$PATH"

# 设置工作目录
WORKDIR /app

# 从 builder 阶段复制产物
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/alpha_workbench /app/alpha_workbench
COPY --from=builder /app/pyproject.toml /app/pyproject.toml

# 暴露 Streamlit 默认端口
EXPOSE 8501

# 默认运行 Streamlit UI
CMD ["streamlit", "run", "alpha_workbench/app/streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0"]
