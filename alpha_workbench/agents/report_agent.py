"""Research report generator."""

from __future__ import annotations

from typing import Any


def generate_report(trace: dict[str, Any]) -> str:
    idea = trace["idea_spec"]
    best = trace["backtest_result"]["factor_results"][0]
    audit = trace["audit_report"]
    return "\n".join(
        [
            "# AlphaWorkbench Demo 研究报告",
            "",
            f"## 投资思想\n{idea['core_hypothesis']}",
            "",
            f"## 当前最佳候选因子\n{best['factor_name']}（{best['factor_id']}）",
            "",
            (
                "## 样例回测结论\n"
                f"IC 均值：{best['ic_mean']:.3f}；"
                f"多空年化收益：{best['long_short_return']:.2%}；"
                f"最大回撤：{best['max_drawdown']:.2%}。"
            ),
            "",
            f"## 审计等级\n{audit['overall_level']}",
            "",
            "## 说明\n本报告由 mock demo 生成，只用于展示研发流程，不构成投资建议。",
        ]
    )
