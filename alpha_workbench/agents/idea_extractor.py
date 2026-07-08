"""Idea extraction agent.

Integrates role3 capabilities (real LLM call, finance taxonomy, validation,
structured fallback) while keeping the module-level API unchanged.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from agno.agent import Agent
from pydantic import BaseModel, Field

from alpha_workbench.agents.core.model import AlphaModel
from alpha_workbench.agents.finance_taxonomy import infer_finance_concepts
from alpha_workbench.core.config import settings
from alpha_workbench.parsers.pdf_parser import maybe_parse_pdf

logger = logging.getLogger(__name__)


class EvidenceItem(BaseModel):
    """Evidence fragment supporting the investment idea."""

    source: str = Field(..., description="证据来源，如 user_input / pdf_text")
    text: str = Field(..., description="证据原文片段")


class SuggestedResearchSpec(BaseModel):
    """Recommended research configuration inferred from the idea."""

    research_question: str = Field(default="", description="研究问题")
    target_universe: str = Field(default="", description="目标股票池")
    rebalance_frequency: str = Field(default="", description="调仓频率")
    holding_period: str = Field(default="", description="持仓周期")
    neutralization: list[str] = Field(default_factory=list, description="中性化维度")
    validation_checks: list[str] = Field(default_factory=list, description="验证检查项")


class IdeaSpecModel(BaseModel):
    """Structured investment idea output."""

    idea_id: str = Field(..., description="英文 snake_case ID")
    idea_name: str = Field(..., description="投资思想名称")
    core_hypothesis: str = Field(..., description="核心投资假设，使用谨慎措辞")
    economic_mechanism: list[str] = Field(..., description="经济机制列表")
    required_data_concepts: list[str] = Field(..., description="所需数据概念列表")
    risk_flags: list[str] = Field(..., description="风险标志列表")
    evidence: list[EvidenceItem] = Field(default_factory=list, description="证据片段")
    summary: str = Field(default="", description="面向研究员的简短摘要")
    factor_directions: list[str] = Field(default_factory=list, description="后续因子方向")
    uncertainties: list[str] = Field(default_factory=list, description="需确认的不确定性")
    suggested_research_spec: SuggestedResearchSpec = Field(
        default_factory=SuggestedResearchSpec,
        description="推荐研究配置",
    )


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
    "factor_directions",
    "uncertainties",
}


def default_suggested_research_spec() -> dict[str, Any]:
    """Return conservative default settings for the next research step."""

    return {
        "research_question": "该投资思想是否能形成稳健、可解释、可审计的潜在因子。",
        "target_universe": "A股全市场或可投资股票池",
        "rebalance_frequency": "monthly",
        "holding_period": "20 trading days",
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


def _normalize_evidence(value: Any) -> list[dict[str, str]]:
    """Keep evidence as list[dict] to match current frontend expectations."""

    if value is None:
        return []
    if isinstance(value, dict):
        return [value]
    if isinstance(value, str):
        stripped = value.strip()
        return [{"source": "user_input", "text": stripped}] if stripped else []
    if isinstance(value, list):
        normalized: list[dict[str, str]] = []
        for item in value:
            if isinstance(item, dict) and "text" in item:
                normalized.append({"source": item.get("source", "user_input"), "text": str(item["text"]).strip()})
            elif isinstance(item, str):
                stripped = item.strip()
                if stripped:
                    normalized.append({"source": "user_input", "text": stripped})
        return normalized
    return []


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

    normalized["evidence"] = _normalize_evidence(normalized.get("evidence"))

    suggested = normalized.get("suggested_research_spec")
    if isinstance(suggested, BaseModel):
        normalized["suggested_research_spec"] = suggested.model_dump()
    elif not isinstance(suggested, dict):
        normalized["suggested_research_spec"] = default_suggested_research_spec()
        if "suggested_research_spec" not in missing_fields:
            missing_fields.append("suggested_research_spec")

    for field in ("idea_id", "idea_name", "core_hypothesis", "summary"):
        normalized[field] = str(normalized.get(field, _default_value(field))).strip()

    return normalized, missing_fields


def _build_prompt(input_text: str, source_meta: dict[str, Any] | None = None) -> str:
    source_json = json.dumps(source_meta or {"source_type": "text"}, ensure_ascii=False)
    template = '''你是 AlphaWorkbench 的 IdeaExtractionAgent，任务是把自然语言投资想法或研报文本抽取为结构化 IdeaSpec。

请只输出一个 JSON 对象，不要输出 Markdown、解释文字或代码块。

输出必须包含以下扁平字段：
{
  "idea_id": "英文 snake_case id",
  "idea_name": "中文短标题",
  "core_hypothesis": "谨慎表述的核心投资假设，不承诺收益",
  "economic_mechanism": ["经济机制1", "经济机制2"],
  "required_data_concepts": ["需要的数据概念"],
  "risk_flags": ["未来函数、数据可得性、样本偏差、行业市值暴露等风险"],
  "evidence": [{"source": "user_input", "text": "来自输入文本的关键证据片段"}],
  "summary": "面向研究员的简短摘要",
  "factor_directions": ["后续可给因子生成环节的因子方向"],
  "uncertainties": ["需要回测或人工确认的不确定性"],
  "suggested_research_spec": {
    "research_question": "研究问题",
    "target_universe": "目标股票池",
    "rebalance_frequency": "调仓频率",
    "holding_period": "持仓周期",
    "neutralization": ["industry", "market_cap"],
    "validation_checks": ["验证检查项"]
  }
}

抽取要求：
- 这是金融投研语义抽取，不是普通摘要。
- 识别核心投资假设、经济机制、所需数据、风险与不确定性、证据片段和后续因子方向。
- 对收益使用"可能""潜在""有待回测验证"等谨慎措辞。
- 禁止输出确定性收益承诺，禁止生成实盘交易建议。
- 如涉及公告日、预测数据、未来收益、行业或市值，请明确数据对齐和暴露风险。

source_meta: __SOURCE_META_PLACEHOLDER__

输入文本：
"""
__INPUT_TEXT_PLACEHOLDER__
"""
'''
    return template.replace("__SOURCE_META_PLACEHOLDER__", source_json).replace("__INPUT_TEXT_PLACEHOLDER__", input_text)


def _extract_text_from_raw(raw: Any) -> str | None:
    if isinstance(raw, str):
        return raw
    if not isinstance(raw, dict):
        return None

    for key in ("text", "content", "message", "result", "output", "data"):
        value = raw.get(key)
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            nested = _extract_text_from_raw(value)
            if nested:
                return nested

    choices = raw.get("choices")
    if isinstance(choices, list) and choices:
        choice = choices[0]
        if isinstance(choice, dict):
            message = choice.get("message")
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                return message["content"]
            if isinstance(choice.get("text"), str):
                return choice["text"]
        if isinstance(choice, str):
            return choice

    return None


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    fence_match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.DOTALL | re.IGNORECASE)
    if fence_match:
        return fence_match.group(1).strip()
    return stripped


def parse_model_response(raw_response: Any) -> dict[str, Any]:
    """Parse raw model output into a dict, accepting common response shapes."""

    if isinstance(raw_response, BaseModel):
        return raw_response.model_dump()

    if isinstance(raw_response, dict):
        if isinstance(raw_response.get("idea_spec"), dict):
            return raw_response["idea_spec"]
        text = _extract_text_from_raw(raw_response)
        if text:
            return parse_model_response(text)
        return raw_response

    if isinstance(raw_response, str):
        text = _strip_code_fence(raw_response)
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, flags=re.DOTALL)
            if not match:
                raise
            parsed = json.loads(match.group(0))
        if not isinstance(parsed, dict):
            raise TypeError(f"Model JSON must be an object, got {type(parsed)!r}")
        if isinstance(parsed.get("idea_spec"), dict):
            return parsed["idea_spec"]
        return parsed

    raise TypeError(f"Unsupported model response type: {type(raw_response)!r}")


def _enrich_with_taxonomy(idea_spec: dict[str, Any], text: str) -> dict[str, Any]:
    enriched = dict(idea_spec)
    inferred = infer_finance_concepts(text)

    required = list(enriched.get("required_data_concepts") or [])
    for field in inferred["required_fields"]:
        if field not in required:
            required.append(field)
    enriched["required_data_concepts"] = required

    risks = list(enriched.get("risk_flags") or [])
    for risk in inferred["risk_flags"]:
        if risk not in risks:
            risks.append(risk)
    enriched["risk_flags"] = risks

    return enriched


def _evidence_snippet(input_text: str, limit: int = 240) -> str:
    compact = " ".join((input_text or "").split())
    return compact[:limit] if compact else "用户输入未提供可用文本。"


def mock_extract_idea(
    input_text: str,
    source_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a stable mock idea spec enhanced with taxonomy signals."""

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
        "evidence": [{"source": "user_input", "text": _evidence_snippet(input_text)}],
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
        "suggested_research_spec": default_suggested_research_spec(),
    }
    idea_spec, missing_fields = validate_idea_spec(idea_spec)
    idea_spec["user_input"] = input_text
    idea_spec["source_meta"] = source
    idea_spec["is_mock"] = True
    idea_spec["is_fallback"] = False
    idea_spec["missing_fields"] = missing_fields
    return idea_spec


