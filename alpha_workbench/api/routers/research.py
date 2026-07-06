"""Research project API routes."""

from __future__ import annotations

import json
from threading import Thread
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
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
from alpha_workbench.memory.research_trace import _safe_json_default
from alpha_workbench.workflows.demo_workflow import run_demo_workflow


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

    # Sync backtest sub-config with top-level values
    backtest = dict(research.get("backtest") or {})
    if "rebalance_frequency" in research:
        backtest["rebalance_frequency"] = research["rebalance_frequency"]
    if "transaction_cost_bps" in research:
        backtest["transaction_cost_bps"] = research["transaction_cost_bps"]
    if "initial_cash" in research:
        backtest["initial_cash"] = research["initial_cash"]
    research["backtest"] = backtest

    trace = dict(trace)
    trace["research_spec"] = research
    return trace


router = APIRouter(prefix="/api/research", tags=["research"])


INITIAL_PROGRESS = [
    {
        "step": "创建研究任务",
        "status": "completed",
        "message": "已收到研究想法，准备进入智能研读。",
    },
    {
        "step": "智能研读",
        "status": "running",
        "message": "正在提炼投资假设与关键约束。",
    },
]


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=_safe_json_default))


def _summary_from_trace(trace: dict[str, Any]) -> str:
    idea = trace.get("idea_spec") or {}
    if isinstance(idea, dict):
        hypothesis = idea.get("hypothesis") or idea.get("summary")
        if hypothesis:
            return str(hypothesis)[:400]
    return "研究流程已完成。"


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


def _project_summary(db: Session, project: ResearchProject) -> ResearchProjectSummary:
    latest = _latest_run(db, project.id or 0, project.user_id)
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
        progress_events=latest.progress_events if latest else [],
    )


def _append_progress(db: Session, run: ResearchRun, step: str, message: str) -> None:
    events = list(run.progress_events or [])
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
    db.add(run)
    db.commit()
    db.refresh(run)


def _finish_progress(db: Session, run: ResearchRun, status_value: str, message: str) -> None:
    events = list(run.progress_events or [])
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


def _run_project_workflow(project_id: int, run_id: int, input_text: str, user_id: int) -> None:
    with Session(engine) as db:
        project = db.get(ResearchProject, project_id)
        run = db.get(ResearchRun, run_id)
        if project is None or run is None:
            return
        start = time.perf_counter()

        def progress_callback(message: str) -> None:
            _append_progress(db, run, message.replace("...", "").replace("。", ""), message)

        try:
            trace = run_demo_workflow(
                input_text=input_text,
                save_trace=False,
                progress_callback=progress_callback,
            )
            safe_trace = _json_safe(trace)
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
            db.add(project)
            db.add(run)
            db.add(
                ResearchTrace(
                    run_id=run.id or 0,
                    user_id=user_id,
                    trace_json=safe_trace,
                    report_markdown=report,
                    metrics_summary=metrics,
                )
            )
            db.commit()
        except Exception as exc:
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
def create_project(
    payload: ResearchProjectCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ResearchProjectDetail:
    project = ResearchProject(
        user_id=user.id or 0,
        title=payload.title.strip(),
        idea_text=payload.input_text.strip(),
        status="running",
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    run = ResearchRun(
        project_id=project.id or 0,
        user_id=user.id or 0,
        input_text=payload.input_text,
        status="running",
        current_step="智能研读",
        progress_events=[
            {
                **event,
                "time": utcnow().isoformat(timespec="seconds"),
            }
            for event in INITIAL_PROGRESS
        ],
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    Thread(
        target=_run_project_workflow,
        args=(project.id or 0, run.id or 0, payload.input_text, user.id or 0),
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
    return ResearchRunProgress(
        project_id=project.id or 0,
        run_id=latest.id if latest else None,
        status=project.status,
        current_step=latest.current_step if latest else "",
        progress_events=latest.progress_events if latest else [],
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
        trace=trace_record.trace_json if trace_record else {},
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

    Only allowed while the workflow is still running or has just been created.
    """
    project = db.get(ResearchProject, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Research project not found")

    if project.status not in {"running", "pending"}:
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

    updated_trace = _update_research_spec(trace_record.trace_json, update)
    trace_record.trace_json = _json_safe(updated_trace)
    project.updated_at = utcnow()
    db.add(trace_record)
    db.add(project)
    db.commit()
    db.refresh(trace_record)

    return get_project(project_id, user, db)
