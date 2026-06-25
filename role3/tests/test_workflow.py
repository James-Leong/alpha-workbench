from role3.workflow import run_role3_workflow


def test_run_role3_workflow_returns_expected_shape():
    result = run_role3_workflow("单季度净利润超预期")

    assert result["workflow_mode"] == "role3_idea_extraction"
    assert "idea_result" in result
    assert result["workflow_meta"]["scope"] == "role3_only"
