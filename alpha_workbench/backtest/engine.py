"""Mock backtest engine for the first demo flow."""

from __future__ import annotations

from typing import Any


MOCK_METRICS = {
    "earnings_surprise_adj_001": {
        "ic_mean": 0.072,
        "ic_positive_ratio": 0.64,
        "long_short_return": 0.118,
        "max_drawdown": -0.046,
        "turnover": 0.32,
    },
    "pre_announcement_underreaction_002": {
        "ic_mean": 0.058,
        "ic_positive_ratio": 0.59,
        "long_short_return": 0.092,
        "max_drawdown": -0.052,
        "turnover": 0.41,
    },
    "quality_surprise_combo_003": {
        "ic_mean": 0.061,
        "ic_positive_ratio": 0.61,
        "long_short_return": 0.101,
        "max_drawdown": -0.039,
        "turnover": 0.28,
    },
}


def _mock_nav_series() -> list[dict[str, Any]]:
    dates = [
        "2023-01-31",
        "2023-02-28",
        "2023-03-31",
        "2023-04-30",
        "2023-05-31",
        "2023-06-30",
        "2023-07-31",
        "2023-08-31",
    ]
    long_short_nav = [1.00, 1.018, 1.011, 1.036, 1.052, 1.048, 1.075, 1.091]
    benchmark_nav = [1.00, 1.006, 0.998, 1.012, 1.019, 1.014, 1.027, 1.033]
    return [
        {
            "date": date,
            "long_short_nav": long_nav,
            "benchmark_nav": bench_nav,
        }
        for date, long_nav, bench_nav in zip(dates, long_short_nav, benchmark_nav)
    ]


def run_backtest(
    factor_specs: list[dict[str, Any]],
    research_spec: dict[str, Any],
) -> dict[str, Any]:
    factor_results = []
    for spec in factor_specs:
        metrics = MOCK_METRICS.get(spec["factor_id"], MOCK_METRICS["earnings_surprise_adj_001"])
        factor_results.append(
            {
                "factor_id": spec["factor_id"],
                "factor_name": spec["factor_name"],
                **metrics,
            }
        )

    factor_results.sort(key=lambda row: row["long_short_return"], reverse=True)
    return {
        "research_universe": research_spec["universe"],
        "factor_results": factor_results,
        "nav_series": _mock_nav_series(),
        "notes": [
            "当前回测为 mock 数据，用于模块联调和演示。",
            "真实实现需要替换为样例 CSV 或正式行情/财务数据。",
        ],
        "is_mock": True,
    }
