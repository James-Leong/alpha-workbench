"""Behavioral audit for future-data leakage in factor plugins."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd

from alpha_workbench.factor_runtime.context import FactorContext
from alpha_workbench.factor_runtime.runner import run_factor


class LookaheadAuditError(ValueError):
    """Raised when future input mutations change historical factor values."""


def run_lookahead_perturbation_audit(
    calculate: Callable[[FactorContext, dict[str, Any]], object],
    context: FactorContext,
    baseline: pd.DataFrame,
    required_fields: Sequence[str],
    *,
    params: Mapping[str, Any] | None = None,
    cutoff_fraction: float | None = None,
    cutoff_fractions: Sequence[float] = (0.3, 0.5, 0.7),
) -> dict[str, Any]:
    """Mutate future inputs at several cutoffs and verify historical stability."""

    dates = context.trading_dates
    if len(dates) < 4:
        raise ValueError("lookahead audit requires at least four trading dates")
    field_names = list(dict.fromkeys(required_fields))
    if not field_names:
        raise ValueError("lookahead audit requires at least one input field")

    fractions = (cutoff_fraction,) if cutoff_fraction is not None else tuple(cutoff_fractions)
    if not fractions:
        raise ValueError("lookahead audit requires at least one cutoff fraction")
    if any(not 0.25 <= fraction <= 0.9 for fraction in fractions):
        raise ValueError("cutoff fractions must be between 0.25 and 0.9")

    cutoff_reports: list[dict[str, Any]] = []
    seen_positions: set[int] = set()
    for fraction in fractions:
        cutoff_position = min(len(dates) - 2, max(1, int(len(dates) * fraction)))
        if cutoff_position in seen_positions:
            continue
        seen_positions.add(cutoff_position)
        cutoff_date = dates[cutoff_position]
        mutation_start = dates[cutoff_position + 1]
        perturbed_fields = {
            name: _perturb_frame_after(context.field(name), cutoff_date)
            for name in field_names
        }
        perturbed_context = FactorContext(
            perturbed_fields,
            trading_dates=dates,
            symbols=context.symbols,
        )
        perturbed_result = run_factor(calculate, perturbed_context, dict(params or {}))

        historical_baseline = baseline.loc[:cutoff_date]
        historical_perturbed = perturbed_result.loc[:cutoff_date]
        equal_cells = historical_baseline.eq(historical_perturbed) | (
            historical_baseline.isna() & historical_perturbed.isna()
        )
        changed_cells = int((~equal_cells).to_numpy().sum())
        if changed_cells:
            changed_dates = equal_cells.index[(~equal_cells).any(axis=1)]
            first_changed = pd.Timestamp(changed_dates[0]).date().isoformat()
            raise LookaheadAuditError(
                "future input perturbation changed historical factor values: "
                f"changed_cells={changed_cells}, first_changed_date={first_changed}, "
                f"audit_cutoff={cutoff_date.date().isoformat()}"
            )
        cutoff_reports.append(
            {
                "cutoff_fraction": fraction,
                "cutoff_date": cutoff_date.date().isoformat(),
                "mutation_start": mutation_start.date().isoformat(),
                "audited_rows": int(len(historical_baseline)),
                "changed_cells": 0,
            }
        )

    return {
        "name": "lookahead_perturbation",
        "status": "passed",
        "cutoffs": cutoff_reports,
        "audited_rows": sum(report["audited_rows"] for report in cutoff_reports),
        "perturbed_fields": field_names,
        "changed_cells": 0,
    }


def _perturb_frame_after(frame: pd.DataFrame, cutoff_date: pd.Timestamp) -> pd.DataFrame:
    perturbed = frame.copy(deep=True)
    try:
        index_dates = pd.DatetimeIndex(pd.to_datetime(perturbed.index, errors="raise"))
    except (TypeError, ValueError) as exc:
        raise ValueError("lookahead audit fields must use date-like indexes") from exc
    future_mask = index_dates > cutoff_date
    if not future_mask.any():
        return perturbed

    future_positions = np.flatnonzero(future_mask)
    for column_position, column in enumerate(perturbed.columns):
        series = perturbed[column]
        if pd.api.types.is_datetime64_any_dtype(series.dtype):
            values = [
                index_dates[position] + pd.Timedelta(days=365 + column_position)
                for position in future_positions
            ]
        elif pd.api.types.is_numeric_dtype(series.dtype):
            original = pd.to_numeric(series.iloc[future_positions], errors="coerce").fillna(0.0)
            values = (
                original.to_numpy(dtype=float) * -11.0
                + 1_000_000.0
                + np.arange(len(future_positions), dtype=float)
                + column_position
            )
        else:
            non_null = series.dropna()
            parsed_dates = pd.to_datetime(non_null, errors="coerce")
            if len(non_null) and parsed_dates.notna().all():
                values = [
                    index_dates[position] + pd.Timedelta(days=365 + column_position)
                    for position in future_positions
                ]
            else:
                values = [
                    f"__future_perturbed_{position}_{column_position}__"
                    for position in future_positions
                ]
        perturbed.iloc[future_positions, column_position] = values
    return perturbed
