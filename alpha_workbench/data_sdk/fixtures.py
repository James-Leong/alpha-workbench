"""Deterministic point-in-time fixtures for factor development."""

from __future__ import annotations

import math

import pandas as pd

from alpha_workbench.data_sdk.base import normalize_long_frame


def _wide_to_long(data: pd.DataFrame) -> pd.DataFrame:
    frame = data.rename_axis(index="trade_date", columns="symbol").reset_index()
    return normalize_long_frame(
        frame.melt(id_vars="trade_date", var_name="symbol", value_name="value")
    )


def make_earnings_surprise_pit_fixture(
    *,
    n_stocks: int = 20,
    n_days: int = 80,
    start_date: str = "2024-01-02",
) -> dict[str, pd.DataFrame]:
    """Build daily price and earnings data with strict PIT availability.

    Each company has two announcements. ``announce_date`` and both earnings
    values become visible together on the first trading day strictly after the
    announcement, then remain visible until the next announcement takes effect.
    Price returns follow a separate deterministic formula and are never used to
    construct an earnings field.
    """
    if n_stocks < 20:
        raise ValueError("the earnings surprise PIT fixture requires at least 20 stocks")
    if n_days < 70:
        raise ValueError("the earnings surprise PIT fixture requires at least 70 trade days")

    trade_dates = pd.bdate_range(start_date, periods=n_days)
    symbols = tuple(f"{index + 1:06d}.XSHE" for index in range(n_stocks))

    price = pd.DataFrame(index=trade_dates, columns=symbols, dtype=float)
    returns = pd.DataFrame(index=trade_dates, columns=symbols, dtype=float)
    for symbol_index, symbol in enumerate(symbols):
        path = [50.0 + symbol_index * 1.75]
        return_path = [0.0]
        for day_index in range(1, n_days):
            daily_return = (
                0.0003
                + 0.0001 * ((symbol_index % 5) - 2)
                + 0.003 * math.sin((day_index + 1) * (symbol_index + 2) * 0.17)
            )
            return_path.append(daily_return)
            path.append(path[-1] * (1.0 + daily_return))
        price[symbol] = path
        returns[symbol] = return_path

    quarter_net_profit = pd.DataFrame(index=trade_dates, columns=symbols, dtype=float)
    expected_net_profit = pd.DataFrame(index=trade_dates, columns=symbols, dtype=float)
    announce_date = pd.DataFrame(index=trade_dates, columns=symbols, dtype="datetime64[ns]")

    for symbol_index, symbol in enumerate(symbols):
        announcement_indexes = (18 + symbol_index % 5, 49 + symbol_index % 7)
        for report_number, announcement_index in enumerate(announcement_indexes):
            announcement = trade_dates[announcement_index]
            effective_index = trade_dates.searchsorted(announcement, side="right")
            if effective_index >= len(trade_dates):
                continue

            expected = 80.0 + symbol_index * 2.5 + report_number * 8.0
            surprise_rate = ((symbol_index + report_number * 3) % 9 - 4) * 0.035
            actual = expected * (1.0 + surprise_rate)
            effective_date = trade_dates[effective_index]

            quarter_net_profit.loc[effective_date:, symbol] = actual
            expected_net_profit.loc[effective_date:, symbol] = expected
            announce_date.loc[effective_date:, symbol] = announcement

    return {
        "price": _wide_to_long(price),
        "returns": _wide_to_long(returns),
        "quarter_net_profit": _wide_to_long(quarter_net_profit),
        "expected_net_profit": _wide_to_long(expected_net_profit),
        "announce_date": _wide_to_long(announce_date),
    }


generate_earnings_surprise_pit_fixture = make_earnings_surprise_pit_fixture
