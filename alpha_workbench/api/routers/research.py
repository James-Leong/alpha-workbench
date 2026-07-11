"""Research project API routes."""

from __future__ import annotations

import json
import os
import tempfile
from threading import Thread
import time
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
    elif project_status == "failed":
        for event in normalized:
            if event.get("status") == "running":
                event["status"] = "failed"
    return normalized


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
        except Exception as exc:
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

        def progress_callback(message: str) -> None:
            _append_progress(db, run, message.replace("...", "").replace("。", ""), message)

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
            trace_record.trace_json = safe_trace
            trace_record.report_markdown = report
            trace_record.metrics_summary = metrics
            db.add(project)
            db.add(run)
            db.add(trace_record)
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
