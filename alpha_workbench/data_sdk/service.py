"""Business-facing data service independent of concrete data vendors."""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from alpha_workbench.data_sdk.base import DataProvider, normalize_long_frame


class DataService:
    """Provide one load/save API over a provider and an optional local store."""

    def __init__(
        self,
        provider: DataProvider | None = None,
        *,
        store: DataProvider | None = None,
    ) -> None:
        if provider is None and store is None:
            raise ValueError("DataService requires a provider or store")
        self.provider = provider
        self.store = store

    def load(
        self,
        field: str,
        *,
        start_date: str | pd.Timestamp | None = None,
        end_date: str | pd.Timestamp | None = None,
        symbols: Sequence[str] | None = None,
        refresh: bool = False,
    ) -> pd.DataFrame:
        query = {
            "start_date": start_date,
            "end_date": end_date,
            "symbols": symbols,
        }
        if self.store is not None and not refresh:
            if self.provider is None:
                return normalize_long_frame(self.store.load(field, **query))
            has_snapshot = getattr(self.store, "has_snapshot", None)
            if callable(has_snapshot) and has_snapshot(field, **query):
                return normalize_long_frame(self.store.load(field, **query))

        if self.provider is None:
            return self.store.load(field, **query)  # type: ignore[union-attr]

        data = normalize_long_frame(self.provider.load(field, **query))
        if self.store is not None:
            replace_scope = getattr(self.store, "replace_scope", None)
            if callable(replace_scope):
                replace_scope(field, data, **query)
            else:
                if not data.empty:
                    self.store.save(field, data)
                record_snapshot = getattr(self.store, "record_snapshot", None)
                if callable(record_snapshot):
                    record_snapshot(field, **query, row_count=len(data))
        return data

    def save(self, field: str, data: pd.DataFrame) -> None:
        target = self.store or self.provider
        if target is None:
            raise RuntimeError("DataService has no writable target")
        target.save(field, normalize_long_frame(data))
