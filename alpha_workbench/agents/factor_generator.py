"""Factor generation agent with stable mock output."""

from __future__ import annotations

from typing import Any


def mock_generate_factors(
    idea_spec: dict[str, Any],
    research_spec: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        {
            "factor_id": "earnings_surprise_adj_001",
            "factor_name": "行业中性盈利超预期",
            "plain_description": "衡量单季度净利润相对历史同期的超预期程度，并做行业中性化处理。",
            "latex_formula": r"z_{industry}\left(\frac{NP_q - NP_{q,y-1}}{|NP_{q,y-1}| + 1}\right)",
            "formula_tree": {
                "op": "industry_zscore",
                "args": [
                    {
                        "op": "divide",
                        "args": [
                            {"op": "subtract", "args": ["quarter_net_profit", "quarter_net_profit_yoy_base"]},
                            {"op": "add", "args": [{"op": "abs", "args": ["quarter_net_profit_yoy_base"]}, 1]},
                        ],
                    }
                ],
            },
            "required_fields": ["quarter_net_profit", "quarter_net_profit_yoy_base", "industry"],
            "risk_notes": ["历史同期利润为 proxy，后续可替换为一致预期净利润。"],
            "is_mock": True,
        },
        {
            "factor_id": "pre_announcement_underreaction_002",
            "factor_name": "公告前低反应修正",
            "plain_description": "盈利超预期越强，且公告前 20 日涨幅越低，因子分数越高。",
            "latex_formula": r"Surprise - 0.5 \times Ret_{[-20,-1]}",
            "formula_tree": {
                "op": "subtract",
                "args": [
                    {"op": "ref", "args": ["earnings_surprise_score"]},
                    {"op": "multiply", "args": [0.5, "pre_announcement_return_20d"]},
                ],
            },
            "required_fields": ["earnings_surprise_score", "pre_announcement_return_20d"],
            "risk_notes": ["公告前收益窗口必须严格早于公告日。"],
            "is_mock": True,
        },
        {
            "factor_id": "quality_surprise_combo_003",
            "factor_name": "质量增强盈利超预期",
            "plain_description": "在盈利超预期基础上叠加经营质量，降低一次性损益扰动。",
            "latex_formula": r"0.7 \times Surprise + 0.3 \times CFOQuality",
            "formula_tree": {
                "op": "add",
                "args": [
                    {"op": "multiply", "args": [0.7, "earnings_surprise_score"]},
                    {"op": "multiply", "args": [0.3, "operating_cashflow_quality"]},
                ],
            },
            "required_fields": ["earnings_surprise_score", "operating_cashflow_quality"],
            "risk_notes": ["经营现金流披露频率和利润披露频率可能不完全一致。"],
            "is_mock": True,
        },
    ]


def generate_factors(
    idea_spec: dict[str, Any],
    research_spec: dict[str, Any],
) -> list[dict[str, Any]]:
    return mock_generate_factors(idea_spec, research_spec)
