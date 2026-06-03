"""UI status helpers that do not depend on Streamlit."""

from __future__ import annotations

from typing import Any


def backtest_source_summary(backtest_result: dict[str, Any]) -> dict[str, Any]:
    """Summarize which engine produced the visible backtest results."""
    factor_results = backtest_result.get("factor_results", [])
    engines = {item.get("engine") for item in factor_results if item.get("engine")}
    chips: list[str] = []

    if "mercury" in engines or backtest_result.get("mercury_results"):
        chips.append("交易级回测")
    if "local_fallback" in engines:
        chips.append("本地 fallback")
    if backtest_result.get("uses_synthetic_factor_data"):
        chips.append("合成因子信号")
    elif backtest_result.get("is_mock"):
        chips.append("Mock 数据")

    if "mercury" in engines and "local_fallback" in engines:
        label = "Mercury + 本地 fallback"
    elif "mercury" in engines or backtest_result.get("mercury_results"):
        label = "Mercury 交易级回测"
    elif "local_fallback" in engines:
        label = "本地 fallback"
    elif backtest_result.get("is_mock"):
        label = "Mock 数据"
    else:
        label = "待回测"

    return {
        "label": label,
        "chips": chips,
        "engines": sorted(engine for engine in engines if engine),
    }


CHART_LABELS = {
    "ic_series": "IC 序列",
    "layer_cumreturns": "分层累计收益",
    "long_short_nav": "多空净值",
}


def group_charts_by_factor(
    charts: dict[str, Any],
    factor_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Group flat chart keys by factor for clearer frontend rendering."""
    grouped: list[dict[str, Any]] = []
    consumed: set[str] = set()
    for factor in factor_results:
        fid = factor.get("factor_id", "")
        factor_charts = []
        for suffix, label in CHART_LABELS.items():
            key = f"{fid}_{suffix}"
            if key in charts:
                factor_charts.append({"key": key, "label": label, "figure": charts[key]})
                consumed.add(key)
        grouped.append(
            {
                "factor_id": fid,
                "factor_name": factor.get("factor_name", fid),
                "engine": factor.get("engine", ""),
                "charts": factor_charts,
            }
        )

    leftovers = [
        {"key": key, "label": key, "figure": figure}
        for key, figure in charts.items()
        if key not in consumed
    ]
    if leftovers:
        grouped.append(
            {
                "factor_id": "_other",
                "factor_name": "其他图表",
                "engine": "",
                "charts": leftovers,
            }
        )
    return grouped
