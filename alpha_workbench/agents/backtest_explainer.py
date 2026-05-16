"""Backtest explanation agent with mock fallback."""

from __future__ import annotations

from typing import Any


def mock_explain_backtest(backtest_result: dict[str, Any]) -> dict[str, Any]:
    leader = backtest_result["factor_results"][0]
    return {
        "summary": (
            f"样例回测中，{leader['factor_name']} 的 IC 均值和多空收益表现最好，"
            "说明盈利超预期信息在 mock 数据中存在一定排序能力。"
        ),
        "observations": [
            "三组候选因子均为正 IC，适合作为后续真实数据验证的 baseline。",
            "多空收益来自固定样例数据，只用于展示流程和页面联调。",
            "后续应加入分年度、分行业、换手率和交易成本敏感性分析。",
        ],
        "is_mock": True,
    }


def explain_backtest(backtest_result: dict[str, Any]) -> dict[str, Any]:
    return mock_explain_backtest(backtest_result)
