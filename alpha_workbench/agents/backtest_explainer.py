"""Backtest explanation agent with real LLM and mock fallback."""

from __future__ import annotations

from typing import Any

import pandas as pd

from alpha_workbench.backtest.llm_explainer import BacktestExplainer
from alpha_workbench.schemas.backtest_schemas import (
    BacktestExplanationResult,
    BacktestMetrics,
    FactorSpec,
    ICMetrics,
    LayerMetrics,
    LongShortMetrics,
    TopPortfolioMetrics,
)


def _dict_to_metrics(factor_result: dict[str, Any]) -> BacktestMetrics:
    """Convert a single factor_result dict into BacktestMetrics."""
    return BacktestMetrics(
        ic_metrics=ICMetrics(
            ic_mean=factor_result.get("ic_mean", 0.0),
            ic_std=factor_result.get("ic_std", 0.0),
            icir=factor_result.get("icir", 0.0),
            ic_positive_ratio=factor_result.get("ic_positive_ratio", 0.0),
            ic_tstat=factor_result.get("ic_tstat", 0.0),
            rank_ic_mean=factor_result.get("rank_ic_mean", 0.0),
            rank_ic_std=factor_result.get("rank_ic_std", 0.0),
            rank_icir=factor_result.get("rank_icir", 0.0),
            rank_ic_positive_ratio=factor_result.get("rank_ic_positive_ratio", 0.0),
            rank_ic_tstat=factor_result.get("rank_ic_tstat", 0.0),
        ),
        layer_metrics=LayerMetrics(
            layer_returns=factor_result.get("layer_returns", {}),
            layer_cum_returns=pd.DataFrame(),  # placeholder — not needed for explanation
        ),
        long_short_metrics=LongShortMetrics(
            annual_return=factor_result.get("long_short_return", 0.0),
            annual_volatility=factor_result.get("annual_volatility", 0.0),
            sharpe_ratio=factor_result.get("sharpe_ratio", 0.0),
            max_drawdown=factor_result.get("max_drawdown", 0.0),
            cum_returns=pd.Series(dtype=float),  # placeholder
            top_portfolio=TopPortfolioMetrics(
                annual_return=factor_result.get("long_short_return", 0.0),
                annual_volatility=factor_result.get("annual_volatility", 0.0),
                sharpe_ratio=factor_result.get("sharpe_ratio", 0.0),
                max_drawdown=factor_result.get("max_drawdown", 0.0),
                cum_returns=pd.Series(dtype=float),  # placeholder
            ),
        ),
    )


def explain_backtest(backtest_result: dict[str, Any]) -> dict[str, Any]:
    """Explain backtest results using DeepSeek LLM, with mock fallback.

    Contract from team_work_plan.md:
        explain_backtest(backtest_results: dict) -> dict

    Uses the best-performing factor from factor_results as the analysis target.
    Returns BacktestExplanationResult.to_dict().
    """
    factor_results: list[dict[str, Any]] = backtest_result.get("factor_results", [])

    if not factor_results:
        return _mock_explain(backtest_result).to_dict()

    best = factor_results[0]

    # Build lightweight FactorSpec for the explainer
    factor_spec = FactorSpec(
        factor_id=best.get("factor_id", "UNKNOWN"),
        factor_name=best.get("factor_name", "Unknown Factor"),
        description=best.get("factor_name", ""),
    )

    metrics = _dict_to_metrics(best)

    explainer = BacktestExplainer()
    result = explainer.explain(
        metrics=metrics,
        factor_spec=factor_spec,
        backtest_period=backtest_result.get("research_universe", "Unknown"),
    )
    return result.to_dict()


def _mock_explain(backtest_result: dict[str, Any]) -> BacktestExplanationResult:
    """Fallback mock explanation when no factor results are available."""
    return BacktestExplanationResult(
        summary="当前回测数据不足，无法生成有意义的分析。请提供完整的因子数据后再试。",
        ic_analysis="数据不足，无法分析。",
        layer_analysis="数据不足，无法分析。",
        long_short_analysis="数据不足，无法分析。",
        turnover_analysis="数据不足，无法分析。",
        risk_assessment="数据不足，无法评估风险。",
        recommendations="建议使用真实数据运行回测。",
        is_fallback=True,
    )


# Preserve original mock function for standalone use
def mock_explain_backtest(backtest_result: dict[str, Any]) -> dict[str, Any]:
    """Legacy mock -- delegates to the real mock fallback."""
    return _mock_explain(backtest_result).to_dict()
