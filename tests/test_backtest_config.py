from __future__ import annotations

from datetime import date

import pandas as pd

from alpha_workbench.backtest import engine as backtest_engine
from alpha_workbench.backtest.hybrid_engine import HybridBacktestEngine
from alpha_workbench.backtest.llm_explainer import BacktestExplainer
from alpha_workbench.backtest.mercury_adapter import MercuryBacktestResponse, MercurySummary
from alpha_workbench.app.status import backtest_source_summary, group_charts_by_factor
from alpha_workbench.app.research_config import apply_research_config_edits
from alpha_workbench.data.sample_data import generate_sample_data
from alpha_workbench.data.universe import resolve_universe
from alpha_workbench.schemas.backtest_schemas import (
    BacktestFigures,
    BacktestInput,
    BacktestMetrics,
    BacktestReport,
    FactorSpec,
    ICMetrics,
    LayerMetrics,
    LongShortMetrics,
    ResearchSpec,
)


def _factor_spec() -> FactorSpec:
    return FactorSpec(
        factor_id="TEST_FACTOR",
        factor_name="Test Factor",
        description="test",
    )


def _minimal_report(factor_spec: FactorSpec) -> BacktestReport:
    idx = pd.date_range("2024-01-01", periods=2, freq="B")
    cum_returns = pd.Series([1.0, 1.01], index=idx)
    metrics = BacktestMetrics(
        ic_metrics=ICMetrics(
            ic_mean=0.1,
            ic_std=0.01,
            icir=10.0,
            ic_positive_ratio=1.0,
            ic_tstat=2.0,
            rank_ic_mean=0.1,
            rank_ic_std=0.01,
            rank_icir=10.0,
            rank_ic_positive_ratio=1.0,
            rank_ic_tstat=2.0,
        ),
        layer_metrics=LayerMetrics(
            layer_returns={"L1": 0.01, "L2": 0.02},
            layer_cum_returns=pd.DataFrame({"L1": [1.0, 1.01], "L2": [1.0, 1.02]}, index=idx),
        ),
        long_short_metrics=LongShortMetrics(
            annual_return=0.2,
            annual_volatility=0.1,
            sharpe_ratio=2.0,
            max_drawdown=-0.03,
            cum_returns=cum_returns,
        ),
    )
    return BacktestReport(
        factor_id=factor_spec.factor_id,
        factor_name=factor_spec.factor_name,
        backtest_period="2024-01-01 ~ 2024-01-02",
        metrics=metrics,
        figures=BacktestFigures(),
    )


def test_generate_sample_data_honors_start_and_end_dates():
    factor_data, price_data, returns_data = generate_sample_data(
        n_stocks=12,
        start_date="2024-01-01",
        end_date="2024-01-31",
        seed=7,
    )

    assert factor_data.index.min().date() == date(2024, 1, 1)
    assert factor_data.index.max().date() <= date(2024, 1, 31)
    assert price_data.index.equals(factor_data.index)
    assert returns_data.index.equals(factor_data.index)


def test_resolve_universe_accepts_explicit_frontend_codes():
    assert resolve_universe("000001.XSHE, 600000.XSHG 000002.XSHE") == [
        "000001.XSHE",
        "600000.XSHG",
        "000002.XSHE",
    ]


def test_run_backtest_maps_research_spec_to_backtest_input(monkeypatch):
    captured_inputs: list[BacktestInput] = []

    class CapturingEngine:
        def __init__(self, **kwargs):
            self.use_mercury = kwargs.get("use_mercury", False)

        def run_backtest(self, input_data: BacktestInput) -> BacktestReport:
            captured_inputs.append(input_data)
            return _minimal_report(input_data.factor_spec)

        def close(self):
            return None

    monkeypatch.setattr(backtest_engine, "HybridBacktestEngine", CapturingEngine)

    result = backtest_engine.run_backtest(
        [{"factor_id": "TEST_FACTOR", "factor_name": "Test Factor"}],
        {
            "universe": "沪深300样例股票池",
            "rebalance_frequency": "monthly",
            "holding_period": "20D",
            "transaction_cost_bps": 15,
            "sample_window": {"start": "2024-01-01", "end": "2024-01-31"},
            "backtest": {"groups": 4},
        },
        enable_mercury=False,
    )

    assert result["factor_results"]
    assert len(captured_inputs) == 1
    input_data = captured_inputs[0]
    assert input_data.research_spec is not None
    assert input_data.research_spec.rebalance_frequency == "monthly"
    assert input_data.research_spec.holding_period == "20D"
    assert input_data.start_date == date(2024, 1, 1)
    assert input_data.end_date == date(2024, 1, 31)
    assert input_data.commission_rate == 0.0015
    assert input_data.n_quantiles == 4


