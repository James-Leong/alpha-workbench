"""Small rule-based finance taxonomy for Role3 extraction."""

from __future__ import annotations

from typing import Any


FINANCE_CONCEPT_MAP: dict[str, dict[str, Any]] = {
    "盈利超预期": {
        "keywords": ["盈利超预期", "业绩超预期", "净利润超预期", "利润超预期", "earnings surprise"],
        "canonical_name": "earnings_surprise",
        "required_fields": [
            "actual_quarterly_profit",
            "expected_quarterly_profit",
            "announcement_date",
        ],
        "risk_flags": [
            "expectation_data_unavailable",
            "announcement_date_lookahead",
            "one-off_items_distortion",
        ],
    },
    "预期修正": {
        "keywords": ["预期修正", "预测上修", "一致预期上修", "分析师上调", "revision"],
        "canonical_name": "earnings_revision",
        "required_fields": [
            "analyst_forecast_before_announcement",
            "analyst_forecast_after_announcement",
            "forecast_revision_date",
        ],
        "risk_flags": [
            "forecast_timestamp_alignment",
            "analyst_coverage_bias",
        ],
    },
    "公告前价格反应": {
        "keywords": ["公告前", "价格未充分反应", "股价没有明显上涨", "公告前收益率", "pre-announcement"],
        "canonical_name": "pre_announcement_price_reaction",
        "required_fields": [
            "pre_announcement_20d_return",
            "announcement_date",
            "future_holding_period_return",
        ],
        "risk_flags": [
            "pre_announcement_window_must_end_before_event",
            "event_date_alignment_error",
        ],
    },
    "行业市值中性": {
        "keywords": ["行业", "市值", "中性化", "风格暴露", "market cap"],
        "canonical_name": "industry_size_neutralization",
        "required_fields": ["industry_classification", "market_cap"],
        "risk_flags": ["industry_or_size_exposure_false_alpha"],
    },
}


def _append_unique(target: list[str], values: list[str]) -> None:
    for value in values:
        if value not in target:
            target.append(value)


def infer_finance_concepts(text: str) -> dict[str, Any]:
    """Infer canonical concepts, data fields, and risks using keyword matches."""

    haystack = (text or "").lower()
    concepts: list[str] = []
    required_fields: list[str] = []
    risk_flags: list[str] = []

    for config in FINANCE_CONCEPT_MAP.values():
        keywords = [str(keyword).lower() for keyword in config["keywords"]]
        if any(keyword in haystack for keyword in keywords):
            concepts.append(config["canonical_name"])
            _append_unique(required_fields, config["required_fields"])
            _append_unique(risk_flags, config["risk_flags"])

    if not concepts:
        concepts.append("general_investment_hypothesis")

    return {
        "concepts": concepts,
        "required_fields": required_fields,
        "risk_flags": risk_flags,
    }
