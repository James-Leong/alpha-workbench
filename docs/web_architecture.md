# AlphaWorkbench Web 架构

本文档记录产品级网站外壳的实现边界。核心因子研报工作流仍由现有 `alpha_workbench/workflows/` 承担，后续单独优化。

## 技术栈

- 后端：FastAPI
- 前端：React + Vite + TypeScript
- 数据库：本地 SQLite
- ORM：SQLModel
- 认证：账号密码 + GitHub OAuth
- 会话：服务端 session 表 + HttpOnly Cookie

## 目录

```text
alpha_workbench/api/
  main.py              FastAPI app 入口
  config.py            Web/API 环境变量
  db.py                SQLModel engine 与初始化
  models.py            用户、会话、OAuth、研究记录模型
  schemas.py           API 请求/响应模型
  auth/                密码哈希与 session helpers
  routers/
    auth.py            注册、登录、退出、GitHub OAuth
    research.py        研究项目、workflow 执行、trace 读取

frontend/
  src/
    api/client.ts      API 客户端
    pages/             登录、注册、dashboard、研究页、设置页
    components/        产品外壳组件
```

## 模块边界

- FastAPI 只负责产品外壳、认证、持久化和 API 编排。
- React 只负责产品页面和用户交互，不直接访问 SQLite。
- `run_demo_workflow()` 是当前唯一研究执行入口。
- Streamlit 仍可作为内部 demo/debug 入口，不作为产品主站。

## 本地启动

```bash
uv sync --extra dev
./scripts/start_api.sh
./scripts/start_frontend.sh
```

前端默认访问 `http://localhost:5173`，后端默认访问 `http://localhost:8000`。

`frontend/.npmrc` 已固定使用 `https://registry.npmmirror.com/`，便于国内环境安装前端依赖。
