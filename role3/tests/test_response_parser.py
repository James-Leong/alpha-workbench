from unittest.mock import patch

from role3.idea_extractor import extract_idea, parse_model_response


def test_parse_json_string_response():
    parsed = parse_model_response(
        '{"idea_spec": {"idea_id": "x", "idea_name": "测试", "core_hypothesis": "可能有效"}}'
    )

    assert parsed["idea_spec"]["idea_id"] == "x"


def test_parse_markdown_code_fence_response():
    parsed = parse_model_response(
        '```json\n{"idea_spec": {"idea_id": "fenced", "idea_name": "测试"}}\n```'
    )

    assert parsed["idea_spec"]["idea_id"] == "fenced"


def test_extract_idea_parses_model_json_string():
    raw = '{"idea_spec": {"idea_id": "model_id", "idea_name": "模型想法", "economic_mechanism": "机制"}}'
    with patch("role3.idea_extractor.call_huawei_model", return_value=raw):
        result = extract_idea("盈利超预期", api_url="https://example.test", token="token")

    assert result["is_mock"] is False
    assert result["idea_spec"]["idea_id"] == "model_id"
    assert result["idea_spec"]["economic_mechanism"] == ["机制"]


def test_extract_idea_api_exception_returns_fallback():
    with patch("role3.idea_extractor.call_huawei_model", side_effect=RuntimeError("boom")):
        result = extract_idea("盈利超预期", api_url="https://example.test", token="token")

    assert result["is_mock"] is True
    assert result["is_fallback"] is True
    assert "fallback_error" in result["source_meta"]
