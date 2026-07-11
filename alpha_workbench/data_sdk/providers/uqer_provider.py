"""Optional UQER-backed provider with no import-time UQER dependency."""

from __future__ import annotations

import importlib
from collections.abc import Callable, Sequence
from typing import Any

import pandas as pd

from alpha_workbench.data_sdk.base import filter_long_frame, normalize_long_frame


class UqerUnavailableError(RuntimeError):
    """Raised when UQER data is requested without the optional SDK installed."""


class UqerProvider:
    """Adapt a UQER loader to the project-level provider protocol.

    ``loader`` is useful for integration tests and for adapting account-specific
    UQER queries. The default loader resolves ``uqer`` only when ``load`` is called.
    """

    name = "uqer"

    def __init__(
        self,
        token: str | None = None,
        *,
        loader: Callable[..., pd.DataFrame] | None = None,
    ) -> None:
        self._token = token
        self._loader = loader

    @staticmethod
    def _import_uqer() -> Any:
        try:
            return importlib.import_module("uqer")
        except ModuleNotFoundError as exc:
            if exc.name != "uqer":
                raise
            raise UqerUnavailableError(
                "UqerProvider requires the optional 'uqer' package. "
                "Install and configure the UQER SDK before requesting remote data."
            ) from exc

    def _default_loader(
        self,
        *,
        field: str,
        start_date: str | pd.Timestamp | None,
        end_date: str | pd.Timestamp | None,
        symbols: Sequence[str] | None,
    ) -> pd.DataFrame:
        uqer = self._import_uqer()
        if self._token:
            uqer.Client(token=self._token)

        raise NotImplementedError(
            "No generic UQER endpoint is safe for every standard field. "
            "Configure UqerProvider(loader=...) with the project's field mapping."
        )

    def load(
        self,
        field: str,
        *,
        start_date: str | pd.Timestamp | None = None,
        end_date: str | pd.Timestamp | None = None,
        symbols: Sequence[str] | None = None,
    ) -> pd.DataFrame:
        loader = self._loader or self._default_loader
        data = loader(
            field=field,
            start_date=start_date,
            end_date=end_date,
            symbols=symbols,
        )
        return filter_long_frame(
            normalize_long_frame(data),
            start_date=start_date,
            end_date=end_date,
            symbols=symbols,
        )

    def save(self, field: str, data: pd.DataFrame) -> None:
        raise PermissionError("UqerProvider is read-only; save data through a local store")
