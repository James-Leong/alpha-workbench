from role3.idea_extractor import extract_idea
from role3.validators import REQUIRED_IDEA_FIELDS


def test_extract_idea_without_credentials_returns_mock_envelope():
    result = extract_idea("单季度净利润超预期，且公告前股价没有明显上涨。")

    assert set(result) == {
        "idea_spec",
        "is_mock",
        "is_fallback",
        "source_meta",
        "raw_model_response",
        "missing_fields",
    }
    assert result["is_mock"] is True
    assert result["is_fallback"] is False
    assert result["raw_model_response"] is None


def test_mock_idea_spec_contains_required_fields():
    result = extract_idea("盈利超预期")

    for field in REQUIRED_IDEA_FIELDS:
        assert field in result["idea_spec"]
