"""Agno workflow for Role 3 idea extraction.

This workflow keeps the public interface stable:
- input: `input_text`, optional `source_meta`, optional `api_url`, optional `token`
- output: a trace dict that contains the fixed Role 3 envelope under `idea_result`

Only the middle processing steps should change over time.
"""

from __future__ import annotations

from typing import Any

from alpha_workbench.workflows.agno_runtime import (
    AGNO_AVAILABLE,
    build_agno_workflow,
    make_step_output,
    step_input_payload,
    workflow_response_content,
    workflow_runtime_metadata,
)
from role3.idea_extractor import extract_idea


def _ensure_payload(step_input: Any) -> dict[str, Any]:
    payload = step_input_payload(step_input)
    if isinstance(payload, dict):
        return payload
    return {"input_text": str(payload or "")}


def _step_extract_idea(step_input: Any) -> Any:
    payload = _ensure_payload(step_input)
    idea_result = extract_idea(
        input_text=payload.get("input_text", ""),
        source_meta=payload.get("source_meta"),
        api_url=payload.get("api_url"),
        token=payload.get("token"),
    )
    payload["idea_result"] = idea_result
    return make_step_output(payload)


def _step_build_role3_trace(step_input: Any) -> Any:
    payload = _ensure_payload(step_input)
    trace = {
        "workflow_mode": "role3_idea_extraction",
        "input_text": payload.get("input_text", ""),
        "source_meta": payload.get("source_meta") or {"source_type": "text"},
        "idea_result": payload.get("idea_result", {}),
    }
    trace.update(workflow_runtime_metadata())
    return make_step_output(trace)


def create_role3_agno_workflow() -> Any | None:
    if not AGNO_AVAILABLE:
        return None

    return build_agno_workflow(
        name="AlphaWorkbench Role3 Idea Extraction Workflow",
        description="Extract IdeaSpec from text or PDF input and package a stable Role 3 trace.",
        steps=[
            (
                "idea_extraction",
                "Call the Role 3 extractor and build the fixed envelope.",
                _step_extract_idea,
            ),
            (
                "build_trace",
                "Package the final Role 3 workflow trace.",
                _step_build_role3_trace,
            ),
        ],
    )


def run_role3_workflow(
    input_text: str,
    *,
    source_meta: dict[str, Any] | None = None,
    api_url: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    payload = {
        "input_text": input_text,
        "source_meta": source_meta or {"source_type": "text"},
        "api_url": api_url,
        "token": token,
    }

    if not AGNO_AVAILABLE:
        trace = {
            "workflow_mode": "role3_idea_extraction",
            "input_text": input_text,
            "source_meta": source_meta or {"source_type": "text"},
            "idea_result": extract_idea(
                input_text=input_text,
                source_meta=source_meta,
                api_url=api_url,
                token=token,
            ),
        }
        trace.update(workflow_runtime_metadata())
        return trace

    workflow = create_role3_agno_workflow()
    if workflow is None:
        trace = {
            "workflow_mode": "role3_idea_extraction",
            "input_text": input_text,
            "source_meta": source_meta or {"source_type": "text"},
            "idea_result": extract_idea(
                input_text=input_text,
                source_meta=source_meta,
                api_url=api_url,
                token=token,
            ),
        }
        trace.update(workflow_runtime_metadata())
        return trace

    try:
        response = workflow.run(input=payload)
        trace = workflow_response_content(response)
        if not isinstance(trace, dict):
            raise TypeError(f"Agno workflow returned unsupported content: {type(trace)!r}")
        trace["workflow_framework"] = "agno"
        trace["agno_available"] = True
        return trace
    except Exception as exc:
        trace = {
            "workflow_mode": "role3_idea_extraction",
            "input_text": input_text,
            "source_meta": source_meta or {"source_type": "text"},
            "idea_result": extract_idea(
                input_text=input_text,
                source_meta=source_meta,
                api_url=api_url,
                token=token,
            ),
        }
        trace.update(workflow_runtime_metadata())
        trace["workflow_framework"] = "python_fallback"
        trace["agno_run_error"] = str(exc)
        return trace
