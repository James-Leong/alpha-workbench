from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import pytest

from alpha_workbench.data_sdk import (
    DataService,
    InMemoryProvider,
    SQLiteStore,
    UqerProvider,
    UqerUnavailableError,
    make_earnings_surprise_pit_fixture,
)
from alpha_workbench.data_sdk.providers import uqer_provider as uqer_provider_module
from alpha_workbench.data_sdk.base import normalize_long_frame


def _long_frame(values: list[tuple[str, str, float]]) -> pd.DataFrame:
    return pd.DataFrame(values, columns=["trade_date", "symbol", "value"])


def test_sqlite_store_round_trip_and_filters(tmp_path):
    prices = _long_frame(
        [
            ("2024-01-02", "000001.XSHE", 10.0),
            ("2024-01-02", "000002.XSHE", 20.0),
            ("2024-01-03", "000001.XSHE", 10.5),
            ("2024-01-03", "000002.XSHE", 19.5),
            ("2024-01-04", "000001.XSHE", 11.0),
            ("2024-01-04", "000002.XSHE", 21.0),
        ]
    )
    daily_returns = prices.assign(value=[0.0, 0.0, 0.05, -0.025, 0.0476, 0.0769])

    with SQLiteStore(tmp_path / "sdk.sqlite3") as store:
        store.save("price", prices)
        store.save("returns", daily_returns)

        loaded = store.load("price")
        expected = prices.assign(trade_date=pd.to_datetime(prices["trade_date"]))
        pd.testing.assert_frame_equal(loaded, expected)
        assert store.fields() == ("price", "returns")

        filtered = store.load(
            "price",
            start_date="2024-01-03",
            end_date="2024-01-04",
            symbols=["000002.XSHE"],
        )
        assert filtered.to_dict("records") == [
            {
                "trade_date": pd.Timestamp("2024-01-03"),
                "symbol": "000002.XSHE",
                "value": 19.5,
            },
            {
                "trade_date": pd.Timestamp("2024-01-04"),
                "symbol": "000002.XSHE",
                "value": 21.0,
            },
        ]

        store.save("price", _long_frame([("2024-01-04", "000002.XSHE", 22.0)]))
        assert store.load("price", start_date="2024-01-04").iloc[-1]["value"] == 22.0
        assert store.load("returns")["value"].tolist() == daily_returns["value"].tolist()


def test_sqlite_store_preserves_datetime_field_values(tmp_path):
    announcements = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
            "symbol": ["000001.XSHE", "000001.XSHE"],
            "value": pd.to_datetime([None, "2024-01-02"]),
        }
    )

    with SQLiteStore(tmp_path / "sdk.sqlite3") as store:
        store.save("announce_date", announcements)
        loaded = store.load("announce_date")

    pd.testing.assert_frame_equal(loaded, announcements)


def test_sqlite_store_serializes_concurrent_access(tmp_path):
    with SQLiteStore(tmp_path / "sdk.sqlite3") as store:
        def save_and_load(index: int) -> float:
            trade_date = pd.Timestamp("2024-01-02") + pd.Timedelta(days=index)
            store.save(
                "price",
                _long_frame([(trade_date.isoformat(), f"S{index:02d}", float(index))]),
            )
            loaded = store.load("price", symbols=[f"S{index:02d}"])
            return float(loaded.iloc[0]["value"])

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(save_and_load, range(20)))

    assert results == [float(index) for index in range(20)]


def test_normalize_long_frame_rejects_timezone_aware_trade_dates():
    frame = _long_frame([("2024-01-02T00:00:00+08:00", "000001.XSHE", 10.0)])

    with pytest.raises(ValueError, match="timezone-naive"):
        normalize_long_frame(frame)


