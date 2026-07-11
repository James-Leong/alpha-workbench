"""Shared contracts and validation for field-oriented long-format data."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

import pandas as pd


LONG_FORMAT_COLUMNS = ("trade_date", "symbol", "value")


def normalize_long_frame(data: pd.DataFrame) -> pd.DataFrame:
    """Validate and normalize a ``trade_date, symbol, value`` frame."""
    if not isinstance(data, pd.DataFrame):
        raise TypeError("data must be a pandas DataFrame")

    missing = [column for column in LONG_FORMAT_COLUMNS if column not in data.columns]
    if missing:
        raise ValueError(f"long-format data is missing columns: {', '.join(missing)}")

    frame = data.loc[:, LONG_FORMAT_COLUMNS].copy()
    trade_dates = pd.to_datetime(frame["trade_date"], errors="raise")
    if isinstance(trade_dates.dtype, pd.DatetimeTZDtype):
        raise ValueError("trade_date must be timezone-naive calendar dates")
    frame["trade_date"] = trade_dates.dt.normalize()
    if frame["trade_date"].isna().any():
        raise ValueError("trade_date cannot contain null values")
    if frame["symbol"].isna().any():
        raise ValueError("symbol cannot contain null values")

    frame["symbol"] = frame["symbol"].astype(str)
    if frame["symbol"].str.strip().eq("").any():
        raise ValueError("symbol cannot contain empty values")
    if frame.duplicated(["trade_date", "symbol"]).any():
        raise ValueError("data contains duplicate trade_date/symbol rows")

    return frame.sort_values(["trade_date", "symbol"], kind="stable").reset_index(drop=True)


def filter_long_frame(
    data: pd.DataFrame,
    *,
    start_date: str | pd.Timestamp | None = None,
    end_date: str | pd.Timestamp | None = None,
    symbols: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Apply inclusive date and symbol filters to normalized long-format data."""
    frame = normalize_long_frame(data)
    if start_date is not None:
        frame = frame.loc[frame["trade_date"] >= pd.Timestamp(start_date).normalize()]
    if end_date is not None:
        frame = frame.loc[frame["trade_date"] <= pd.Timestamp(end_date).normalize()]
    if symbols is not None:
        frame = frame.loc[frame["symbol"].isin([str(symbol) for symbol in symbols])]
    return frame.reset_index(drop=True)


@runtime_checkable
class DataProvider(Protocol):
    """Provider protocol consumed by the data service and business code."""

    name: str

    def load(
        self,
        field: str,
        *,
        start_date: str | pd.Timestamp | None = None,
        end_date: str | pd.Timestamp | None = None,
        symbols: Sequence[str] | None = None,
    ) -> pd.DataFrame:
        """Load one standard field as a long-format frame."""

    def save(self, field: str, data: pd.DataFrame) -> None:
        """Persist one standard field from a long-format frame."""
