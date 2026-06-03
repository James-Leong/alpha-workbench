"""Helpers for applying frontend research configuration edits."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def apply_research_config_edits(
    research_spec: dict[str, Any],
    *,
    universe: str,
    holding_period: str,
    benchmark: str,
    rebalance_frequency: str,
    transaction_cost_bps: int,
    sample_start: str,
    sample_end: str,
    initial_cash: float | None = None,
) -> dict[str, Any]:
    """Return a ResearchSpec dict with user-confirmed frontend edits applied."""
    updated = deepcopy(research_spec)
    updated["universe"] = universe
    updated["holding_period"] = holding_period
    updated["benchmark"] = benchmark
    updated["rebalance_frequency"] = rebalance_frequency.strip().lower()
    updated["transaction_cost_bps"] = int(transaction_cost_bps)
    if initial_cash is not None:
        updated["initial_cash"] = float(initial_cash)
    updated["sample_window"] = {
        "start": sample_start,
        "end": sample_end,
    }
    updated.setdefault("backtest", {})
    updated["backtest"]["rebalance_frequency"] = updated["rebalance_frequency"]
    updated["backtest"]["transaction_cost_bps"] = updated["transaction_cost_bps"]
    if initial_cash is not None:
        updated["backtest"]["initial_cash"] = updated["initial_cash"]
    return updated
