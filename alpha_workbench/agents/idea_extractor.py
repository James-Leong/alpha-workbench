"""Idea extraction agent.

Real Agno integration keeps the module-level API unchanged and replaces
the internals of `extract_idea`.
"""

from __future__ import annotations

from typing import Any

from agno.agent import Agent
from pydantic import BaseModel, Field

from alpha_workbench.agents.core.model import AlphaModel
from alpha_workbench.core.config import settings
from alpha_workbench.parsers.pdf_parser import parse_pdf
from alpha_workbench.schemas.specs import clone_default_idea_spec


class EvidenceItem(BaseModel):
    """Evidence fragment supporting the investment idea."""

    source: str = Field(..., description="证据来源，如 user_input / pdf_text")
    text: str = Field(..., description="证据原文片段")


class IdeaSpecModel(BaseModel):
    """结构化投资思想输出。"""

    idea_name: str = Field(..., description="投资思想名称")
    core_hypothesis: str = Field(..., description="核心投资假设")
    economic_mechanism: list[str] = Field(..., description="经济机制列表")
    required_data_concepts: list[str] = Field(..., description="所需数据概念列表")
    risk_flags: list[str] = Field(..., description="风险标志列表")
    evidence: list[EvidenceItem] = Field(default_factory=list, description="证据片段")


def _build_prompt(input_text: str) -> str:
    return f"""你是一位量化投资研究专家。请从以下投资想法中提炼出结构化的投资思想（IdeaSpec）。

投资想法：
{input_text}

请输出以下 JSON 结构（不要输出其他内容）：
{{
  "idea_name": "投资思想名称",
  "core_hypothesis": "核心投资假设",
  "economic_mechanism": ["机制1", "机制2", "机制3"],
  "required_data_concepts": ["概念1", "概念2"],
  "risk_flags": ["风险1", "风险2"],
  "evidence": [{{"source": "user_input", "text": "原文片段"}}]
}}

注意：
1. 不要输出交易建议或实盘承诺。
2. 必须标注不确定性、数据替代和潜在风险。
3. 输出必须是合法 JSON。"""


def _extract_input_text(
    input_text: str,
    source_meta: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """统一处理文本/PDF输入，返回用于提炼的文本和来源元数据。"""
    source_meta = source_meta or {"source_type": "text"}
    if source_meta.get("source_type") == "pdf" and source_meta.get("pdf_path"):
        pdf_result = parse_pdf(source_meta["pdf_path"])
        extracted = pdf_result.get("text", "").strip()
        if extracted:
            return extracted, {
                **source_meta,
                "pdf_page_count": pdf_result.get("page_count", 0),
                "pdf_is_fallback": pdf_result.get("is_fallback", True),
                "pdf_error": pdf_result.get("error"),
            }
    return input_text, source_meta


def mock_extract_idea(
    input_text: str,
    source_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    idea_spec = clone_default_idea_spec()
    idea_spec["user_input"] = input_text
    idea_spec["source_meta"] = source_meta or {"source_type": "text"}
    return idea_spec


def extract_idea(
    input_text: str,
    source_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract investment idea using AlphaModel when API key is available."""
    text, source_meta = _extract_input_text(input_text, source_meta)

    if not settings.llm_api_key:
        return mock_extract_idea(text, source_meta)

    try:
        agent = Agent(
            model=AlphaModel(),
            output_schema=IdeaSpecModel,
            instructions="你是一位专业的量化投资研究专家。请从用户输入中提炼结构化的投资思想，输出合法 JSON。",
        )
        response = agent.run(_build_prompt(text))
        result = response.content if hasattr(response, "content") else response
        if isinstance(result, IdeaSpecModel):
            data = result.model_dump()
        elif isinstance(result, dict):
            data = result
        else:
            return mock_extract_idea(text, source_meta)
        data["user_input"] = text
        data["source_meta"] = source_meta
        data["is_mock"] = False
        data["is_fallback"] = False
        return data
    except Exception as e:
        print(f"[IdeaExtractor] LLM调用失败，使用mock fallback: {e}")
        return mock_extract_idea(text, source_meta)
