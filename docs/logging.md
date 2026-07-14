# AlphaWorkbench 日志与配置说明

## 日志模块

项目使用 `alpha_workbench/core/logging.py` 统一初始化标准库 `logging`，所有模块仍按惯例使用：

```python
import logging
logger = logging.getLogger(__name__)
```

### 默认输出

默认情况下，日志写入项目根目录的 `logs/` 文件夹：

| 文件 | 格式 | 内容 |
|---|---|---|
| `logs/app.log` | 纯文本 | 所有 `>= LOG_LEVEL` 的日志 |
| `logs/app.jsonl` | JSON Lines | 所有 `>= LOG_LEVEL` 的日志，便于采集分析 |
| `logs/error.log` | 纯文本 | 仅 `ERROR` 及以上级别 |

### 环境变量

| 变量 | 说明 | 默认值 |
|---|---|---|
| `LOG_LEVEL` | 日志级别（DEBUG/INFO/WARNING/ERROR） | `INFO` |
| `ALPHA_LOG_LEVEL` | `LOG_LEVEL` 的兼容别名 | 无 |
| `LOG_TO_CONSOLE` | 是否同时输出到 stderr | `false` |
| `LOG_TO_FILE` | 是否写入文件 | `true` |
| `LOG_JSON_ENABLED` | 是否生成 JSON Lines 文件 | `true` |
| `LOG_DIR` | 日志目录 | `<项目根目录>/logs` |
| `LOG_ROTATION_MAX_BYTES` | 单个日志文件大小上限（字节） | `10485760`（10 MB） |
| `LOG_ROTATION_BACKUP_COUNT` | 保留的轮转备份数 | `5` |

### 与 research run 日志的关系

研究流程的运行时审计日志统一使用同样的 `logging` 框架，输出到：

```text
runs/research_runs/run_{run_id}.jsonl
```

该文件仅用于后端排查和审计，**不再返回给前端**。前端进度展示通过 `/api/research/projects/{id}/progress` 从数据库 `ResearchRun.progress_events` 读取。

运行审计 logger 通过 `alpha_workbench.core.logging.get_run_logger(run_id)` 获取，它向上隔离（`propagate=False`），不会污染全局 `logs/app.jsonl`。

## 运行时产物目录

除日志外，所有按运行生成的产物也统一放在 `runs/` 下：

| 目录 | 内容 | 是否应提交 |
|---|---|---|
| `runs/factor_code_jobs/` | Codex 实时生成的因子插件任务目录 | 否 |
| `runs/factor_plugins/` | 通过验证后提升的插件注册表 | 否 |
| `runs/research_runs/` | 研究运行审计日志（JSON Lines） | 否 |

`data/` 目录仅保留持久化数据（如 SQLite 数据库文件），不再存放运行时产物。

## 配置分类

项目采用 `pydantic-settings` 管理环境变量，配置按功能分为多个嵌套类：

```text
Settings
├── app
├── logging
├── database
├── api
├── auth
├── llm
├── vision_llm
├── mercury
├── factor_code
├── review
└── reference
```

### 常用访问方式

新代码推荐按分类访问：

```python
from alpha_workbench.core.config import settings

print(settings.logging.level)
print(settings.database.url)
print(settings.api.allowed_origins)
```

为兼容旧代码，顶层 `Settings` 也保留了扁平属性，例如：

```python
settings.log_level        # -> settings.logging.level
settings.database_url     # -> settings.database.url
settings.allowed_origins  # -> settings.api.allowed_origins
settings.llm_api_key      # -> settings.llm.api_key
```

### 单例

进程内使用 `@lru_cache` 缓存：

```python
from alpha_workbench.core.config import get_settings

s = get_settings()
```

### FastAPI 依赖注入（可选）

```python
from fastapi import Depends
from alpha_workbench.core.config import Settings, get_settings

@app.get("/info")
def info(settings: Settings = Depends(get_settings)):
    return {"app_name": settings.app.name}
```

## 本地开发建议

- 复制 `.env.template` 为 `.env`，按需填写真实密钥。
- 开发时若想查看控制台日志，设置 `LOG_TO_CONSOLE=true`。
- `logs/` 目录已加入 `.gitignore`，本地日志不会提交。
