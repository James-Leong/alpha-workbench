"""In-memory provider for deterministic tests and local demos."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import pandas as pd

from alpha_workbench.data_sdk.base import filter_long_frame, normalize_long_frame


class InMemoryProvider:
    """Store independent field frames in memory using the provider protocol."""

    name = "in_memory"

    def __init__(self, fields: Mapping[str, pd.DataFrame] | None = None) -> None:
        self._fields: dict[str, pd.DataFrame] = {}
        for field, data in (fields or {}).items():
            self.save(field, data)

    def load(
        self,
        field: str,
        *,
        start_date: str | pd.Timestamp | None = None,
        end_date: str | pd.Timestamp | None = None,
        symbols: Sequence[str] | None = None,
    ) -> pd.DataFrame:
        if field not in self._fields:
            return pd.DataFrame(columns=["trade_date", "symbol", "value"])
        return filter_long_frame(
            self._fields[field],
            start_date=start_date,
            end_date=end_date,
            symbols=symbols,
        )

    def save(self, field: str, data: pd.DataFrame) -> None:
        if not field or not field.strip():
            raise ValueError("field must be a non-empty string")
        self._fields[field] = normalize_long_frame(data)

    def fields(self) -> tuple[str, ...]:
        return tuple(sorted(self._fields))
