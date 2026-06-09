"""Deterministic MVP workflow for AlphaWorkbench."""

from __future__ import annotations

from typing import Any

from alpha_workbench.agents.audit_agent import run_audit
from alpha_workbench.agents.backtest_explainer import explain_backtest
from alpha_workbench.agents.factor_generator import generate_factors
from alpha_workbench.agents.idea_extractor import extract_idea
from alpha_workbench.agents.report_agent import generate_report
from alpha_workbench.backtest.engine import run_backtest
from alpha_workbench.factor_engine.compiler import compile_factors
from alpha_workbench.memory.research_trace import save_research_trace
from alpha_workbench.schemas.specs import build_research_trace, clone_default_research_spec
from alpha_workbench.workflows.agno_runtime import (
    AGNO_AVAILABLE,
    build_agno_workflow,
    make_step_output,
    step_input_payload,
    workflow_response_content,
    workflow_runtime_metadata,
)

DEFAULT_INPUT = "单季度净利润超预期，且公告前股价没有明显上涨的公司，未来可能获得超额收益。"


def build_research_spec(
    idea_spec: dict[str, Any],
    user_rules: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a ResearchSpec dict compatible with both legacy consumers and role5 models.

    The dict is accepted by:
      - role5 ResearchSpec.from_dict() (extra keys are ignored)
      - role3/role4/role6 agents (read legacy keys like holding_period etc.)
      - role5 run_backtest() (reads backtest.groups, universe, etc.)
    """
    research_spec = clone_default_research_spec()
    research_spec["idea_name"] = idea_spec["idea_name"]
    if user_rules:
        research_spec.update(user_rules)
    # Add role5-compatible backtest config block
    research_spec.setdefault(
        "backtest",
        {
            "groups": 5,
            "rebalance_frequency": research_spec.get("rebalance_frequency", "monthly"),
            "holding_period": int(str(research_spec.get("holding_period", "20")).split()[0]),
            "transaction_cost_bps": research_spec.get("transaction_cost_bps", 10),
            "initial_cash": research_spec.get("initial_cash", 1_000_000),
        },
    )
    return research_spec


def _run_python_demo_workflow(
    input_text: str = DEFAULT_INPUT,
    *,
    save_trace: bool = False,
    agno_run_error: str | None = None,
) -> dict[str, Any]:
    idea_spec = extract_idea(input_text)
    if progress_callback:
        progress_callback("正在构建研究配置...")
    research_spec = build_research_spec(idea_spec)
    if progress_callback:
        progress_callback("正在生成候选因子...")
    factor_specs = generate_factors(idea_spec, research_spec)
    if progress_callback:
        progress_callback("正在编译因子表达式...")
    compiled_factors = compile_factors(factor_specs)
    if progress_callback:
        progress_callback("正在执行回测...")
    backtest_result = run_backtest(factor_specs, research_spec)
    if progress_callback:
        progress_callback("正在生成回测解释...")
    explanation = explain_backtest(backtest_result)

    partial_trace = {
        "input_text": input_text,
        "idea_spec": idea_spec,
        "research_spec": research_spec,
        "factor_specs": factor_specs,
        "compiled_factors": compiled_factors,
        "backtest_result": backtest_result,
        "explanation": explanation,
    }
    audit_report = run_audit(partial_trace)
    if progress_callback:
        progress_callback("正在生成研究报告...")
    trace = build_research_trace(
        input_text=input_text,
        idea_spec=idea_spec,
        research_spec=research_spec,
        factor_specs=factor_specs,
        backtest_result=backtest_result,
        explanation=explanation,
        audit_report=audit_report,
        report_markdown="",
    )
    trace["workflow_mode"] = "demo_workflow"
    trace["compiled_factors"] = compiled_factors
    trace["report_markdown"] = generate_report(trace)
    if save_trace:
        trace["trace_path"] = save_research_trace(trace)
    trace.update(workflow_runtime_metadata())
    if agno_run_error:
        trace["workflow_framework"] = "python_fallback"
        trace["agno_run_error"] = agno_run_error
    return trace


def _ensure_payload(step_input: Any) -> dict[str, Any]:
    payload = step_input_payload(step_input)
    if isinstance(payload, dict):
        return payload
    return {"input_text": str(payload or DEFAULT_INPUT), "save_trace": False}


def _step_extract_idea(step_input: Any) -> Any:
    payload = _ensure_payload(step_input)
    payload["idea_spec"] = extract_idea(payload.get("input_text", DEFAULT_INPUT))
    return make_step_output(payload)


def _step_build_research_spec(step_input: Any) -> Any:
    payload = _ensure_payload(step_input)
    payload["research_spec"] = build_research_spec(payload["idea_spec"])
    return make_step_output(payload)


def _step_generate_factors(step_input: Any) -> Any:
    payload = _ensure_payload(step_input)
    payload["factor_specs"] = generate_factors(payload["idea_spec"], payload["research_spec"])
    return make_step_output(payload)


def _step_compile_factors(step_input: Any) -> Any:
    payload = _ensure_payload(step_input)
    payload["compiled_factors"] = compile_factors(payload["factor_specs"])
    return make_step_output(payload)


def _step_run_backtest(step_input: Any) -> Any:
    payload = _ensure_payload(step_input)
    payload["backtest_result"] = run_backtest(payload["factor_specs"], payload["research_spec"])
    return make_step_output(payload)


def _step_explain_backtest(step_input: Any) -> Any:
    payload = _ensure_payload(step_input)
    payload["explanation"] = explain_backtest(payload["backtest_result"])
    return make_step_output(payload)


def _step_run_audit(step_input: Any) -> Any:
    payload = _ensure_payload(step_input)
    partial_trace = {
        "input_text": payload.get("input_text", DEFAULT_INPUT),
        "idea_spec": payload["idea_spec"],
        "research_spec": payload["research_spec"],
        "factor_specs": payload["factor_specs"],
        "compiled_factors": payload["compiled_factors"],
        "backtest_result": payload["backtest_result"],
        "explanation": payload["explanation"],
    }
    payload["audit_report"] = run_audit(partial_trace)
    return make_step_output(payload)


def _step_build_report_trace(step_input: Any) -> Any:
    payload = _ensure_payload(step_input)
    trace = build_research_trace(
        input_text=payload.get("input_text", DEFAULT_INPUT),
        idea_spec=payload["idea_spec"],
        research_spec=payload["research_spec"],
        factor_specs=payload["factor_specs"],
        backtest_result=payload["backtest_result"],
        explanation=payload["explanation"],
        audit_report=payload["audit_report"],
        report_markdown="",
    )
    trace["workflow_mode"] = "demo_workflow"
    trace["compiled_factors"] = payload["compiled_factors"]
    trace["report_markdown"] = generate_report(trace)
    trace.update(workflow_runtime_metadata())
    if payload.get("save_trace"):
        trace["trace_path"] = save_research_trace(trace)
    return make_step_output(trace)


def create_agno_demo_workflow() -> Any | None:
    """Create the Agno Workflow used for the deterministic demo path."""
    return build_agno_workflow(
        name="AlphaWorkbench Demo Workflow",
        description="Idea -> ResearchSpec -> Factors -> Backtest -> Audit -> Report.",
        steps=[
            ("idea_extraction", "Extract IdeaSpec from the user research input.", _step_extract_idea),
            (
                "research_config",
                "Build the ResearchSpec configuration from IdeaSpec.",
                _step_build_research_spec,
            ),
            (
                "factor_generation",
                "Generate candidate FactorSpec outputs.",
                _step_generate_factors,
            ),
            ("factor_compile", "Validate and compile candidate factor trees.", _step_compile_factors),
            ("backtest", "Run the baseline backtest.", _step_run_backtest),
            ("backtest_explanation", "Explain backtest results.", _step_explain_backtest),
            ("audit", "Audit the research trace for common risks.", _step_run_audit),
            ("report_trace", "Build report markdown and final trace.", _step_build_report_trace),
        ],
    )


def run_demo_workflow(input_text: str = DEFAULT_INPUT, *, save_trace: bool = False) -> dict[str, Any]:
    if not AGNO_AVAILABLE:
        return _run_python_demo_workflow(input_text, save_trace=save_trace)

    workflow = create_agno_demo_workflow()
    if workflow is None:
        return _run_python_demo_workflow(input_text, save_trace=save_trace)

    try:
        response = workflow.run(input={"input_text": input_text, "save_trace": save_trace})
        trace = workflow_response_content(response)
        if not isinstance(trace, dict):
            raise TypeError(f"Agno workflow returned unsupported content: {type(trace)!r}")
        trace["workflow_framework"] = "agno"
        trace["agno_available"] = True
        return trace
    except Exception as exc:
        return _run_python_demo_workflow(
            input_text,
            save_trace=save_trace,
            agno_run_error=str(exc),
        )