def test_run_backtest_uses_frontend_universe_for_generated_data(monkeypatch):
    captured_inputs: list[BacktestInput] = []
    explicit_universe = ",".join(
        [
            "000001.XSHE",
            "600000.XSHG",
            "000002.XSHE",
            "600009.XSHG",
            "000063.XSHE",
            "600010.XSHG",
            "000100.XSHE",
            "600011.XSHG",
            "000157.XSHE",
            "600015.XSHG",
            "000166.XSHE",
            "600016.XSHG",
        ]
    )

    class CapturingEngine:
        def __init__(self, **kwargs):
            self.use_mercury = kwargs.get("use_mercury", False)

        def run_backtest(self, input_data: BacktestInput) -> BacktestReport:
            captured_inputs.append(input_data)
            return _minimal_report(input_data.factor_spec)

        def close(self):
            return None

    monkeypatch.setattr(backtest_engine, "HybridBacktestEngine", CapturingEngine)

    backtest_engine.run_backtest(
        [{"factor_id": "TEST_FACTOR", "factor_name": "Test Factor"}],
        {
            "universe": explicit_universe,
            "sample_window": {"start": "2024-01-01", "end": "2024-02-29"},
        },
        enable_mercury=False,
    )

    assert list(captured_inputs[0].factor_data.columns) == explicit_universe.split(",")


def test_generated_factor_ids_align_with_chart_keys_and_shared_returns():
    factors = [
        {"factor_id": "earnings_surprise_adj_001", "factor_name": "行业中性盈利超预期"},
        {"factor_id": "quality_surprise_combo_003", "factor_name": "质量增强盈利超预期"},
    ]

    result = backtest_engine.run_backtest(
        factors,
        {
            "universe": "sample_universe",
            "sample_window": {"start": "2024-01-01", "end": "2024-06-30"},
            "backtest": {"groups": 5},
        },
        enable_mercury=False,
    )

    by_id = {item["factor_id"]: item for item in result["factor_results"]}
    assert set(by_id) == {factor["factor_id"] for factor in factors}
    assert abs(by_id["quality_surprise_combo_003"]["ic_mean"]) > 0.01

    chart_groups = group_charts_by_factor(result["charts"], result["factor_results"])
    quality_group = next(
        group for group in chart_groups if group["factor_id"] == "quality_surprise_combo_003"
    )
    assert {chart["label"] for chart in quality_group["charts"]} == {
        "IC 序列",
        "分层累计收益",
        "多空净值",
    }


def test_llm_parser_accepts_frontend_ic_analysis_heading():
    raw = """
### 总体评价
整体表现一般。

### IC分析
IC均值接近0，预测能力不足。

### 风险评估
回撤较大。

### 改进建议
建议补充真实因子数据。
"""

    result = BacktestExplainer(force_mock=True)._parse_explanation_to_structured(raw)

    assert result.ic_analysis == "IC均值接近0，预测能力不足。"


def test_llm_parser_keeps_inline_ic_analysis_content():
    raw = """
1. 总体评价：整体表现一般。
2. IC分析：IC均值为0.0000，Rank IC为0.0000，预测能力不足。
3. 风险评估：最大回撤较大。
4. 改进建议：建议补充真实因子数据。
"""

    result = BacktestExplainer(force_mock=True)._parse_explanation_to_structured(raw)

    assert result.ic_analysis == "IC均值为0.0000，Rank IC为0.0000，预测能力不足。"


def test_run_backtest_uses_mercury_for_each_factor_before_local_fallback(monkeypatch):
    calls: list[tuple[bool, str]] = []

    class RoutingEngine:
        def __init__(self, **kwargs):
            self.use_mercury = kwargs.get("use_mercury", False)

        def run_backtest(self, input_data: BacktestInput) -> BacktestReport:
            calls.append((self.use_mercury, input_data.factor_spec.factor_id))
            if self.use_mercury and input_data.factor_spec.factor_id == "FACTOR_B":
                raise RuntimeError("Mercury unavailable")
            report = _minimal_report(input_data.factor_spec)
            if self.use_mercury:
                report.raw_data = {
                    "mercury_response": {
                        "summary": {
                            "sharpe": report.metrics.long_short_metrics.sharpe_ratio,
                            "total_return": report.metrics.long_short_metrics.annual_return,
                        },
                        "job_id": f"job-{input_data.factor_spec.factor_id}",
                        "status": "completed",
                    }
                }
            return report

        def close(self):
            return None

    monkeypatch.setattr(backtest_engine, "HybridBacktestEngine", RoutingEngine)

    result = backtest_engine.run_backtest(
        [
            {"factor_id": "FACTOR_A", "factor_name": "Factor A"},
            {"factor_id": "FACTOR_B", "factor_name": "Factor B"},
        ],
        {"sample_window": {"start": "2024-01-01", "end": "2024-02-29"}},
        enable_mercury=True,
    )

    assert calls == [
        (True, "FACTOR_A"),
        (True, "FACTOR_B"),
        (False, "FACTOR_B"),
    ]
    engines = {item["factor_id"]: item["engine"] for item in result["factor_results"]}
    assert engines == {"FACTOR_A": "mercury", "FACTOR_B": "local_fallback"}