def extract_idea(
    input_text: str,
    source_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract investment idea using AlphaModel when API key is available.

    Returns a flat dict compatible with the existing UI and workflow, while
    carrying enriched metadata from the role3 extraction logic.
    """

    text, source_meta = maybe_parse_pdf(input_text, source_meta)

    if not settings.llm_api_key:
        return mock_extract_idea(text, source_meta)

    raw_response: Any = None
    try:
        agent = Agent(
            model=AlphaModel(),
            output_schema=IdeaSpecModel,
            instructions="你是一位专业的量化投资研究专家。请从用户输入中提炼结构化的投资思想，只输出合法 JSON。",
        )
        response = agent.run(_build_prompt(text, source_meta))
        result = response.content if hasattr(response, "content") else response
        raw_response = result

        data = parse_model_response(result)
        data = _enrich_with_taxonomy(data, text)
        data, missing_fields = validate_idea_spec(data)

        data["user_input"] = text
        data["source_meta"] = source_meta
        data["is_mock"] = False
        data["is_fallback"] = False
        data["missing_fields"] = missing_fields
        data["raw_model_response"] = raw_response
        return data
    except Exception as e:
        logger.exception("[IdeaExtractor] LLM调用失败，使用mock fallback")
        fallback = mock_extract_idea(text, source_meta)
        fallback["is_fallback"] = True
        fallback["fallback_error"] = f"{type(e).__name__}: {e}"
        if raw_response is not None:
            fallback["raw_model_response"] = raw_response
        return fallback
