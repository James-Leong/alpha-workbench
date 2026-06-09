"""Universe parsing helpers for demo and Mercury backtests."""

from __future__ import annotations

import re

from alpha_workbench.data.sample_data import DEFAULT_SAMPLE_SECURITIES


UNIVERSE_ALIASES: dict[str, list[str]] = {
    "sample_universe": DEFAULT_SAMPLE_SECURITIES[:50],
    "样例股票池": DEFAULT_SAMPLE_SECURITIES[:50],
    "沪深300样例股票池": DEFAULT_SAMPLE_SECURITIES[:50],
    "沪深300": DEFAULT_SAMPLE_SECURITIES[:50],
    "csi300": DEFAULT_SAMPLE_SECURITIES[:50],
    "hs300": DEFAULT_SAMPLE_SECURITIES[:50],
    "中证500样例股票池": DEFAULT_SAMPLE_SECURITIES[30:80],
    "中证500": DEFAULT_SAMPLE_SECURITIES[30:80],
    "csi500": DEFAULT_SAMPLE_SECURITIES[30:80],
}


def resolve_universe(universe: str | None, *, default_size: int = 50) -> list[str]:
    """Resolve a UI universe value to Mercury-compatible security codes.

    The frontend can pass either a known alias such as ``sample_universe`` or a
    comma/space separated list such as ``000001.XSHE, 600000.XSHG``.
    """
    if not universe:
        return DEFAULT_SAMPLE_SECURITIES[:default_size]

    value = universe.strip()
    key = value.lower()
    for alias, securities in UNIVERSE_ALIASES.items():
        if key == alias.lower():
            return securities.copy()

    tokens = [token.strip() for token in re.split(r"[,，\s]+", value) if token.strip()]
    explicit = [token.upper() for token in tokens if _looks_like_security_code(token)]
    if explicit:
        return explicit

    return DEFAULT_SAMPLE_SECURITIES[:default_size]


def _looks_like_security_code(value: str) -> bool:
    return bool(re.fullmatch(r"\d{6}\.(XSHE|XSHG|SZ|SH)", value.upper()))
