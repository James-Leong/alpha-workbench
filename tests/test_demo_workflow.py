from alpha_workbench.core.config import settings
from alpha_workbench.schemas.specs import clone_default_idea_spec, clone_default_research_spec
from alpha_workbench.workflows.demo_workflow import run_demo_workflow, run_resume_workflow


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