def test_run_backtest_is_not_mock_when_mercury_produces_results(monkeypatch):
    class MercuryEngine:
        def __init__(self, **kwargs):
            self.use_mercury = kwargs.get("use_mercury", False)

        def run_backtest(self, input_data: BacktestInput) -> BacktestReport:
            report = _minimal_report(input_data.factor_spec)
            report.raw_data = {
                "mercury_response": {
                    "summary": {
                        "sharpe": 1.2,
                        "total_return": 0.1,
                        "annualized_return": 0.2,
                        "annualized_volatility": 0.1,
                        "max_drawdown": -0.03,
                    },
                    "job_id": "job-1",
                    "status": "completed",
                }
            }
            return report

        def close(self):
            return None

    monkeypatch.setattr(backtest_engine, "HybridBacktestEngine", MercuryEngine)

    result = backtest_engine.run_backtest(
        [{"factor_id": "TEST_FACTOR", "factor_name": "Test Factor"}],
        {"sample_window": {"start": "2024-01-01", "end": "2024-02-29"}},
        enable_mercury=True,
    )

    assert result["mercury_results"]
    assert result["is_mock"] is False
    assert result["uses_synthetic_factor_data"] is True


def test_mercury_backtest_uses_research_config_and_factor_ranked_assets():
    factor_data = pd.DataFrame(
        [[0.1, 0.9, 0.3, 0.8, 0.2]],
        index=pd.to_datetime(["2024-01-15"]),
        columns=["A.XSHE", "B.XSHE", "C.XSHE", "D.XSHE", "E.XSHE"],
    )
    input_data = BacktestInput(
        factor_spec=_factor_spec(),
        factor_data=factor_data,
        price_data=pd.DataFrame(10.0, index=factor_data.index, columns=factor_data.columns),
        research_spec=ResearchSpec.from_dict(
            {
                "rebalance_frequency": "monthly",
                "transaction_cost_bps": 15,
                "initial_cash": 2500000,
                "sample_window": {"start": "2024-01-01", "end": "2024-01-31"},
            }
        ),
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31),
        commission_rate=0.0015,
    )

    class MercuryStub:
        def __init__(self):
            self.run_spec = None

        def create_and_wait(self, run_spec):
            self.run_spec = run_spec
            return None

    mercury = MercuryStub()
    hybrid = HybridBacktestEngine(use_mercury=False)
    hybrid.mercury = mercury

    assert hybrid._run_mercury_backtest(input_data, factor_data) is None

    run_spec = mercury.run_spec
    assert run_spec.run.start_date == "20240101"
    assert run_spec.run.end_date == "20240131"
    assert run_spec.run.initial_cash == 2500000
    assert run_spec.run.transaction_cost_bps == 15
    ops = run_spec.inputs[0]["ops"]
    assert {"op": "schedule", "schedule": "monthly"} in ops
    assert ops[0]["assets"] == ["B.XSHE", "D.XSHE", "C.XSHE", "E.XSHE", "A.XSHE"]


def test_mercury_schedule_falls_back_to_holding_period_when_frequency_missing():
    assert HybridBacktestEngine._resolve_rebalance_schedule(None, "20D") == "weekly"
    assert HybridBacktestEngine._resolve_rebalance_schedule("", "1M") == "monthly"
    assert HybridBacktestEngine._resolve_rebalance_schedule("weekly", "1M") == "weekly"
    assert HybridBacktestEngine._resolve_rebalance_schedule("quarterly", "20D") == "quarterly"
    assert HybridBacktestEngine._resolve_rebalance_schedule("once", "20D") == "once"
    assert HybridBacktestEngine._resolve_rebalance_schedule("", "1Q") == "quarterly"


