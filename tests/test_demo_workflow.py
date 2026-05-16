from alpha_workbench.workflows.demo_workflow import run_demo_workflow


def test_demo_workflow_returns_complete_trace():
    trace = run_demo_workflow()

    assert trace["idea_spec"]["idea_name"]
    assert len(trace["factor_specs"]) == 3
    assert len(trace["compiled_factors"]) == 3
    assert trace["backtest_result"]["factor_results"]
    assert trace["audit_report"]["checks"]
    assert trace["report_markdown"].startswith("# AlphaWorkbench Demo")