def test_data_service_uses_provider_protocol_for_load_and_save(tmp_path):
    source_data = _long_frame(
        [
            ("2024-01-02", "000001.XSHE", 10.0),
            ("2024-01-03", "000001.XSHE", 10.5),
        ]
    )
    class CountingProvider(InMemoryProvider):
        def __init__(self, fields):
            super().__init__(fields)
            self.calls = 0

        def load(self, field, **kwargs):
            self.calls += 1
            return super().load(field, **kwargs)

    provider = CountingProvider({"price": source_data})

    with SQLiteStore(tmp_path / "cache.sqlite3") as store:
        service = DataService(provider, store=store)
        loaded = service.load("price", start_date="2024-01-03")
        assert loaded["value"].tolist() == [10.5]
        assert store.load("price")["value"].tolist() == [10.5]
        cached = service.load("price", start_date="2024-01-03")
        assert cached["value"].tolist() == [10.5]
        assert provider.calls == 1

        broader = service.load("price", start_date="2024-01-02")
        assert broader["value"].tolist() == [10.0, 10.5]
        assert provider.calls == 2

        service.save("factor", source_data.assign(value=[1.0, 2.0]))
        assert store.load("factor")["value"].tolist() == [1.0, 2.0]


def test_data_service_refresh_replaces_cached_scope(tmp_path):
    original = _long_frame(
        [
            ("2024-01-02", "000001.XSHE", 10.0),
            ("2024-01-03", "000001.XSHE", 10.5),
        ]
    )
    provider = InMemoryProvider({"price": original})
    with SQLiteStore(tmp_path / "cache.sqlite3") as store:
        service = DataService(provider, store=store)
        assert len(service.load("price")) == 2
        provider.save("price", original.iloc[:1])

        refreshed = service.load("price", refresh=True)
        cached = service.load("price")

    assert len(refreshed) == 1
    pd.testing.assert_frame_equal(cached, refreshed)


def test_uqer_provider_import_is_lazy_and_missing_sdk_error_is_clear(monkeypatch):
    import_attempts: list[str] = []

    def missing_uqer(name: str):
        import_attempts.append(name)
        raise ModuleNotFoundError("No module named 'uqer'", name="uqer")

    monkeypatch.setattr(uqer_provider_module.importlib, "import_module", missing_uqer)
    provider = UqerProvider()
    assert import_attempts == []

    with pytest.raises(UqerUnavailableError, match="optional 'uqer' package"):
        provider.load("price")
    assert import_attempts == ["uqer"]


def test_earnings_surprise_fixture_applies_events_on_next_trading_day():
    fixture = make_earnings_surprise_pit_fixture()

    assert set(fixture) == {
        "price",
        "returns",
        "quarter_net_profit",
        "expected_net_profit",
        "announce_date",
    }
    price = fixture["price"].pivot(index="trade_date", columns="symbol", values="value")
    returns = fixture["returns"].pivot(index="trade_date", columns="symbol", values="value")
    actual = fixture["quarter_net_profit"].pivot(
        index="trade_date", columns="symbol", values="value"
    )
    expected = fixture["expected_net_profit"].pivot(
        index="trade_date", columns="symbol", values="value"
    )
    announced = fixture["announce_date"].pivot(
        index="trade_date", columns="symbol", values="value"
    )

    assert price.shape == (80, 20)
    assert len(price.index) == 80
    pd.testing.assert_frame_equal(returns.iloc[1:], price.pct_change().iloc[1:])
    assert returns.iloc[0].eq(0.0).all()

    for symbol in price.columns:
        visible_announcements = announced[symbol].dropna()
        transitions = visible_announcements.loc[
            visible_announcements.ne(visible_announcements.shift())
        ]
        assert len(transitions) == 2

        for effective_date, raw_announcement in transitions.items():
            announcement = pd.Timestamp(raw_announcement)
            next_trade_index = price.index.searchsorted(announcement, side="right")
            assert effective_date == price.index[next_trade_index]

            announcement_day_value = announced.loc[announcement, symbol]
            assert pd.isna(announcement_day_value) or pd.Timestamp(announcement_day_value) < announcement
            assert pd.notna(actual.loc[effective_date, symbol])
            assert pd.notna(expected.loc[effective_date, symbol])

        first_announcement = pd.Timestamp(transitions.iloc[0])
        assert actual.loc[:first_announcement, symbol].isna().all()
        assert expected.loc[:first_announcement, symbol].isna().all()
