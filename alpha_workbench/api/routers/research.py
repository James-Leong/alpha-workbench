"""Research project API routes."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime
from threading import Thread
import time
import traceback
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import ValidationError
from sqlmodel import Session, select

from alpha_workbench.api.auth.sessions import get_current_user, verify_csrf
from alpha_workbench.api.db import engine, get_db
from alpha_workbench.api.models import ResearchProject, ResearchRun, ResearchTrace, User, utcnow
from alpha_workbench.api.schemas import (
    ResearchProjectCreate,
    ResearchProjectDetail,
    ResearchRunProgress,
    ResearchProjectSummary,
    ResearchSpecUpdate,
)
from alpha_workbench.agents.idea_extractor import extract_idea
from alpha_workbench.core.config import settings as core_settings
from alpha_workbench.core.logging import get_run_logger
from alpha_workbench.memory.research_trace import _safe_json_default
from alpha_workbench.workflows.demo_workflow import build_research_spec, run_resume_workflow, _parse_holding_period


def _update_research_spec(trace: dict[str, Any], update: ResearchSpecUpdate) -> dict[str, Any]:
    """Merge user edits into the research_spec portion of a trace."""
    research = dict(trace.get("research_spec") or {})
    if update.universe is not None:
        research["universe"] = update.universe
    if update.rebalance_frequency is not None:
        research["rebalance_frequency"] = update.rebalance_frequency.strip().lower()
    if update.holding_period is not None:
        research["holding_period"] = update.holding_period
    if update.transaction_cost_bps is not None:
        research["transaction_cost_bps"] = update.transaction_cost_bps
    if update.benchmark is not None:
        research["benchmark"] = update.benchmark
    if update.initial_cash is not None:
        research["initial_cash"] = update.initial_cash
    if update.sample_window_start is not None or update.sample_window_end is not None:
        sample_window = dict(research.get("sample_window") or {})
        if update.sample_window_start is not None:
            sample_window["start"] = update.sample_window_start
        if update.sample_window_end is not None:
            sample_window["end"] = update.sample_window_end
        research["sample_window"] = sample_window
    if update.filters is not None:
        research["filters"] = update.filters
    if update.factor_execution_mode is not None:
        factor_execution = dict(research.get("factor_execution") or {})
        factor_execution["mode"] = update.factor_execution_mode
        factor_execution["code_agent"] = "codex"
        research["factor_execution"] = factor_execution

    # Sync backtest sub-config with top-level values
    backtest = dict(research.get("backtest") or {})
    if "rebalance_frequency" in research:
        backtest["rebalance_frequency"] = research["rebalance_frequency"]
    if "holding_period" in research:
        backtest["holding_period"] = _parse_holding_period(research["holding_period"])
    if "transaction_cost_bps" in research:
        backtest["transaction_cost_bps"] = research["transaction_cost_bps"]
    if "initial_cash" in research:
        backtest["initial_cash"] = research["initial_cash"]
    research["backtest"] = backtest

    trace = dict(trace)
    trace["research_spec"] = research
    return trace


router = APIRouter(prefix="/api/research", tags=["research"])
logger = logging.getLogger(__name__)


INITIAL_PROGRESS = [
    {
        "step": "创建研究任务",
        "status": "completed",
        "message": "已收到研究想法，准备进入智能研读。",
    },
    {
        "step": "智能研读",
        "status": "completed",
        "message": "已提炼投资假设，请确认研究配置。",
    },
]


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=_safe_json_default))


def _run_log_path(run_id: int) -> str:
    log_dir = core_settings.base_dir / "runs" / "research_runs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return str(log_dir / f"run_{run_id}.jsonl")


def _append_run_log(
    run_id: int,
    event: str,
    *,
    project_id: int | None = None,
    stage: str = "",
    message: str = "",
    extra: dict[str, Any] | None = None,
    exc: BaseException | None = None,
) -> str:
    """追加一条结构化事件到研究运行审计日志。

    事件统一通过标准 ``logging`` 写入 ``runs/research_runs/run_{run_id}.jsonl``，
    不再使用裸文件写入。
    """
    path = _run_log_path(run_id)
    run_logger = get_run_logger(run_id)
    payload: dict[str, Any] = {
        "event": event,
        "stage": stage,
        "project_id": project_id,
        "run_id": run_id,
    }
    if message:
        payload["run_message"] = message[:4000]
    if extra:
        payload["extra"] = _json_safe(extra)
    if exc is not None:
        payload["error_type"] = type(exc).__name__
        payload["traceback_tail"] = "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        )[-8000:]
    try:
        run_logger.info(message or event, extra=payload)
    except Exception:
        logger.exception("failed to append run log for run_id=%s", run_id)
    return path


def _diagnostic_payload(
    *,
    stage: str,
    project: ResearchProject | None,
    run: ResearchRun | None,
    message: str,
    exc: BaseException | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "stage": stage,
        "message": message[:4000],
        "time": utcnow().isoformat(timespec="seconds"),
        "project_id": project.id if project is not None else None,
        "run_id": run.id if run is not None else None,
        "project_status": project.status if project is not None else None,
        "run_status": run.status if run is not None else None,
        "current_step": run.current_step if run is not None else "",
    }
    if exc is not None:
        payload["error_type"] = type(exc).__name__
        payload["traceback_tail"] = "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        )[-8000:]
    if extra:
        payload["extra"] = _json_safe(extra)
    return payload


def _append_trace_diagnostic(
    db: Session,
    trace_record: ResearchTrace | None,
    diagnostic: dict[str, Any],
) -> None:
    if trace_record is None:
        return
    trace_json = dict(trace_record.trace_json or {})
    diagnostics = [dict(item) for item in trace_json.get("workflow_diagnostics", [])]
    diagnostics.append(_json_safe(diagnostic))
    trace_json["workflow_diagnostics"] = diagnostics[-20:]
    trace_record.trace_json = _json_safe(trace_json)
    db.add(trace_record)


def _ensure_run_log_path(run_id: int) -> str:
    """返回研究运行审计日志的本地文件路径（仅用于后端排查，不暴露给前端）。"""
    return _run_log_path(run_id)


def _summary_from_trace(trace: dict[str, Any]) -> str:
    idea = trace.get("idea_spec") or {}
    if isinstance(idea, dict):
        hypothesis = (
            idea.get("core_hypothesis")
            or idea.get("hypothesis")
            or idea.get("summary")
            or idea.get("idea_name")
        )
        if hypothesis:
            return str(hypothesis)[:400]
    return "研究流程已完成。"


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _display_safe_trace(trace: dict[str, Any]) -> dict[str, Any]:
    """Normalize old trace payloads for the UI without mutating stored data."""

    safe_trace = _json_safe(trace)
    code_agent = safe_trace.get("code_agent")
    if isinstance(code_agent, dict):
        summary = str(code_agent.get("summary") or "").strip()
        if summary and not _contains_cjk(summary):
            code_agent["summary"] = (
                "已生成 AlphaWorkbench 因子插件，并完成 manifest、AST、pytest、"
                "沙箱 smoke 和未来函数扰动审计。"
            )
        risks = code_agent.get("risks")
        if isinstance(risks, list):
            code_agent["risks"] = _display_safe_risks(risks)

    backtest_result = safe_trace.get("backtest_result")
    if isinstance(backtest_result, dict):
        mercury_status = backtest_result.get("mercury_status")
        if isinstance(mercury_status, dict):
            notes = mercury_status.get("notes")
            if isinstance(notes, list):
                mercury_status["notes"] = [_display_safe_mercury_note(note) for note in notes]
            attempts = mercury_status.get("attempts")
            if isinstance(attempts, dict):
                for attempt in attempts.values():
                    if isinstance(attempt, dict) and "message" in attempt:
                        attempt["message"] = _display_safe_mercury_note(attempt["message"])
    return safe_trace


def _display_safe_risks(risks: list[Any]) -> list[str]:
    localized: list[str] = []
    for item in risks:
        text = str(item or "").strip()
        if not text:
            continue
        if _contains_cjk(text):
            localized.append(text)
            continue
        lower = text.lower()
        if any(token in lower for token in ["open", "high", "low", "close", "ohlc"]):
            localized.append(
                "当前因子在缺少完整 OHLC 字段时会使用收盘价路径代理，接入真实行情字段后需要复核上下影线口径。"
            )
        elif any(token in lower for token in ["fundamental", "announcement", "technical signal"]):
            localized.append(
                "当前生成逻辑与研究主题中的基本面字段和公告时点存在口径差异，需要在真实数据接入时确认字段契约。"
            )
        elif "test" in lower and any(token in lower for token in ["not executed", "not run"]):
            localized.append(
                "Codex 自述测试执行不完整；平台已重新执行生成 pytest、沙箱 smoke 和未来函数扰动审计。"
            )
        else:
            localized.append("生成插件仍需结合真实字段、样本窗口和交易级回测表现复核。")
    return list(dict.fromkeys(localized))


def _display_safe_mercury_note(note: Any) -> str:
    text = str(note or "").strip()
    if not text or _contains_cjk(text):
        return text
    if text.startswith("Mercury returned no result for "):
        factor_id = text.removeprefix("Mercury returned no result for ").split(";")[0].strip()
        return f"Mercury 未返回 {factor_id} 的交易级结果，已回退到本地因子分析。"
    if text.startswith("Mercury failed for "):
        detail = text.removeprefix("Mercury failed for ").replace("; used local fallback.", "")
        return f"Mercury 调用失败：{detail}；已回退到本地因子分析。"
    if text.startswith("Mercury service unavailable"):
        return "Mercury 服务不可用，已回退到本地因子分析。"
    return "Mercury 未返回可展示的交易级结果，已回退到本地因子分析。"


def _metrics_from_trace(trace: dict[str, Any]) -> dict[str, Any]:
    backtest = trace.get("backtest_result") or {}
    if not isinstance(backtest, dict):
        return {}
    metrics = backtest.get("metrics") or backtest.get("summary") or {}
    if isinstance(metrics, dict):
        return _json_safe(metrics)
    return {}


def _latest_run(db: Session, project_id: int, user_id: int) -> ResearchRun | None:
    return db.exec(
        select(ResearchRun)
        .where((ResearchRun.project_id == project_id) & (ResearchRun.user_id == user_id))
        .order_by(ResearchRun.created_at.desc())
    ).first()


def _normalize_progress_events(
    events: list[dict[str, Any]],
    project_status: str,
) -> list[dict[str, Any]]:
    """Return display-safe progress events without impossible mixed states."""

    normalized = [dict(event) for event in events]
    if project_status == "completed":
        for event in normalized:
            if event.get("status") == "running":
                event["status"] = "completed"
            if event.get("status") == "completed":
                _rewrite_completed_progress_event(event)
    elif project_status == "failed":
        for event in normalized:
            if event.get("status") == "running":
                event["status"] = "failed"
    return normalized


def _rewrite_completed_progress_event(event: dict[str, Any]) -> None:
    """Replace stale in-progress wording for already completed projects."""

    completed_text = {
        "研究执行": ("研究执行", "已进入研究执行流程。"),
        "正在生成候选因子": ("已生成候选因子", "候选因子已生成。"),
        "正在编译因子表达式": ("已编译因子表达式", "因子表达式已完成校验。"),
        "正在调用 Codex 生成并验证因子插件": (
            "已生成并验证 Codex 因子插件",
            "Codex 因子插件已生成，并完成沙箱验证。",
        ),
        "正在执行回测": ("已执行回测", "回测已完成。"),
        "正在生成回测解释": ("已生成回测解释", "回测解释已生成。"),
        "正在生成研究报告": ("已生成研究报告", "研究报告已生成。"),
        "完成": ("完成", "研究结果已生成。"),
    }
    step = str(event.get("step") or "")
    if step in completed_text:
        event["step"], event["message"] = completed_text[step]
        return

    message = str(event.get("message") or "")
    if message.startswith("正在"):
        event["message"] = message.replace("正在", "已", 1).rstrip(".。") + "。"


def _project_summary(db: Session, project: ResearchProject) -> ResearchProjectSummary:
    latest = _latest_run(db, project.id or 0, project.user_id)
    latest = _maybe_finish_stale_codex_run(db, project, latest)
    return ResearchProjectSummary(
        id=project.id or 0,
        title=project.title,
        idea_text=project.idea_text,
        status=project.status,
        summary=project.summary,
        created_at=project.created_at,
        updated_at=project.updated_at,
        latest_run_id=latest.id if latest else None,
        current_step=latest.current_step if latest else "",
        progress_events=_normalize_progress_events(
            latest.progress_events if latest else [],
            project.status,
        ),
    )


def _append_progress(db: Session, run: ResearchRun, step: str, message: str) -> None:
    events = [dict(event) for event in (run.progress_events or [])]
    for event in events:
        if event.get("status") == "running":
            event["status"] = "completed"
    events.append(
        {
            "step": step,
            "status": "running",
            "message": message,
            "time": utcnow().isoformat(timespec="seconds"),
        }
    )
    run.current_step = step
    run.progress_events = events
    project = db.get(ResearchProject, run.project_id)
    if project is not None:
        project.updated_at = utcnow()
        db.add(project)
    db.add(run)
    db.commit()
    db.refresh(run)


def _finish_progress(db: Session, run: ResearchRun, status_value: str, message: str) -> None:
    events = [dict(event) for event in (run.progress_events or [])]
    for event in events:
        if event.get("status") == "running":
            event["status"] = status_value
    events.append(
        {
            "step": "完成",
            "status": status_value,
            "message": message,
            "time": utcnow().isoformat(timespec="seconds"),
        }
    )
    run.current_step = "完成" if status_value == "completed" else "失败"
    run.progress_events = events


def _event_datetime(event: dict[str, Any]) -> datetime | None:
    raw_time = event.get("time")
    if not raw_time:
        return None
    try:
        return datetime.fromisoformat(str(raw_time))
    except ValueError:
        return None


def _stale_codex_timeout_seconds() -> int:
    return max(int(core_settings.factor_code_timeout_seconds) + 60, 900)


def _maybe_finish_stale_codex_run(
    db: Session,
    project: ResearchProject,
    run: ResearchRun | None,
) -> ResearchRun | None:
    """Fail a Codex step that outlived its worker thread/process.

    The demo API uses in-process background threads. During development, uvicorn
    reloads or interrupted Codex subprocesses can leave a run marked as running
    even though there is no worker left to update it. Keep the UI from spinning
    forever by treating an old Codex progress event as a timed-out run.
    """

    if (
        run is None
        or project.status != "running"
        or run.status != "running"
        or "Codex" not in str(run.current_step)
    ):
        return run

    running_events = [
        dict(event)
        for event in (run.progress_events or [])
        if event.get("status") == "running" and "Codex" in str(event.get("step", ""))
    ]
    if not running_events:
        return run
    started_at = _event_datetime(running_events[-1])
    if started_at is None:
        return run
    if (utcnow() - started_at).total_seconds() <= _stale_codex_timeout_seconds():
        return run

    message = (
        "Codex 因子插件生成超过超时阈值，后台 worker 已无进度更新；"
        "请重新启动研究或切换为表达式模式。"
    )
    trace_record = db.exec(select(ResearchTrace).where(ResearchTrace.run_id == run.id)).first()
    log_path = _append_run_log(
        run.id or 0,
        "stale_codex_run",
        project_id=project.id,
        stage="stale_codex_run",
        message=message,
        extra={"timeout_seconds": _stale_codex_timeout_seconds()},
    )
    _ensure_run_log_path(run.id or 0)
    _append_trace_diagnostic(
        db,
        trace_record,
        _diagnostic_payload(
            stage="stale_codex_run",
            project=project,
            run=run,
            message=message,
            extra={"timeout_seconds": _stale_codex_timeout_seconds()},
        ),
    )
    run.status = "failed"
    run.error = message
    _finish_progress(db, run, "failed", message)
    project.status = "failed"
    project.summary = f"{message} 运行日志：{log_path}"
    project.updated_at = utcnow()
    db.add(project)
    db.add(run)
    db.commit()
    db.refresh(run)
    db.refresh(project)
    return run


def _run_initial_research(
    project_id: int,
    run_id: int,
    user_id: int,
    idea_input: str,
    source_meta: dict[str, Any],
) -> None:
    """Extract the initial idea/research spec after the project page exists."""

    with Session(engine) as db:
        project = db.get(ResearchProject, project_id)
        run = db.get(ResearchRun, run_id)
        trace_record = db.exec(select(ResearchTrace).where(ResearchTrace.run_id == run_id)).first()
        if project is None or run is None or trace_record is None or project.user_id != user_id:
            return
        log_path = _ensure_run_log_path(run_id)
        _append_run_log(
            run_id,
            "thread_start",
            project_id=project_id,
            stage="initial_research",
            message="Initial research worker started.",
            extra={"log_path": log_path},
        )

        try:
            idea_spec = extract_idea(idea_input, source_meta)
            research_spec = build_research_spec(idea_spec)
            factor_execution = dict(research_spec.get("factor_execution") or {})
            factor_execution["mode"] = "codex"
            factor_execution["code_agent"] = "codex"
            factor_execution.setdefault("fallback_to_expression", True)
            research_spec["factor_execution"] = factor_execution

            trace_record.trace_json = _json_safe(
                {
                    "input_text": project.idea_text,
                    "idea_spec": idea_spec,
                    "research_spec": research_spec,
                }
            )
            run.current_step = "等待确认研究配置"
            events = [dict(event) for event in (run.progress_events or [])]
            for event in events:
                if event.get("status") == "running":
                    event["status"] = "completed"
                    event["message"] = "已提炼投资假设，请确认研究配置。"
            run.progress_events = events
            project.status = "pending"
            project.summary = _summary_from_trace(trace_record.trace_json)
            project.updated_at = utcnow()
            db.add(project)
            db.add(run)
            db.add(trace_record)
            db.commit()
            _append_run_log(
                run_id,
                "thread_success",
                project_id=project_id,
                stage="initial_research",
                message="Initial research completed.",
            )
        except Exception as exc:
            logger.exception("initial research failed for project_id=%s run_id=%s", project_id, run_id)
            _append_run_log(
                run_id,
                "thread_error",
                project_id=project_id,
                stage="initial_research",
                message=str(exc),
                exc=exc,
            )
            _append_trace_diagnostic(
                db,
                trace_record,
                _diagnostic_payload(
                    stage="initial_research",
                    project=project,
                    run=run,
                    message=str(exc),
                    exc=exc,
                ),
            )
            run.status = "failed"
            run.error = str(exc)
            run.current_step = "智能研读失败"
            _finish_progress(db, run, "failed", "智能研读失败，请检查输入或 PDF 内容。")
            project.status = "failed"
            project.summary = str(exc)[:400]
            project.updated_at = utcnow()
            db.add(project)
            db.add(run)
            db.commit()
        finally:
            pdf_path = source_meta.get("pdf_path")
            if pdf_path:
                try:
                    os.unlink(str(pdf_path))
                except OSError:
                    pass


def _run_resume_workflow(project_id: int, run_id: int, user_id: int) -> None:
    """Resume the workflow for a pending project using the trace's research_spec."""
    with Session(engine) as db:
        project = db.get(ResearchProject, project_id)
        run = db.get(ResearchRun, run_id)
        trace_record = db.exec(
            select(ResearchTrace).where(ResearchTrace.run_id == run_id)
        ).first()
        if project is None or run is None or trace_record is None:
            return
        start = time.perf_counter()
        log_path = _ensure_run_log_path(run_id)
        _append_run_log(
            run_id,
            "thread_start",
            project_id=project_id,
            stage="resume_workflow",
            message="Resume workflow worker started.",
            extra={"log_path": log_path},
        )

        def progress_callback(message: str) -> None:
            _append_run_log(
                run_id,
                "progress",
                project_id=project_id,
                stage=message.replace("...", "").replace("。", ""),
                message=message,
            )
            _append_progress(db, run, message.replace("...", "").replace("。", ""), message)

        def trace_update_callback(updates: dict[str, Any]) -> None:
            _append_run_log(
                run_id,
                "trace_update",
                project_id=project_id,
                stage="resume_workflow",
                message="Trace updated during workflow execution.",
                extra={"keys": sorted(updates.keys())},
            )
            current_trace = dict(trace_record.trace_json or {})
            current_trace.update(updates)
            trace_record.trace_json = _json_safe(current_trace)
            project.updated_at = utcnow()
            db.add(project)
            db.add(trace_record)
            db.commit()
            db.refresh(trace_record)

        try:
            trace_json = trace_record.trace_json or {}
            input_text = str(trace_json.get("input_text") or project.idea_text)
            idea_spec = trace_json.get("idea_spec") or {}
            research_spec = trace_json.get("research_spec") or {}
            trace = run_resume_workflow(
                input_text=input_text,
                idea_spec=idea_spec,
                research_spec=research_spec,
                save_trace=False,
                progress_callback=progress_callback,
                trace_update_callback=trace_update_callback,
            )
            safe_trace = _json_safe(trace)
            if safe_trace.get("pipeline_status") == "fallback":
                _append_run_log(
                    run_id,
                    "fallback",
                    project_id=project_id,
                    stage="factor_plugin_fallback",
                    message="Codex factor plugin pipeline fell back to expression mode.",
                    extra={"pipeline_errors": safe_trace.get("pipeline_errors", [])},
                )
                diagnostics = [
                    dict(item) for item in safe_trace.get("workflow_diagnostics", [])
                ]
                diagnostics.append(
                    _diagnostic_payload(
                        stage="factor_plugin_fallback",
                        project=project,
                        run=run,
                        message="Codex factor plugin pipeline fell back to expression mode.",
                        extra={
                            "pipeline_errors": safe_trace.get("pipeline_errors", []),
                            "factor_implementation_mode": safe_trace.get(
                                "factor_implementation_mode"
                            ),
                        },
                    )
                )
                safe_trace["workflow_diagnostics"] = diagnostics[-20:]
            report = str(safe_trace.get("report_markdown") or "")
            metrics = _metrics_from_trace(safe_trace)
            run.status = "completed"
            run.workflow_mode = str(safe_trace.get("workflow_mode") or "demo_workflow")
            run.is_mock = bool(safe_trace.get("is_mock", True))
            run.duration_ms = int((time.perf_counter() - start) * 1000)
            _finish_progress(db, run, "completed", "研究结果已生成。")
            project.status = "completed"
            project.summary = _summary_from_trace(safe_trace)
            project.updated_at = utcnow()
            trace_record.trace_json = safe_trace
            trace_record.report_markdown = report
            trace_record.metrics_summary = metrics
            db.add(project)
            db.add(run)
            db.add(trace_record)
            db.commit()
            _append_run_log(
                run_id,
                "thread_success",
                project_id=project_id,
                stage="resume_workflow",
                message="Resume workflow completed.",
                extra={"duration_ms": run.duration_ms},
            )
        except Exception as exc:
            logger.exception("resume workflow failed for project_id=%s run_id=%s", project_id, run_id)
            _append_run_log(
                run_id,
                "thread_error",
                project_id=project_id,
                stage="resume_workflow",
                message=str(exc),
                exc=exc,
            )
            _append_trace_diagnostic(
                db,
                trace_record,
                _diagnostic_payload(
                    stage="resume_workflow",
                    project=project,
                    run=run,
                    message=str(exc),
                    exc=exc,
                ),
            )
            run.status = "failed"
            run.error = str(exc)
            run.duration_ms = int((time.perf_counter() - start) * 1000)
            _finish_progress(db, run, "failed", "研究生成失败，请调整输入后重试。")
            project.status = "failed"
            project.summary = str(exc)[:400]
            project.updated_at = utcnow()
            db.add(project)
            db.add(run)
            db.commit()


