# Docker 快速启动指南

## 快速开始

### 1. 使用 docker-compose 启动（推荐）

```bash
# 构建镜像并启动服务
docker-compose up --build

# 后台启动
docker-compose up -d --build

# 查看日志
docker-compose logs -f app
```

Streamlit UI 将在 `http://localhost:8501` 上可访问。

### 2. 直接使用 Docker 构建和运行

```bash
# 构建镜像
docker build -t alpha-workbench:latest .

# 运行 Streamlit 服务
docker run -p 8501:8501 \
  -v $(pwd)/runs:/app/runs \
  -v $(pwd)/alpha_workbench/data:/app/alpha_workbench/data \
  alpha-workbench:latest

# 运行 CLI demo
docker run -it \
  -v $(pwd)/runs:/app/runs \
  alpha-workbench:latest \
  alpha-workbench-demo --save-trace
```

## 项目结构

- `Dockerfile` - 使用多阶段构建优化镜像大小
- `docker-compose.yaml` - 服务编排配置
- `.dockerignore` - 忽略不必要的文件

## Docker 镜像特性

- **基础镜像**: Python 3.12-slim（轻量级）
- **包管理**: 使用 `uv` 加速依赖安装
- **多阶段构建**: 减少最终镜像大小
- **卷挂载**: 支持本地数据和运行结果持久化

## 常用命令

```bash
# 停止服务
docker-compose down

# 清理未使用的资源
docker-compose down --volumes

# 重新构建镜像（不使用缓存）
docker-compose build --no-cache

# 进入容器内部
docker-compose exec app /bin/bash

# 查看镜像大小
docker images alpha-workbench

# 查看容器运行状态
docker-compose ps
```

## 故障排查

### Streamlit 连接被拒绝
确保 `--server.address=0.0.0.0` 已设置以允许外部连接。

### 依赖安装失败
检查网络连接和 pyproject.toml 中的依赖配置。

### 挂载卷权限错误
在 Linux 上，可能需要调整目录权限：
```bash
chmod -R 755 ./runs ./alpha_workbench/data
```

## 生产部署建议

- 使用 Docker 私有仓库存储镜像
- 配置环境变量管理敏感信息
- 使用 Kubernetes 或 Docker Swarm 进行编排
- 添加资源限制和健康检查
- 配置日志收集和监控
