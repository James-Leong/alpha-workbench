"""Data access boundary exposed to factor plugins."""

from __future__ import annotations

from collections.abc import Hashable, Mapping, Sequence

import pandas as pd


class FactorContext:
    """Read-only-by-copy access to the input matrices for a factor run."""

    def __init__(
        self,
        fields: Mapping[str, pd.DataFrame],
        *,
        trading_dates: Sequence[object] | pd.DatetimeIndex | None = None,
        symbols: Sequence[Hashable] | None = None,
    ) -> None:
        if not fields and (trading_dates is None or symbols is None):
            raise ValueError(
                "trading_dates and symbols are required when fields is empty"
            )

        copied_fields: dict[str, pd.DataFrame] = {}
        for name, frame in fields.items():
            if not isinstance(name, str) or not name:
                raise ValueError("field names must be non-empty strings")
            if not isinstance(frame, pd.DataFrame):
                raise TypeError(f"field '{name}' must be a pandas DataFrame")
            copied_fields[name] = frame.copy(deep=True)

        first_frame = next(iter(copied_fields.values()), None)
        source_dates = trading_dates if trading_dates is not None else first_frame.index
        source_symbols = symbols if symbols is not None else first_frame.columns

        self._fields = copied_fields
        self._trading_dates = pd.DatetimeIndex(source_dates).copy()
        self._symbols = list(source_symbols)

        if not self._trading_dates.is_unique:
            raise ValueError("trading_dates must be unique")
        if len(self._symbols) != len(set(self._symbols)):
            raise ValueError("symbols must be unique")
        expected_columns = pd.Index(self._symbols)
        for name, frame in copied_fields.items():
            if not isinstance(frame.index, pd.DatetimeIndex):
                raise TypeError(f"field '{name}' must use a DatetimeIndex")
            if not frame.index.equals(self._trading_dates):
                raise ValueError(f"field '{name}' index must match trading_dates exactly")
            if not frame.columns.equals(expected_columns):
                raise ValueError(f"field '{name}' columns must match symbols exactly")

    def field(self, name: str) -> pd.DataFrame:
        """Return an isolated copy of a named input field."""

        try:
            return self._fields[name].copy(deep=True)
        except KeyError as exc:
            available = ", ".join(sorted(self._fields)) or "<none>"
            raise KeyError(f"unknown factor field '{name}'; available: {available}") from exc

    @property
    def field_names(self) -> tuple[str, ...]:
        return tuple(self._fields)

    @property
    def trading_dates(self) -> pd.DatetimeIndex:
        return self._trading_dates.copy()

    @property
    def symbols(self) -> list[Hashable]:
        return self._symbols.copy()