@router.get("/projects", response_model=list[ResearchProjectSummary])
def list_projects(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ResearchProjectSummary]:
    projects = db.exec(
        select(ResearchProject)
        .where(ResearchProject.user_id == user.id)
        .order_by(ResearchProject.updated_at.desc())
    ).all()
    return [_project_summary(db, project) for project in projects]


@router.post(
    "/projects",
    response_model=ResearchProjectDetail,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_csrf)],
)
async def create_project(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ResearchProjectDetail:
    """Create a research project from text or an uploaded PDF.

    Supports both JSON body (legacy) and multipart/form-data (PDF upload).
    """

    content_type = request.headers.get("content-type", "")
    is_multipart = content_type.startswith("multipart/form-data")

    if is_multipart:
        form = await request.form()
        title = str(form.get("title", "")).strip()
        input_text = str(form.get("input_text", "")).strip()
        source_type = str(form.get("source_type", "text")).strip()
        file_field = form.get("file")
        # starlette.formparsers may return UploadFile or a string; accept any truthy value
        project_file: Any = file_field if file_field is not None else None
        project_title = title
        project_input = input_text
        project_source_type = source_type
    else:
        # Legacy JSON path: read and validate the raw body ourselves.
        try:
            raw_body = await request.body()
            raw = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=422, detail=f"Invalid JSON: {exc}") from exc

        try:
            payload = ResearchProjectCreate(**raw)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors()) from exc
        project_title = payload.title.strip()
        project_input = payload.input_text.strip()
        project_source_type = payload.source_type or "text"
        project_file = None

    file_content_type = project_file.content_type if hasattr(project_file, "content_type") else None
    filename = project_file.filename if hasattr(project_file, "filename") else str(getattr(project_file, "filename", "") or "")
    is_pdf = (
        project_source_type == "pdf"
        or file_content_type in ("application/pdf",)
        or str(filename).lower().endswith(".pdf")
    )

    tmp_path: str | None = None
    if is_pdf and project_file is not None:
        suffix = ".pdf" if str(filename).lower().endswith(".pdf") else ""
        file_bytes = project_file.file.read() if hasattr(project_file, "file") else b""
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
        source_meta = {"source_type": "pdf", "pdf_path": tmp_path, "filename": filename}
        idea_input = tmp_path
        display_input = filename or "PDF 研报"
    else:
        source_meta = {"source_type": "text"}
        idea_input = project_input
        display_input = project_input

    project = ResearchProject(
        user_id=user.id or 0,
        title=project_title,
        idea_text=display_input,
        status="pending",
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    run = ResearchRun(
        project_id=project.id or 0,
        user_id=user.id or 0,
        input_text=display_input,
        status="pending",
        current_step="智能研读",
        progress_events=[
            {**INITIAL_PROGRESS[0], "time": utcnow().isoformat(timespec="seconds")},
            {
                "step": "智能研读",
                "status": "running",
                "message": "正在提炼投资假设并生成研究配置。",
                "time": utcnow().isoformat(timespec="seconds"),
            },
        ],
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    db.add(
        ResearchTrace(
            run_id=run.id or 0,
            user_id=user.id or 0,
            trace_json=_json_safe({"input_text": display_input}),
            report_markdown="",
            metrics_summary={},
        )
    )
    db.commit()

    Thread(
        target=_run_initial_research,
        args=(project.id or 0, run.id or 0, user.id or 0, idea_input, source_meta),
        daemon=True,
    ).start()

    return get_project(project.id or 0, user, db)


@router.get("/projects/{project_id}/progress", response_model=ResearchRunProgress)
def get_project_progress(
    project_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ResearchRunProgress:
    project = db.get(ResearchProject, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Research project not found")
    latest = _latest_run(db, project.id or 0, user.id or 0)
    latest = _maybe_finish_stale_codex_run(db, project, latest)
    return ResearchRunProgress(
        project_id=project.id or 0,
        run_id=latest.id if latest else None,
        status=project.status,
        current_step=latest.current_step if latest else "",
        progress_events=_normalize_progress_events(
            latest.progress_events if latest else [],
            project.status,
        ),
    )


@router.get("/projects/{project_id}", response_model=ResearchProjectDetail)
def get_project(
    project_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ResearchProjectDetail:
    project = db.get(ResearchProject, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Research project not found")
    latest = _latest_run(db, project.id or 0, user.id or 0)
    trace_record = None
    if latest:
        trace_record = db.exec(select(ResearchTrace).where(ResearchTrace.run_id == latest.id)).first()
    summary = _project_summary(db, project)
    return ResearchProjectDetail(
        **summary.model_dump(),
        report_markdown=trace_record.report_markdown if trace_record else "",
        metrics_summary=trace_record.metrics_summary if trace_record else {},
        trace=_display_safe_trace(trace_record.trace_json if trace_record else {}),
    )


@router.patch(
    "/projects/{project_id}/research-spec",
    response_model=ResearchProjectDetail,
    dependencies=[Depends(verify_csrf)],
)
def update_research_spec(
    project_id: int,
    update: ResearchSpecUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ResearchProjectDetail:
    """Update the research_spec stored on the latest run trace.

    Only allowed while the project is still pending and before the user starts
    the remaining workflow stages.
    """
    project = db.get(ResearchProject, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Research project not found")

    if project.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="研究已开始执行或已完成，配置不可修改。",
        )

    latest = _latest_run(db, project.id or 0, user.id or 0)
    if latest is None:
        raise HTTPException(status_code=404, detail="没有找到研究运行记录")

    trace_record = db.exec(select(ResearchTrace).where(ResearchTrace.run_id == latest.id)).first()
    if trace_record is None:
        raise HTTPException(status_code=404, detail="没有找到研究路径记录")
    if not (trace_record.trace_json or {}).get("research_spec"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="智能研读尚未完成，请稍后再保存配置。",
        )

    updated_trace = _update_research_spec(trace_record.trace_json, update)
    trace_record.trace_json = _json_safe(updated_trace)
    project.updated_at = utcnow()
    db.add(trace_record)
    db.add(project)
    db.commit()
    db.refresh(trace_record)

    return get_project(project_id, user, db)


@router.post(
    "/projects/{project_id}/start",
    response_model=ResearchProjectDetail,
    dependencies=[Depends(verify_csrf)],
)
def start_project(
    project_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ResearchProjectDetail:
    """Start the remaining workflow stages for a pending project."""
    project = db.get(ResearchProject, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Research project not found")

    if project.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="研究不在待开始状态，无法启动。",
        )

    latest = _latest_run(db, project.id or 0, user.id or 0)
    if latest is None:
        raise HTTPException(status_code=404, detail="没有找到研究运行记录")

    trace_record = db.exec(select(ResearchTrace).where(ResearchTrace.run_id == latest.id)).first()
    if trace_record is None:
        raise HTTPException(status_code=404, detail="没有找到研究路径记录")
    if not (trace_record.trace_json or {}).get("research_spec"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="智能研读尚未完成，请稍后再启动研究。",
        )

    project.status = "running"
    project.updated_at = utcnow()
    latest.status = "running"
    latest.current_step = "生成候选因子"
    events = [dict(event) for event in (latest.progress_events or [])]
    for event in events:
        if event.get("status") == "running":
            event["status"] = "completed"
    events.append(
        {
            "step": "研究执行",
            "status": "running",
            "message": "开始生成候选因子...",
            "time": utcnow().isoformat(timespec="seconds"),
        }
    )
    latest.progress_events = events
    db.add(project)
    db.add(latest)
    db.commit()

    Thread(
        target=_run_resume_workflow,
        args=(project.id or 0, latest.id or 0, user.id or 0),
        daemon=True,
    ).start()

    return get_project(project_id, user, db)
