"""Mock and fallback output for Role3."""

from __future__ import annotations

from typing import Any

from role3.finance_taxonomy import infer_finance_concepts
from role3.validators import validate_idea_spec


def _evidence_snippet(input_text: str, limit: int = 240) -> str:
    compact = " ".join((input_text or "").split())
    return compact[:limit] if compact else "用户输入未提供可用文本。"


def mock_idea_spec(input_text: str, source_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a stable mock envelope for the default earnings-surprise theme."""

    source = dict(source_meta or {"source_type": "text"})
    inferred = infer_finance_concepts(input_text)
    required_data = [
        "实际单季度净利润",
        "市场一致预期净利润",
        "财报公告日",
        "公告前20个交易日收益率",
        "未来持有期收益率",
        "行业分类",
        "市值",
    ]
    for field in inferred["required_fields"]:
        if field not in required_data:
            required_data.append(field)

    risk_flags = [
        "财报公告日处理不当可能产生未来函数",
        "一致预期数据可能不可得，需要使用 proxy 字段",
        "公告前收益率窗口必须严格早于公告日",
        "行业和市值暴露可能造成伪 alpha",
        "单季度利润可能受非经常性损益影响",
    ]
    for risk in inferred["risk_flags"]:
        if risk not in risk_flags:
            risk_flags.append(risk)

    idea_spec = {
        "idea_id": "earnings_surprise_revision",
        "idea_name": "盈利超预期与预期修正",
        "core_hypothesis": "单季度盈利超预期且公告前价格未充分反应的公司，未来可能存在有待回测验证的相对超额收益。",
        "economic_mechanism": [
            "盈利公告形成基本面信息冲击。",
            "分析师盈利预测可能在公告后发生上修。",
            "投资者对业绩改善可能存在反应不足。",
            "公告前价格未充分上涨意味着预期尚未完全反映。",
        ],
        "required_data_concepts": required_data,
        "risk_flags": risk_flags,
        "evidence": [_evidence_snippet(input_text)],
        "summary": "该想法关注盈利超预期、公告前价格反应不足与后续预期修正之间的潜在关联，需要通过事件对齐和中性化回测验证。",
        "factor_directions": [
            "盈利超预期强度",
            "公告前价格反应调整",
            "盈利预测修正强度",
            "行业中性化后的盈利冲击",
        ],
        "uncertainties": [
            "一致预期和公告日时间戳的可得性需要确认。",
            "超额收益是否来自盈利冲击本身有待回测验证。",
            "不同市场阶段和行业中的稳定性可能存在差异。",
        ],
        "suggested_research_spec": {
            "research_question": "盈利超预期且公告前价格反应不足是否能预测公告后相对收益。",
            "target_universe": "A股全市场或可投资股票池",
            "event_date": "财报公告日",
            "signal_definition": "实际单季度净利润相对一致预期的 surprise，并结合公告前20日收益率调整。",
            "holding_period": "20至60个交易日",
            "neutralization": ["industry", "market_cap"],
            "validation_checks": [
                "公告日前后数据可得性检查",
                "行业和市值中性化",
                "分年度、分行业稳健性检验",
            ],
        },
    }
    idea_spec, missing_fields = validate_idea_spec(idea_spec)
    return {
        "idea_spec": idea_spec,
        "is_mock": True,
        "is_fallback": False,
        "source_meta": source,
        "raw_model_response": None,
        "missing_fields": missing_fields,
    }