def test_hybrid_engine_preserves_factor_analytics_when_mercury_succeeds():
    dates = pd.date_range("2024-01-01", periods=12, freq="B")
    columns = [f"{i:06d}.XSHE" for i in range(12)]
    price_data = pd.DataFrame(
        [[10 + day + col for col in range(12)] for day in range(12)],
        index=dates,
        columns=columns,
    )
    returns_data = price_data.pct_change().shift(-1)
    factor_data = returns_data.shift(0).fillna(0)
    input_data = BacktestInput(
        factor_spec=_factor_spec(),
        factor_data=factor_data,
        price_data=price_data,
        returns_data=returns_data,
        n_quantiles=3,
    )

    class MercuryStub:
        def create_and_wait(self, run_spec):
            return MercuryBacktestResponse(
                job_id="job-1",
                status="completed",
                summary=MercurySummary(
                    start_date="20240101",
                    end_date="20240116",
                    total_return=0.12,
                    annualized_return=0.2,
                    annualized_volatility=0.1,
                    sharpe=2.0,
                    max_drawdown=-0.03,
                ),
            )

    hybrid = HybridBacktestEngine(enable_plotting=False, enable_llm_explanation=False, use_mercury=False)
    hybrid.use_mercury = True
    hybrid.mercury = MercuryStub()

    report = hybrid.run_backtest(input_data)

    assert report.raw_data["engine"] == "mercury"
    assert report.metrics.ic_metrics.rank_ic_mean != 0.0
    assert report.metrics.layer_metrics.layer_returns
    assert report.metrics.long_short_metrics.sharpe_ratio == 2.0


def test_backtest_source_summary_prefers_factor_engine_status():
    summary = backtest_source_summary(
        {
            "factor_results": [
                {"factor_id": "A", "engine": "mercury"},
                {"factor_id": "B", "engine": "local_fallback"},
            ],
            "is_mock": True,
        }
    )

    assert summary["label"] == "Mercury + 本地 fallback"
    assert "交易级回测" in summary["chips"]
    assert "本地 fallback" in summary["chips"]
    assert "Mock 数据" in summary["chips"]


def test_backtest_source_summary_distinguishes_synthetic_factor_signals():
    summary = backtest_source_summary(
        {
            "factor_results": [{"factor_id": "A", "engine": "mercury"}],
            "is_mock": False,
            "uses_synthetic_factor_data": True,
        }
    )

    assert summary["label"] == "Mercury 交易级回测"
    assert "交易级回测" in summary["chips"]
    assert "合成因子信号" in summary["chips"]
    assert "Mock 数据" not in summary["chips"]


def test_group_charts_by_factor_uses_factor_names_and_chart_labels():
    grouped = group_charts_by_factor(
        {
            "FACTOR_A_ic_series": "ic-a",
            "FACTOR_A_layer_cumreturns": "layer-a",
            "FACTOR_B_long_short_nav": "nav-b",
        },
        [
            {"factor_id": "FACTOR_A", "factor_name": "因子A", "engine": "local_fallback"},
            {"factor_id": "FACTOR_B", "factor_name": "因子B", "engine": "mercury"},
        ],
    )

    assert grouped[0]["factor_name"] == "因子A"
    assert [(item["label"], item["figure"]) for item in grouped[0]["charts"]] == [
        ("IC 序列", "ic-a"),
        ("分层累计收益", "layer-a"),
    ]
    assert grouped[1]["factor_name"] == "因子B"
    assert grouped[1]["charts"][0]["label"] == "多空净值"


def test_apply_research_config_edits_persists_frontend_sample_window():
    updated = apply_research_config_edits(
        {"sample_window": {"start": "2021-01-01", "end": "2021-12-31"}},
        universe="000001.XSHE,600000.XSHG",
        holding_period="10D",
        benchmark="中证500",
        rebalance_frequency="Weekly",
        transaction_cost_bps=8,
        initial_cash=3000000,
        sample_start="2024-01-02",
        sample_end="2024-03-29",
    )

    assert updated["universe"] == "000001.XSHE,600000.XSHG"
    assert updated["holding_period"] == "10D"
    assert updated["rebalance_frequency"] == "weekly"
    assert updated["transaction_cost_bps"] == 8
    assert updated["initial_cash"] == 3000000
    assert updated["sample_window"] == {"start": "2024-01-02", "end": "2024-03-29"}
    assert updated["backtest"]["rebalance_frequency"] == "weekly"
    assert updated["backtest"]["initial_cash"] == 3000000
