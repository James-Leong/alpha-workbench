"""Execution and output validation for loaded factor plugins."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Callable

import numpy as np
import pandas as pd

from alpha_workbench.factor_runtime.context import FactorContext


class FactorResultValidationError(ValueError):
    """Raised when calculate() returns a matrix outside the factor contract."""


def validate_factor_result(
    result: object,
    context: FactorContext,
    *,
    lookback_days: int = 0,
) -> pd.DataFrame:
    if not isinstance(result, pd.DataFrame):
        raise FactorResultValidationError("calculate() must return a pandas DataFrame")
    if not isinstance(result.index, pd.DatetimeIndex):
        raise FactorResultValidationError("factor result index must be a DatetimeIndex")
    if not result.index.is_unique:
        raise FactorResultValidationError("factor result index must be unique")
    if not result.columns.is_unique:
        raise FactorResultValidationError("factor result columns must be unique")
    if not result.index.equals(context.trading_dates):
        raise FactorResultValidationError(
            "factor result index must exactly match context.trading_dates"
        )
    if not result.columns.equals(pd.Index(context.symbols)):
        raise FactorResultValidationError(
            "factor result columns must exactly match context.symbols"
        )
    if not all(pd.api.types.is_numeric_dtype(dtype) for dtype in result.dtypes):
        raise FactorResultValidationError("factor result values must be numeric")
    values = result.to_numpy(dtype=float)
    if np.isinf(values).any():
        raise FactorResultValidationError("factor result cannot contain infinite values")
    eligible_rows = max(0, len(result.index) - lookback_days)
    minimum_finite = max(1, eligible_rows * len(result.columns) // 100)
    if int(np.isfinite(values).sum()) < minimum_finite:
        raise FactorResultValidationError(
            "factor result has insufficient finite coverage after its lookback window"
        )
    return result


def run_factor(
    calculate: Callable[[FactorContext, dict[str, Any]], object],
    context: FactorContext,
    params: Mapping[str, Any] | None = None,
    *,
    lookback_days: int = 0,
) -> pd.DataFrame:
    result = calculate(context, dict(params or {}))
    return validate_factor_result(result, context, lookback_days=lookback_days)
