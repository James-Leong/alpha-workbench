"""Backtest engine with HybridBacktestEngine and Mercury integration."""

from __future__ import annotations

import logging
import hashlib
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from alpha_workbench.backtest.factor_backtest import mock_run_backtest
from alpha_workbench.backtest.hybrid_engine import HybridBacktestEngine
from alpha_workbench.backtest.mercury_adapter import MercuryConfig
from alpha_workbench.data.sample_data import generate_sample_data, create_mock_factorspec
from alpha_workbench.data.universe import resolve_universe
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
    require_factor_data: bool = False,
    market_data_is_mock: bool = False,
) -> dict[str, Any]:
    """Run backtest for multiple factors using HybridBacktestEngine.

    Strategy:
      1. Run Mercury backtest for every factor when enabled.
      2. Fall back to local metrics only when Mercury is unavailable or fails.

    Returns a dict with:
        research_universe: str
        factor_results:    list[dict]  -- per-factor metrics sorted by sharpe desc
        mercury_results:   dict        -- Mercury summary keyed by factor id
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

    if require_factor_data:
        available = set(factor_data_dict or {})
        required = {str(item.get("factor_id", "")) for item in factor_specs}
        missing = sorted(required - available)
        if missing:
            raise ValueError(
                "Strict factor-data mode requires computed data for every factor; "
                f"missing: {', '.join(missing)}"
            )
        for factor_id in sorted(required):
            _validate_strict_factor_frame(factor_id, factor_data_dict[factor_id])

    rs = research_spec or {}
    n_quantiles = rs.get("backtest", {}).get("groups", 5)
    universe = rs.get("universe", "sample_universe")
    securities = resolve_universe(universe)
    research_model = _build_research_spec(rs)
    start_date = _parse_date(rs.get("sample_window", {}).get("start"))
    end_date = _parse_date(rs.get("sample_window", {}).get("end"))
    commission_rate = float(rs.get("transaction_cost_bps", 10)) / 10000

    # ── shared data caches (regenerated on first use) ──────────────────────
    shared_price: pd.DataFrame | None = price_data
    shared_returns: pd.DataFrame | None = returns_data
    uses_synthetic_factor_data = False
    uses_mock_market_data = market_data_is_mock

    factor_results: list[dict[str, Any]] = []
    mercury_results: dict[str, Any] = {}
    mercury_attempts: dict[str, Any] = {}
    charts: dict[str, Any] = {}
    notes: list[str] = []
    mercury_config = MercuryConfig()
    mercury_enabled = bool(enable_mercury)

    try:
        mercury_engine = None
        local_engine = None

        if enable_mercury:
            mercury_engine = HybridBacktestEngine(
                enable_plotting=True,
                enable_llm_explanation=False,
                mercury_config=mercury_config,
                use_mercury=True,
            )
            if not mercury_engine.use_mercury:
                notes.append(
                    f"Mercury service unavailable at {mercury_config.base_url}; used local fallback."
                )

        local_engine = HybridBacktestEngine(
            enable_plotting=True,
            enable_llm_explanation=False,
            mercury_config=None,
            use_mercury=False,
        )

        # ── Run every factor, preferring Mercury and falling back locally ───
        for factor_idx, factor_dict in enumerate(factor_specs):
            fid = factor_dict.get("factor_id", "UNKNOWN")
            fname = factor_dict.get("factor_name", fid)
            logger.info("Backtest: %s (%s)", fname, fid)

            if factor_data_dict and fid in factor_data_dict:
                fdata = factor_data_dict[fid]
            else:
                uses_synthetic_factor_data = True
                if shared_price is None:
                    uses_mock_market_data = True
                    _, shared_price, shared_returns = generate_sample_data(
                        n_stocks=len(securities),
                        n_days=120,
                        start_date=start_date.isoformat() if start_date else None,
                        end_date=end_date.isoformat() if end_date else None,
                        securities=securities,
                        seed=_stable_seed(f"{universe}:shared_market"),
                    )
                if shared_returns is None:
                    shared_returns = shared_price.pct_change().shift(-1)
                fdata = _generate_synthetic_factor_data(shared_returns, fid, factor_idx)

            if shared_price is None:
                uses_mock_market_data = True
                _, shared_price, shared_returns = generate_sample_data(
                    n_stocks=len(securities),
                    n_days=120,
                    start_date=start_date.isoformat() if start_date else None,
                    end_date=end_date.isoformat() if end_date else None,
                    securities=securities,
                )

            common_dates = fdata.index.intersection(shared_price.index)
            common_stocks = fdata.columns.intersection(shared_price.columns)
            if len(common_dates) < 10 or len(common_stocks) < 10:
                if require_factor_data:
                    raise ValueError(
                        "Strict factor-data mode requires at least 10 overlapping dates and "
                        f"10 overlapping symbols for {fid}; got "
                        f"{len(common_dates)} dates and {len(common_stocks)} symbols"
                    )
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
                research_spec=research_model,
                start_date=start_date,
                end_date=end_date,
                n_quantiles=n_quantiles,
                commission_rate=commission_rate,
            )

            report, engine_name = _run_with_mercury_fallback(
                input_data=input_data,
                mercury_engine=mercury_engine,
                local_engine=local_engine,
                notes=notes,
            )

            raw = report.raw_data or {}
            mr = raw.get("mercury_response")
            if mr:
                mercury_attempts[fid] = _compact_mercury_response(mr)
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
                mercury_results[fid] = enriched

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
                "engine": engine_name,
            })

            if report.figures.ic_series_plot is not None:
                charts[f"{fid}_ic_series"] = report.figures.ic_series_plot
            if report.figures.layer_cumreturn_plot is not None:
                charts[f"{fid}_layer_cumreturns"] = report.figures.layer_cumreturn_plot
            if report.figures.long_short_nav_plot is not None:
                charts[f"{fid}_long_short_nav"] = report.figures.long_short_nav_plot

        factor_results.sort(key=lambda r: r.get("sharpe_ratio", 0.0), reverse=True)

        n_m = len(mercury_results)
        logger.info(
            "Backtest complete: %d factors, %d Mercury results, synthetic_factor=%s, "
            "mock_market=%s",
            len(factor_results),
            n_m,
            uses_synthetic_factor_data,
            uses_mock_market_data,
        )

    except Exception:
        if require_factor_data:
            raise
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
            "mercury_status": {
                "enabled": bool(enable_mercury),
                "base_url": mercury_config.base_url,
                "attempted": False,
                "success_count": 0,
                "fallback": True,
                "notes": ["Hybrid engine encountered an error before Mercury status could be collected."],
            },
            "charts": {},
            "is_mock": True,
            "uses_synthetic_factor_data": True,
            "uses_mock_market_data": True,
            "notes": ["Hybrid engine encountered an error; results are synthetic."],
        }

    finally:
        if "mercury_engine" in locals() and mercury_engine is not None:
            mercury_engine.close()
        if "local_engine" in locals() and local_engine is not None:
            local_engine.close()

    if uses_synthetic_factor_data:
        notes.append("No real factor data provided; used synthetic factor signals.")
    if uses_mock_market_data:
        notes.append("No market data provided; used deterministic sample market data.")

    result_is_mock = (uses_synthetic_factor_data or uses_mock_market_data) and not mercury_results
    mercury_status = {
        "enabled": mercury_enabled,
        "base_url": mercury_config.base_url,
        "attempted": bool(mercury_attempts),
        "success_count": len(mercury_results),
        "attempt_count": len(mercury_attempts),
        "fallback": len(mercury_results) == 0,
        "attempts": mercury_attempts,
        "notes": [
            note for note in notes
            if "Mercury" in note or "mercury" in note
        ],
    }

    return {
        "research_universe": universe,
        "factor_results": factor_results,
        "mercury_results": mercury_results,
        "mercury_status": mercury_status,
        "charts": charts,
        "is_mock": result_is_mock,
        "uses_synthetic_factor_data": uses_synthetic_factor_data,
        "uses_mock_market_data": uses_mock_market_data,
        "notes": notes,
    }


def _validate_strict_factor_frame(factor_id: str, frame: object) -> None:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError(f"Strict factor data for {factor_id} must be a pandas DataFrame")
    if frame.empty:
        raise ValueError(f"Strict factor data for {factor_id} cannot be empty")
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise TypeError(f"Strict factor data for {factor_id} must use a DatetimeIndex")
    if not frame.index.is_unique or not frame.index.is_monotonic_increasing:
        raise ValueError(
            f"Strict factor data for {factor_id} must have a unique, increasing index"
        )
    if not frame.columns.is_unique:
        raise ValueError(f"Strict factor data for {factor_id} must have unique columns")
    if len(frame.index) < 10 or len(frame.columns) < 10:
        raise ValueError(
            f"Strict factor data for {factor_id} requires at least 10 dates and 10 symbols"
        )


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


def _generate_synthetic_factor_data(
    returns_data: pd.DataFrame,
    factor_id: str,
    factor_idx: int,
) -> pd.DataFrame:
    """Create synthetic factor values aligned with one shared return matrix."""
    rng = np.random.default_rng(_stable_seed(f"{factor_id}:{factor_idx}:factor"))
    clean_returns = returns_data.copy()
    cross_sectional_std = clean_returns.stack().std()
    noise_scale = float(cross_sectional_std) if pd.notna(cross_sectional_std) else 0.02
    noise = rng.normal(0.0, noise_scale, clean_returns.shape)

    signal_strength = max(0.35, 0.8 - factor_idx * 0.18)
    factor_values = signal_strength * clean_returns.fillna(0.0).to_numpy() + noise
    factor_data = pd.DataFrame(
        factor_values,
        index=clean_returns.index,
        columns=clean_returns.columns,
    )
    factor_data = factor_data.mask(clean_returns.isna())

    missing_mask = rng.random(factor_data.shape) < 0.03
    return factor_data.mask(missing_mask)


def _stable_seed(value: str) -> int:
    """Return a process-stable integer seed for repeatable demo data."""
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _run_with_mercury_fallback(
    *,
    input_data: BacktestInput,
    mercury_engine: HybridBacktestEngine | None,
    local_engine: HybridBacktestEngine,
    notes: list[str],
) -> tuple[Any, str]:
    """Run one factor through Mercury first, falling back to local on failure."""
    fid = input_data.factor_spec.factor_id
    if mercury_engine is not None and mercury_engine.use_mercury:
        try:
            report = mercury_engine.run_backtest(input_data)
            raw = report.raw_data or {}
            if (raw.get("mercury_response") or {}).get("summary"):
                return report, "mercury"
            notes.append(f"Mercury returned no result for {fid}; used local fallback.")
            if raw.get("mercury_response"):
                return report, "local_fallback"
        except Exception as exc:
            logger.exception("Mercury backtest failed for %s; falling back to local", fid)
            notes.append(f"Mercury failed for {fid}: {exc}; used local fallback.")

    return local_engine.run_backtest(input_data), "local_fallback"


def _build_research_spec(research_spec: dict[str, Any]) -> ResearchSpec | None:
    """Convert frontend research config dict to ResearchSpec when available."""
    if not research_spec:
        return None
    return ResearchSpec.from_dict(research_spec)


def _parse_date(value: Any) -> date | None:
    """Parse optional frontend date values into date objects."""
    if not value:
        return None
    return pd.to_datetime(value).date()


def _compact_mercury_response(response: dict[str, Any]) -> dict[str, Any]:
    """Keep Mercury diagnostics useful without storing oversized execution payloads."""

    compact: dict[str, Any] = {
        "job_id": response.get("job_id"),
        "status": response.get("status"),
        "error": response.get("error"),
        "message": response.get("message"),
    }
    if response.get("summary"):
        compact["summary"] = response["summary"]
    if response.get("metrics"):
        compact["metrics"] = response["metrics"]
    run_spec = response.get("run_spec")
    if isinstance(run_spec, dict):
        compact["run_spec"] = run_spec
    return {key: value for key, value in compact.items() if value not in (None, "")}
