from alpha_workbench.workflows.integration_workflow import build_integration_trace


def test_integration_trace_accepts_empty_role_outputs():
    trace = build_integration_trace(input_text="test idea")

    assert trace["workflow_mode"] == "role2_integration_shell"
    assert trace["workflow_framework"] in {"agno", "python_fallback"}
    assert "agno_available" in trace
    assert trace["idea_spec"] == {}
    assert trace["factor_specs"] == []
    assert trace["backtest_result"] == {}

    statuses = {step["output_key"]: step["status"] for step in trace["workflow_steps"]}
    assert statuses["input_text"] == "completed"
    assert statuses["idea_spec"] == "waiting"
    assert statuses["factor_specs"] == "waiting"


def test_integration_trace_accepts_role_outputs():
    trace = build_integration_trace(
        input_text="test idea",
        role_outputs={
            "idea_spec": {"idea_name": "demo"},
            "factor_specs": [{"factor_id": "demo_factor"}],
        },
    )

    statuses = {step["output_key"]: step["status"] for step in trace["workflow_steps"]}
    assert statuses["idea_spec"] == "completed"
    assert statuses["factor_specs"] == "completed"
    assert statuses["backtest_result"] == "waiting"
