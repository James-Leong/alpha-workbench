"""Validation helpers for Role3 IdeaSpec envelopes."""

from __future__ import annotations

from typing import Any


REQUIRED_IDEA_FIELDS = [
    "idea_id",
    "idea_name",
    "core_hypothesis",
    "economic_mechanism",
    "required_data_concepts",
    "risk_flags",
    "evidence",
    "summary",
    "factor_directions",
    "uncertainties",
    "suggested_research_spec",
]

LIST_FIELDS = {
    "economic_mechanism",
    "required_data_concepts",
    "risk_flags",
    "evidence",
    "factor_directions",
    "uncertainties",
}


def default_suggested_research_spec() -> dict[str, Any]:
    """Return conservative default settings for the next research step."""

    return {
        "research_question": "该投资思想是否能形成稳健、可解释、可审计的潜在因子。",
        "target_universe": "A股全市场或可投资股票池",
        "rebalance_frequency": "财报公告后按月或按事件调仓",
        "holding_period": "20至60个交易日",
        "neutralization": ["industry", "market_cap"],
        "validation_checks": [
            "严格使用公告日后可得信息",
            "检查行业和市值暴露",
            "分年度和分行业做稳健性检验",
        ],
    }


def _default_value(field: str) -> Any:
    defaults: dict[str, Any] = {
        "idea_id": "earnings_surprise_revision",
        "idea_name": "盈利超预期与预期修正",
        "core_hypothesis": "盈利超预期且公告前价格未充分反应的公司，未来可能存在有待回测验证的相对收益机会。",
        "economic_mechanism": [],
        "required_data_concepts": [],
        "risk_flags": [],
        "evidence": [],
        "summary": "从输入文本中提炼出盈利超预期、预期修正和公告前价格反应不足相关的潜在因子想法。",
        "factor_directions": [],
        "uncertainties": [],
        "suggested_research_spec": default_suggested_research_spec(),
    }
    return defaults[field]


def _as_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple | set):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def validate_idea_spec(idea_spec: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Fill missing fields and normalize model output into a stable IdeaSpec."""

    normalized = dict(idea_spec or {})
    missing_fields: list[str] = []

    for field in REQUIRED_IDEA_FIELDS:
        value = normalized.get(field)
        is_missing = value is None or value == "" or value == []
        if is_missing:
            normalized[field] = _default_value(field)
            missing_fields.append(field)

    for field in LIST_FIELDS:
        normalized[field] = _as_string_list(normalized.get(field))

    if not isinstance(normalized.get("suggested_research_spec"), dict):
        normalized["suggested_research_spec"] = default_suggested_research_spec()
        if "suggested_research_spec" not in missing_fields:
            missing_fields.append("suggested_research_spec")

    for field in ("idea_id", "idea_name", "core_hypothesis", "summary"):
        normalized[field] = str(normalized.get(field, _default_value(field))).strip()

    return normalized, missing_fields
