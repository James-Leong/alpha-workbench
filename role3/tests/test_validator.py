from role3.validators import REQUIRED_IDEA_FIELDS, validate_idea_spec


def test_validate_idea_spec_fills_missing_fields():
    idea_spec, missing = validate_idea_spec({"idea_name": "测试想法"})

    for field in REQUIRED_IDEA_FIELDS:
        assert field in idea_spec
    assert "core_hypothesis" in missing
    assert "suggested_research_spec" in missing


def test_validate_idea_spec_wraps_string_list_fields():
    idea_spec, _ = validate_idea_spec(
        {
            "economic_mechanism": "盈利公告带来信息冲击",
            "risk_flags": "公告日未来函数风险",
        }
    )

    assert idea_spec["economic_mechanism"] == ["盈利公告带来信息冲击"]
    assert idea_spec["risk_flags"] == ["公告日未来函数风险"]
