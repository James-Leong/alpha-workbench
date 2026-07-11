import json

from pydantic import BaseModel

from alpha_workbench.core.config import settings
from alpha_workbench.data_sdk import make_earnings_surprise_pit_fixture
from alpha_workbench.memory.research_trace import _safe_json_default
from alpha_workbench.workflows import demo_workflow
from alpha_workbench.schemas.specs import clone_default_idea_spec, clone_default_research_spec
from alpha_workbench.workflows.demo_workflow import run_demo_workflow, run_resume_workflow
from alpha_workbench.workflows.factor_plugin_workflow import FactorPluginPipelineResult


def _wide(frame):
    result = frame.pivot(index="trade_date", columns="symbol", values="value")
    result.index.name = None
    result.columns.name = None
    return result


def test_trace_json_default_serializes_pydantic_models():
    class TraceModel(BaseModel):
        name: str

    payload = json.loads(json.dumps({"idea": TraceModel(name="test")}, default=_safe_json_default))

    assert payload == {"idea": {"name": "test"}}


def test_demo_workflow_returns_complete_trace(monkeypatch):
    # 测试使用 mock 模式，避免每次运行都调用真实 LLM（慢且不稳定）
    monkeypatch.setattr(settings, "llm_api_key", "")

    trace = run_demo_workflow()

    assert trace["idea_spec"]["idea_name"]
    assert len(trace["factor_specs"]) >= 3
    assert len(trace["compiled_factors"]) >= 3
    assert trace["backtest_result"]["factor_results"]
    assert trace["audit_report"]["checks"]
    assert trace["report_markdown"].strip()


def test_run_resume_workflow_uses_provided_research_spec(monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "")

    idea_spec = clone_default_idea_spec()
    idea_spec["idea_name"] = "test resume workflow"
    research_spec = clone_default_research_spec()
    research_spec["universe"] = "自定义股票池"

    trace = run_resume_workflow(
        input_text="test input",
        idea_spec=idea_spec,
        research_spec=research_spec,
    )

    assert trace["idea_spec"]["idea_name"] == "test resume workflow"
    assert trace["research_spec"]["universe"] == "自定义股票池"
    assert len(trace["factor_specs"]) >= 3
    assert len(trace["compiled_factors"]) >= 3
    assert trace["backtest_result"]["factor_results"]
    assert trace["audit_report"]["checks"]
    assert trace["report_markdown"].strip()


def test_run_resume_workflow_codex_mode_passes_computed_factor_data(monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "")
    fixture = make_earnings_surprise_pit_fixture()
    price = _wide(fixture["price"]).astype(float)
    actual = _wide(fixture["quarter_net_profit"]).astype(float)
    expected = _wide(fixture["expected_net_profit"]).astype(float)
    factor_data = (actual - expected) / (expected.abs() + 1.0)
    returns = price.pct_change().shift(-1)
    factor_id = "earnings_surprise_adj_001"
    pipeline_result = FactorPluginPipelineResult(
        factor_specs=[{"factor_id": factor_id, "factor_name": "Codex Factor"}],
        factor_data_dict={factor_id: factor_data},
        price_data=price,
        returns_data=returns,
        trace_artifacts={
            "factor_implementation_mode": "python_plugin",
            "code_agent": {"provider": "codex_exec", "version": "test", "is_mock": False},
            "data_provider": "deterministic_pit_fixture",
            "pipeline_status": "passed",
            "pipeline_errors": [],
        },
    )
    monkeypatch.setattr(
        demo_workflow,
        "run_factor_plugin_pipeline",
        lambda *args, **kwargs: pipeline_result,
    )
    original_run_backtest = demo_workflow.run_backtest
    captured: dict = {}

    def capture_backtest(factor_specs, research_spec, **kwargs):
        captured.update(kwargs)
        return original_run_backtest(
            factor_specs,
            research_spec,
            enable_mercury=False,
            **kwargs,
        )

    monkeypatch.setattr(demo_workflow, "run_backtest", capture_backtest)
    research_spec = clone_default_research_spec()
    research_spec["factor_execution"] = {
        "mode": "codex",
        "code_agent": "codex",
        "fallback_to_expression": False,
    }
    research_spec["sample_window"] = {"start": "2024-01-02", "end": "2024-05-31"}

    trace = run_resume_workflow(
        input_text="earnings surprise",
        idea_spec=clone_default_idea_spec(),
        research_spec=research_spec,
    )

    assert captured["require_factor_data"] is True
    assert captured["factor_data_dict"][factor_id].equals(factor_data)
    assert trace["factor_implementation_mode"] == "python_plugin"
    assert trace["pipeline_status"] == "passed"
    assert trace["uses_synthetic_factor_data"] is False
    assert trace["uses_mock_market_data"] is True
