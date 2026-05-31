"""Backtest engine with HybridBacktestEngine and Mercury integration."""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from alpha_workbench.backtest.factor_backtest import mock_run_backtest
from alpha_workbench.backtest.hybrid_engine import HybridBacktestEngine
from alpha_workbench.backtest.mercury_adapter import MercuryConfig
from alpha_workbench.data.sample_data import generate_sample_data, create_mock_factorspec
from alpha_workbench.schemas.backtest_schemas import BacktestInput, FactorSpec, ResearchSpec

logger = logging.getLogger(__name__)


def run_backtest(
    factor_specs: list[dict[str, Any]],
    research_spec: dict[str, Any] | None = None,
    *,
    factor_data_dict: dict[str, pd.DataFrame] | None = None,
    price_data: pd.DataFrame | None = None,
    returns_data: pd.DataFrame | None = None,
    enable_mercury: bool = True,
) -> dict[str, Any]:
    """Run backtest for multiple factors using HybridBacktestEngine.

    Two-pass strategy:
      1. Local metrics for ALL factors (fast — IC, layers, long-short, charts).
      2. Mercury remote backtest ONLY for the best factor (by sharpe_ratio).

    Returns a dict with:
        research_universe: str
        factor_results:    list[dict]  -- per-factor metrics sorted by sharpe desc
        mercury_results:   dict        -- Mercury summary for the best factor only
        charts:            dict        -- serialisable chart references
        is_mock:           bool
        notes:             list[str]
    """
    if not factor_specs:
        logger.warning("run_backtest called with empty factor_specs")
        return {
            "research_universe": (research_spec or {}).get("universe", ""),
            "factor_results": [],
            "notes": ["No factor specs provided."],
            "is_mock": True,
        }

    rs = research_spec or {}
    n_quantiles = rs.get("backtest", {}).get("groups", 5)
    universe = rs.get("universe", "sample_universe")

    # ── shared data caches (regenerated on first use) ──────────────────────
    shared_price: pd.DataFrame | None = price_data
    shared_returns: pd.DataFrame | None = returns_data
    used_mock_data = False

    # ── local engine (never touches Mercury) ───────────────────────────────
    local_engine = HybridBacktestEngine(
        enable_plotting=True,
        enable_llm_explanation=False,
        mercury_config=None,
        use_mercury=False,
    )

    factor_results: list[dict[str, Any]] = []
    charts: dict[str, Any] = {}
    notes: list[str] = []

    try:
        # ── Pass 1: local metrics for every factor ─────────────────────────
        for factor_dict in factor_specs:
            fid = factor_dict.get("factor_id", "UNKNOWN")
            fname = factor_dict.get("factor_name", fid)
            logger.info("Local backtest: %s (%s)", fname, fid)

            if factor_data_dict and fid in factor_data_dict:
                fdata = factor_data_dict[fid]
            else:
                used_mock_data = True
                fdata, pdata, rdata = generate_sample_data(
                    n_stocks=50, n_days=120, seed=hash(fid) % 2**31,
                )
                if shared_price is None:
                    shared_price = pdata
                if shared_returns is None:
                    shared_returns = rdata

            if shared_price is None:
                used_mock_data = True
                _, shared_price, shared_returns = generate_sample_data(n_stocks=50, n_days=120)

            common_dates = fdata.index.intersection(shared_price.index)
            common_stocks = fdata.columns.intersection(shared_price.columns)
            if len(common_dates) < 10 or len(common_stocks) < 10:
                notes.append(f"Skipped {fid}: too few dates/stocks")
                continue

            fdata = fdata.loc[common_dates, common_stocks]
            price_use = shared_price.loc[common_dates, common_stocks]

            rdata_use = None
            if shared_returns is not None:
                r_idx = shared_returns.index.intersection(common_dates)
                r_cols = shared_returns.columns.intersection(common_stocks)
                if len(r_idx) >= 10 and len(r_cols) >= 10:
                    rdata_use = shared_returns.loc[r_idx, r_cols]

            factor_spec = _build_factor_spec(factor_dict)
            input_data = BacktestInput(
                factor_spec=factor_spec,
                factor_data=fdata,
                price_data=price_use,
                returns_data=rdata_use,
                n_quantiles=n_quantiles,
            )

            report = local_engine.run_backtest(input_data)

            ic = report.metrics.ic_metrics
            ls = report.metrics.long_short_metrics
            layer = report.metrics.layer_metrics

            factor_results.append({
                "factor_id": report.factor_id,
                "factor_name": report.factor_name,
                "ic_mean": ic.ic_mean,
                "ic_std": ic.ic_std,
                "icir": ic.icir,
                "ic_positive_ratio": ic.ic_positive_ratio,
                "ic_tstat": ic.ic_tstat,
                "rank_ic_mean": ic.rank_ic_mean,
                "rank_ic_std": ic.rank_ic_std,
                "rank_icir": ic.rank_icir,
                "rank_ic_positive_ratio": ic.rank_ic_positive_ratio,
                "rank_ic_tstat": ic.rank_ic_tstat,
                "long_short_return": ls.annual_return,
                "sharpe_ratio": ls.sharpe_ratio,
                "max_drawdown": ls.max_drawdown,
                "annual_volatility": ls.annual_volatility,
                "layer_returns": layer.layer_returns,
            })

            if report.figures.ic_series_plot is not None:
                charts[f"{fid}_ic_series"] = report.figures.ic_series_plot
            if report.figures.layer_cumreturn_plot is not None:
                charts[f"{fid}_layer_cumreturns"] = report.figures.layer_cumreturn_plot
            if report.figures.long_short_nav_plot is not None:
                charts[f"{fid}_long_short_nav"] = report.figures.long_short_nav_plot

        factor_results.sort(key=lambda r: r.get("sharpe_ratio", 0.0), reverse=True)

        # ── Pass 2: Mercury ONLY for the best factor ───────────────────────
        mercury_results: dict[str, Any] = {}
        if enable_mercury and factor_results:
            best = factor_results[0]
            best_fid = best["factor_id"]
            logger.info("Mercury pass: best factor = %s (sharpe=%.3f)", best_fid, best["sharpe_ratio"])

            best_spec = next(
                (f for f in factor_specs if f.get("factor_id") == best_fid),
                factor_specs[0],
            )
            best_fdata = (
                factor_data_dict.get(best_fid) if factor_data_dict and best_fid in factor_data_dict
                else None
            )
            if best_fdata is None:
                best_fdata, _, _ = generate_sample_data(
                    n_stocks=50, n_days=120, seed=hash(best_fid) % 2**31,
                )

            mercury_config = MercuryConfig()
            mercury_engine = HybridBacktestEngine(
                enable_plotting=True,   # required for raw_data passthrough
                enable_llm_explanation=False,
                mercury_config=mercury_config,
                use_mercury=True,
            )
            try:
                common_dates = best_fdata.index.intersection(shared_price.index)
                common_stocks = best_fdata.columns.intersection(shared_price.columns)
                best_fdata = best_fdata.loc[common_dates, common_stocks]
                best_price = shared_price.loc[common_dates, common_stocks]

                best_input = BacktestInput(
                    factor_spec=_build_factor_spec(best_spec),
                    factor_data=best_fdata,
                    price_data=best_price,
                    n_quantiles=n_quantiles,
                )
                mercury_report = mercury_engine.run_backtest(best_input)

                raw = mercury_report.raw_data
                if raw:
                    mr = raw.get("mercury_response")
                    if mr and mr.get("summary"):
                        enriched = dict(mr["summary"])
                        if mr.get("execution_view"):
                            enriched["execution_view"] = mr["execution_view"]
                        if mr.get("metrics"):
                            enriched["metrics"] = mr["metrics"]
                        if mr.get("job_id"):
                            enriched["job_id"] = mr["job_id"]
                        if mr.get("status"):
                            enriched["status"] = mr["status"]
                        mercury_results[best_fid] = enriched
                        logger.info("Mercury result for %s: sharpe=%.3f", best_fid,
                                      enriched.get("sharpe", 0))
            except Exception:
                logger.exception("Mercury pass failed for %s", best_fid)
            finally:
                mercury_engine.close()

        n_m = len(mercury_results)
        logger.info("Backtest complete: %d factors, %d Mercury results, mock=%s",
                     len(factor_results), n_m, used_mock_data)

    except Exception:
        logger.exception("Hybrid backtest failed, falling back to mock")
        mock_result = mock_run_backtest(factor_specs, rs)
        factor_results = []
        for mr in mock_result.get("results", []):
            m = mr.get("metrics", {})
            ic_m = getattr(m, "ic_metrics", None)
            ls_m = getattr(m, "long_short_metrics", None)
            layer_m = getattr(m, "layer_metrics", None)
            factor_results.append({
                "factor_id": mr.get("factor_id", ""),
                "factor_name": mr.get("factor_name", ""),
                "ic_mean": getattr(ic_m, "ic_mean", 0.0) if ic_m else 0.0,
                "ic_std": getattr(ic_m, "ic_std", 0.0) if ic_m else 0.0,
                "icir": getattr(ic_m, "icir", 0.0) if ic_m else 0.0,
                "ic_positive_ratio": getattr(ic_m, "ic_positive_ratio", 0.0) if ic_m else 0.0,
                "ic_tstat": getattr(ic_m, "ic_tstat", 0.0) if ic_m else 0.0,
                "rank_ic_mean": getattr(ic_m, "rank_ic_mean", 0.0) if ic_m else 0.0,
                "rank_ic_std": getattr(ic_m, "rank_ic_std", 0.0) if ic_m else 0.0,
                "rank_icir": getattr(ic_m, "rank_icir", 0.0) if ic_m else 0.0,
                "rank_ic_positive_ratio": getattr(ic_m, "rank_ic_positive_ratio", 0.0) if ic_m else 0.0,
                "rank_ic_tstat": getattr(ic_m, "rank_ic_tstat", 0.0) if ic_m else 0.0,
                "long_short_return": getattr(ls_m, "annual_return", 0.0) if ls_m else 0.0,
                "sharpe_ratio": getattr(ls_m, "sharpe_ratio", 0.0) if ls_m else 0.0,
                "max_drawdown": getattr(ls_m, "max_drawdown", 0.0) if ls_m else 0.0,
                "annual_volatility": getattr(ls_m, "annual_volatility", 0.0) if ls_m else 0.0,
                "layer_returns": getattr(layer_m, "layer_returns", {}) if layer_m else {},
            })
        return {
            "research_universe": universe,
            "factor_results": factor_results,
            "mercury_results": {},
            "charts": {},
            "is_mock": True,
            "notes": ["Hybrid engine encountered an error; results are synthetic."],
        }

    finally:
        local_engine.close()

    if used_mock_data:
        notes.append("No real factor data provided; used synthetic sample data.")

    return {
        "research_universe": universe,
        "factor_results": factor_results,
        "mercury_results": mercury_results,
        "charts": charts,
        "is_mock": used_mock_data,
        "notes": notes,
    }


def _build_factor_spec(factor_dict: dict[str, Any]) -> FactorSpec:
    """Convert a team_work_plan.md FactorSpec dict to a Pydantic FactorSpec."""
    try:
        return FactorSpec.from_dict(factor_dict)
    except Exception:
        mock = create_mock_factorspec(factor_dict.get("factor_id", "momentum"))
        mock["factor_name"] = factor_dict.get("factor_name", mock.get("factor_name", ""))
        mock["description"] = factor_dict.get("plain_description") or factor_dict.get(
            "description", ""
        )
        return FactorSpec.from_dict(mock)
