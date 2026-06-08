"""Role 2 integration workflow shell.

This module keeps the UI/workflow contract stable while other roles are still
building their own modules. Empty outputs stay as placeholders and can be
filled later by pasting JSON from each role.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from alpha_workbench.memory.research_trace import save_research_trace
from alpha_workbench.workflows.agno_runtime import (
    AGNO_AVAILABLE,
    build_agno_workflow,
    make_step_output,
    step_input_payload,
    workflow_response_content,
    workflow_runtime_metadata,
)


WORKFLOW_STEPS: list[dict[str, str]] = [
    {
        "step_id": "input",
        "label": "研究输入",
        "owner": "role_2_ui_workflow",
        "output_key": "input_text",
    },
    {
        "step_id": "idea_extraction",
        "label": "IdeaSpec 接入",
        "owner": "role_3_idea_agent",
        "output_key": "idea_spec",
    },
    {
        "step_id": "research_config",
        "label": "ResearchSpec 确认",
        "owner": "role_2_ui_workflow",
        "output_key": "research_spec",
    },
    {
        "step_id": "factor_generation",
        "label": "FactorSpec 接入",
        "owner": "role_4_factor_agent",
        "output_key": "factor_specs",
    },
    {
        "step_id": "factor_compile",
        "label": "因子编译结果",
        "owner": "role_4_factor_engine",
        "output_key": "compiled_factors",
    },
    {
        "step_id": "backtest",
        "label": "回测结果接入",
        "owner": "role_5_backtest",
        "output_key": "backtest_result",
    },
    {
        "step_id": "backtest_explanation",
        "label": "回测解释接入",
        "owner": "role_5_backtest_agent",
        "output_key": "explanation",
    },
    {
        "step_id": "audit",
        "label": "审计结果接入",
        "owner": "role_6_audit_agent",
        "output_key": "audit_report",
    },
    {
        "step_id": "report",
        "label": "最终报告接入",
        "owner": "role_6_report_agent",
        "output_key": "report_markdown",
    },
]


EMPTY_ROLE_OUTPUTS: dict[str, Any] = {
    "idea_spec": {},
    "research_spec": {},
    "factor_specs": [],
    "compiled_factors": [],
    "backtest_result": {},
    "explanation": {},
    "audit_report": {},
    "report_markdown": "",
    "user_edits": [],
}


INTEGRATION_CONTRACT: dict[str, dict[str, str]] = {
    "idea_spec": {
        "owner": "role_3_idea_agent",
        "shape": "dict",
        "purpose": "核心投资思想、数据需求、证据片段和风险提示。",
    },
    "research_spec": {
        "owner": "role_2_ui_workflow",
        "shape": "dict",
        "purpose": "用户确认后的研究配置，例如股票池、持有期、交易成本和过滤规则。",
    },
    "factor_specs": {
        "owner": "role_4_factor_agent",
        "shape": "list[dict]",
        "purpose": "候选因子的自然语言解释、LaTeX、字段依赖、表达式树和风险提示。",
    },
    "compiled_factors": {
        "owner": "role_4_factor_engine",
        "shape": "list[dict]",
        "purpose": "因子表达式校验或编译后的状态。",
    },
    "backtest_result": {
        "owner": "role_5_backtest",
        "shape": "dict",
        "purpose": "回测指标、图表数据、诊断信息和 mock/fallback 标记。",
    },
    "explanation": {
        "owner": "role_5_backtest_agent",
        "shape": "dict",
        "purpose": "面向研究员的回测解释、问题观察和下一步建议。",
    },
    "audit_report": {
        "owner": "role_6_audit_agent",
        "shape": "dict",
        "purpose": "未来函数、proxy 数据、交易成本、样本偏差等轻量审计结果。",
    },
    "report_markdown": {
        "owner": "role_6_report_agent",
        "shape": "str",
        "purpose": "最终研究报告 Markdown。",
    },
    "user_edits": {
        "owner": "role_2_ui_workflow",
        "shape": "list[dict]",
        "purpose": "用户在前端确认或修改过的字段记录。",
    },
}


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (dict, list, tuple, set)):
        return bool(value)
    return True


def _normalize_outputs(outputs: dict[str, Any] | None) -> dict[str, Any]:
    normalized = EMPTY_ROLE_OUTPUTS.copy()
    if outputs:
        normalized.update({key: value for key, value in outputs.items() if key in normalized})
    return normalized


def _build_step_states(input_text: str, outputs: dict[str, Any]) -> list[dict[str, str]]:
    step_states = []
    for step in WORKFLOW_STEPS:
        key = step["output_key"]
        value = input_text if key == "input_text" else outputs.get(key)
        status = "completed" if _has_value(value) else "waiting"
        step_states.append({**step, "status": status})
    return step_states


def build_empty_integration_trace(input_text: str = "") -> dict[str, Any]:
    """Create a trace with empty role outputs for UI integration work."""
    return build_integration_trace(input_text=input_text, role_outputs=None)


def _build_integration_trace_content(
    *,
    input_text: str,
    role_outputs: dict[str, Any] | None = None,
    save_trace: bool = False,
) -> dict[str, Any]:
    """Build a trace from whatever role outputs are currently available."""
    outputs = _normalize_outputs(role_outputs)
    trace = {
        "project": "AlphaWorkbench",
        "trace_version": "role2-integration-0.1",
        "workflow_mode": "role2_integration_shell",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "input_text": input_text,
        "integration_contract": INTEGRATION_CONTRACT,
        "workflow_steps": _build_step_states(input_text, outputs),
        **outputs,
    }
    trace.update(workflow_runtime_metadata())
    if save_trace:
        trace["trace_path"] = save_research_trace(trace)
    return trace


def _step_build_integration_trace(step_input: Any) -> Any:
    payload = step_input_payload(step_input)
    if not isinstance(payload, dict):
        payload = {"input_text": str(payload or ""), "role_outputs": None, "save_trace": False}
    trace = _build_integration_trace_content(
        input_text=payload.get("input_text", ""),
        role_outputs=payload.get("role_outputs"),
        save_trace=bool(payload.get("save_trace", False)),
    )
    return make_step_output(trace)


def create_agno_integration_workflow() -> Any | None:
    """Create the Agno Workflow for role-output intake and trace assembly."""
    return build_agno_workflow(
        name="AlphaWorkbench Role Output Intake Workflow",
        description="Accept role outputs and assemble an auditable Research Trace.",
        steps=[
            (
                "assemble_research_trace",
                "Normalize role outputs, compute step states, and build the trace.",
                _step_build_integration_trace,
            )
        ],
    )


def build_integration_trace(
    *,
    input_text: str,
    role_outputs: dict[str, Any] | None = None,
    save_trace: bool = False,
) -> dict[str, Any]:
    """Build a trace from whatever role outputs are currently available."""
    if not AGNO_AVAILABLE:
        return _build_integration_trace_content(
            input_text=input_text,
            role_outputs=role_outputs,
            save_trace=save_trace,
        )

    workflow = create_agno_integration_workflow()
    if workflow is None:
        return _build_integration_trace_content(
            input_text=input_text,
            role_outputs=role_outputs,
            save_trace=save_trace,
        )

    try:
        response = workflow.run(
            input={
                "input_text": input_text,
                "role_outputs": role_outputs,
                "save_trace": save_trace,
            }
        )
        trace = workflow_response_content(response)
        if not isinstance(trace, dict):
            raise TypeError(f"Agno workflow returned unsupported content: {type(trace)!r}")
        trace["workflow_framework"] = "agno"
        trace["agno_available"] = True
        return trace
    except Exception as exc:
        trace = _build_integration_trace_content(
            input_text=input_text,
            role_outputs=role_outputs,
            save_trace=save_trace,
        )
        trace["workflow_framework"] = "python_fallback"
        trace["agno_run_error"] = str(exc)
        return trace
