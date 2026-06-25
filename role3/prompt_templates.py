"""Prompt templates for Role3 idea extraction."""

from __future__ import annotations

import json
from typing import Any


def build_idea_extraction_prompt(input_text: str, source_meta: dict[str, Any] | None = None) -> str:
    """Build a strict JSON-only prompt for finance semantic extraction."""

    source_json = json.dumps(source_meta or {"source_type": "text"}, ensure_ascii=False)
    return f"""你是 AlphaWorkbench 的 Role3 IdeaExtractionAgent，任务是把自然语言投资想法或研报文本抽取为结构化 IdeaSpec。

请只输出一个 JSON 对象，不要输出 Markdown、解释文字或代码块。

输出必须包含：
{{
  "idea_spec": {{
    "idea_id": "英文 snake_case id",
    "idea_name": "中文短标题",
    "core_hypothesis": "谨慎表述的核心投资假设，不承诺收益",
    "economic_mechanism": ["经济机制1", "经济机制2"],
    "required_data_concepts": ["需要的数据概念"],
    "risk_flags": ["未来函数、数据可得性、样本偏差、行业市值暴露等风险"],
    "evidence": ["来自输入文本的关键证据片段"],
    "summary": "面向研究员的简短摘要",
    "factor_directions": ["后续可给 Role4 的因子方向"],
    "uncertainties": ["需要回测或人工确认的不确定性"],
    "suggested_research_spec": {{}}
  }}
}}

抽取要求：
- 这是金融投研语义抽取，不是普通摘要。
- 识别核心投资假设、经济机制、所需数据、风险与不确定性、证据片段和后续因子方向。
- 对收益使用“可能”“潜在”“有待回测验证”等谨慎措辞。
- 禁止输出确定性收益承诺，禁止生成实盘交易建议。
- 如涉及公告日、预测数据、未来收益、行业或市值，请明确数据对齐和暴露风险。

source_meta: {source_json}

输入文本：
\"\"\"
{input_text}
\"\"\"
"""
