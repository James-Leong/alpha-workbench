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
        },
    )
    return research_spec


def run_demo_workflow(
    input_text: str = DEFAULT_INPUT,
    *,
    save_trace: bool = False,
    progress_callback: callable | None = None,
) -> dict[str, Any]:
    if progress_callback:
        progress_callback("正在提取投资思想...")
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
    trace["compiled_factors"] = compiled_factors
    trace["report_markdown"] = generate_report(trace)
    if save_trace:
        trace["trace_path"] = save_research_trace(trace)
    return trace
