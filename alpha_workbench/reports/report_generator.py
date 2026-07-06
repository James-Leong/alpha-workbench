"""Report generation helpers and templates."""

from __future__ import annotations

from typing import Any


REPORT_TEMPLATE = """# AlphaWorkbench 研究报告

## 投资思想

**{idea_name}**

{core_hypothesis}

### 经济机制
{economic_mechanism}

### 所需数据
{required_data}

### 风险提示
{risk_flags}

---

## 研究配置

- **股票池**: {universe}
- **调仓频率**: {rebalance_frequency}
- **持有期**: {holding_period}
- **交易成本**: {transaction_cost_bps} bps
- **基准**: {benchmark}

---

## 候选因子回测结果

{factor_table}

---

## 审计结果

**整体等级**: {audit_level}

{audit_checks}

### 建议行动
{next_actions}

---

## 结论

{conclusion}

---

*本报告由 AlphaWorkbench 自动生成，基于模拟数据，不构成投资建议。*
"""


def _format_bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "- 无"


def _format_factor_table(factor_results: list[dict[str, Any]]) -> str:
    if not factor_results:
        return "暂无回测结果。"
    lines = ["| 因子 | IC 均值 | 多空收益 | 最大回撤 | 夏普 |", "| --- | --- | --- | --- | --- |"]
    for f in factor_results:
        lines.append(
            f"| {f.get('factor_name', f.get('factor_id', '-'))} | "
            f"{f.get('ic_mean', 0):.4f} | "
            f"{f.get('long_short_return', 0):.2%} | "
            f"{f.get('max_drawdown', 0):.2%} | "
            f"{f.get('sharpe_ratio', 0):.2f} |"
        )
    return "\n".join(lines)


def generate_report(trace: dict[str, Any]) -> str:
    """Generate a structured Markdown research report from a ResearchTrace."""
    idea = trace.get("idea_spec") or {}
    research = trace.get("research_spec") or {}
    audit = trace.get("audit_report") or {}
    backtest = trace.get("backtest_result") or {}
    factor_results = backtest.get("factor_results", [])

    best = factor_results[0] if factor_results else {}
    conclusion = (
        f"当前最佳候选因子为 **{best.get('factor_name', best.get('factor_id', '未知'))}**，"
        f"IC 均值为 {best.get('ic_mean', 0):.4f}，"
        f"多空年化收益为 {best.get('long_short_return', 0):.2%}，"
        f"最大回撤为 {best.get('max_drawdown', 0):.2%}。"
        if best
        else "当前暂无有效回测结果，建议补充数据后重新运行。"
    )

    audit_checks = "\n".join(
        f"- **[{c.get('level', 'low').upper()}]** {c.get('item')}：{c.get('message')}"
        for c in audit.get("checks", [])
    ) or "- 无"

    return REPORT_TEMPLATE.format(
        idea_name=idea.get("idea_name", "未知投资思想"),
        core_hypothesis=idea.get("core_hypothesis", "未提供核心假设。"),
        economic_mechanism=_format_bullets(idea.get("economic_mechanism", [])),
        required_data=_format_bullets(idea.get("required_data_concepts", [])),
        risk_flags=_format_bullets(idea.get("risk_flags", [])),
        universe=research.get("universe", "未知"),
        rebalance_frequency=research.get("rebalance_frequency", "未知"),
        holding_period=research.get("holding_period", "未知"),
        transaction_cost_bps=research.get("transaction_cost_bps", 10),
        benchmark=research.get("benchmark", "未知"),
        factor_table=_format_factor_table(factor_results),
        audit_level=audit.get("overall_level", "未知"),
        audit_checks=audit_checks,
        next_actions=_format_bullets(audit.get("next_actions", [])),
        conclusion=conclusion,
    )
