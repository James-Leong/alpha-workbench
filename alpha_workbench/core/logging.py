"""AlphaWorkbench 统一日志模块。

基于 Python 标准库 logging 实现：
- 文本日志 app.log（人可读）
- 结构化日志 app.jsonl（JSON Lines，便于采集分析）
- 错误日志 error.log（仅 ERROR 及以上）
- 可选控制台输出

所有配置来自 alpha_workbench.core.config.Settings.logging。
"""

from __future__ import annotations

import json
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from alpha_workbench.core.config import Settings, get_settings


_TEXT_FMT = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"
_CONFIGURED = False

# logging.LogRecord 内置字段，JSON formatter 之外额外字段不覆盖这些键
_RESERVED_RECORD_KEYS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "message",
    "asctime",
    "taskName",
}


class JsonFormatter(logging.Formatter):
    """把 LogRecord 序列化为 JSON Lines。"""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, datefmt=_DATE_FMT),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "funcName": record.funcName,
            "lineno": record.lineno,
            "thread": record.thread,
            "process": record.process,
        }

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        # 透传 logger.info(..., extra={"key": "value"}) 里的额外字段
        for key, value in record.__dict__.items():
            if key in _RESERVED_RECORD_KEYS:
                continue
            payload[key] = value

        return json.dumps(payload, ensure_ascii=False, default=str)


def _resolve_level(name: str) -> int:
    level = logging.getLevelName(name.upper())
    return level if isinstance(level, int) else logging.INFO


def configure_logging(settings: Settings | None = None, force: bool = False) -> None:
    """配置项目全局日志。

    幂等调用：同进程内重复调用不会重复附加 handler，除非 force=True。
    """

    global _CONFIGURED
    if _CONFIGURED and not force:
        return

    cfg = (settings or get_settings()).logging
    log_level = _resolve_level(cfg.level)

    log_dir = cfg.dir
    if log_dir is None:
        log_dir = Path(__file__).resolve().parents[2] / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(log_level)

    if force:
        for handler in list(root.handlers):
            root.removeHandler(handler)

    text_formatter = logging.Formatter(_TEXT_FMT, datefmt=_DATE_FMT)

    if cfg.to_console:
        console = logging.StreamHandler(sys.stderr)
        console.setLevel(log_level)
        console.setFormatter(text_formatter)
        root.addHandler(console)

    if cfg.to_file:
        max_bytes = cfg.rotation_max_bytes
        backup_count = cfg.rotation_backup_count

        app_handler = RotatingFileHandler(
            log_dir / "app.log",
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        app_handler.setLevel(log_level)
        app_handler.setFormatter(text_formatter)
        root.addHandler(app_handler)

        if cfg.json_enabled:
            json_handler = RotatingFileHandler(
                log_dir / "app.jsonl",
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
            json_handler.setLevel(log_level)
            json_handler.setFormatter(JsonFormatter())
            root.addHandler(json_handler)

        error_handler = RotatingFileHandler(
            log_dir / "error.log",
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(text_formatter)
        root.addHandler(error_handler)

    # 非 DEBUG 模式下降低第三方库噪音
    if log_level > logging.DEBUG:
        for noisy in ("httpx", "httpcore", "urllib3"):
            logging.getLogger(noisy).setLevel(logging.WARNING)

    _CONFIGURED = True


def get_run_logger(run_id: int) -> logging.Logger:
    """返回单个研究运行的专用 logger。

    输出到 ``runs/research_runs/run_{run_id}.jsonl``，使用 JSON Lines 结构化格式，
    且不会向上传播到 root logger，避免污染全局应用日志。
    """
    name = f"research.run.{run_id}"
    run_logger = logging.getLogger(name)
    if getattr(run_logger, "_run_logger_configured", False):
        return run_logger

    cfg = get_settings().logging
    runs_dir = get_settings().base_dir / "runs" / "research_runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    handler = RotatingFileHandler(
        runs_dir / f"run_{run_id}.jsonl",
        maxBytes=cfg.rotation_max_bytes,
        backupCount=cfg.rotation_backup_count,
        encoding="utf-8",
    )
    handler.setFormatter(JsonFormatter())
    handler.setLevel(logging.INFO)

    run_logger.addHandler(handler)
    run_logger.setLevel(logging.INFO)
    run_logger.propagate = False
    run_logger._run_logger_configured = True  # type: ignore[attr-defined]
    return run_logger


def get_logger(name: str) -> logging.Logger:
    """返回以 name 命名的 logger（保持项目统一风格）。"""
    return logging.getLogger(name)
