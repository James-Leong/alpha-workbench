"""Role3 idea extractor — development copy.

Stable interface contract:
- input: `input_text` + optional `source_meta`
- output: a fixed envelope with `idea_spec`, `is_mock`, `is_fallback`,
  `source_meta`, and `raw_model_response`

Only the middle processing may change later; callers should keep using the
same input parameters and output keys.
"""

from __future__ import annotations

import json
import os
from importlib import import_module
from typing import Any

from alpha_workbench.parsers.text_parser import parse_input_text
from role3.huawei_api import extract_idea_via_huawei


PROMPT_TEMPLATE = '''
请将下面的文本提炼为结构化的 IdeaSpec（JSON），严格只输出 JSON，不要多余说明。

要求输出字段：
- idea_id: 使用英文短句作为 id
- idea_name: 中文简短标题
- core_hypothesis: 中文一句话核心假设
- economic_mechanism: 中文列表，描述经济机制
- required_data_concepts: 中文列表，所需数据字段或概念
- risk_flags: 中文列表，潜在风险/未来函数说明
- evidence: 字符串列表，重要证据片段或引用原文
- summary: 中文简短摘要

文本：\n"""
{text}
"""

请严格返回单个 JSON 对象。
'''


def _build_output_envelope(
    *,
    idea_spec: dict[str, Any],
    source_meta: dict[str, Any] | None,
    is_mock: bool,
    is_fallback: bool,
    raw_model_response: Any,
    missing_fields: list[str] | None = None,
) -> dict[str, Any]:
    envelope: dict[str, Any] = {
        "idea_spec": idea_spec,
        "is_mock": is_mock,
        "is_fallback": is_fallback,
        "source_meta": source_meta or {"source_type": "text"},
        "raw_model_response": raw_model_response,
    }
    if missing_fields:
        envelope["missing_fields"] = missing_fields
    return envelope


def mock_extract_idea(input_text: str, source_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    from alpha_workbench.schemas.specs import clone_default_idea_spec

    idea_spec = clone_default_idea_spec()
    idea_spec["user_input"] = input_text
    idea_spec["source_meta"] = source_meta or {"source_type": "text"}
    return _build_output_envelope(
        idea_spec=idea_spec,
        source_meta=source_meta,
        is_mock=True,
        is_fallback=True,
        raw_model_response=None,
    )


def extract_idea(input_text: str, source_meta: dict[str, Any] | None = None, *, api_url: str | None = None, token: str | None = None) -> dict[str, Any]:
    """Try calling remote Huawei LLM, fallback to mock on failure.

    Arguments `api_url` and `token` override environment variables.
    """
    # If input_text is a path to a PDF file, try to extract text (optional)
    text = input_text
    if isinstance(input_text, str) and os.path.exists(input_text) and input_text.lower().endswith(".pdf"):
        try:
            pdf_module = import_module("PyPDF2")
            reader = pdf_module.PdfReader(input_text)
            pages = [p.extract_text() or "" for p in reader.pages]
            text = "\n\n".join(pages)
        except Exception:
            # fallback: use the file path as a hint; caller may provide extracted text
            text = input_text

    source_meta = source_meta or {"source_type": "text"}
    parsed = parse_input_text(text)
    prompt = PROMPT_TEMPLATE.format(text=parsed["text"]) if parsed.get("text") else PROMPT_TEMPLATE.format(text=text)

    try:
        resp = extract_idea_via_huawei(input_text=prompt, api_url=api_url, token=token)
        # The model may return structured JSON or a text field; try to coerce.
        if isinstance(resp, dict):
            # If response contains 'idea_spec' directly, return it.
            if "idea_spec" in resp and isinstance(resp["idea_spec"], dict):
                return _build_output_envelope(
                    idea_spec=resp["idea_spec"],
                    source_meta=source_meta,
                    is_mock=False,
                    is_fallback=False,
                    raw_model_response=resp,
                    missing_fields=resp.get("missing_fields") if isinstance(resp.get("missing_fields"), list) else None,
                )
            # If response appears to be parsed JSON already
            for k in ("data", "result", "output", "outputs"):
                if k in resp and isinstance(resp[k], dict):
                    return _build_output_envelope(
                        idea_spec=resp[k],
                        source_meta=source_meta,
                        is_mock=False,
                        is_fallback=False,
                        raw_model_response=resp,
                    )
            # If the response is dict but contains text, try to parse it
            candidate_text = None
            if "text" in resp and isinstance(resp["text"], str):
                candidate_text = resp["text"]
            elif "message" in resp and isinstance(resp["message"], str):
                candidate_text = resp["message"]
            elif "choices" in resp and isinstance(resp["choices"], list) and resp["choices"]:
                c = resp["choices"][0]
                if isinstance(c, dict) and "message" in c:
                    candidate_text = c.get("message") or c.get("text")
                else:
                    candidate_text = str(c)

            if candidate_text:
                # try to parse JSON from candidate_text
                try:
                    idea_spec = json.loads(candidate_text)
                    if isinstance(idea_spec, dict):
                        return _build_output_envelope(
                            idea_spec=idea_spec,
                            source_meta=source_meta,
                            is_mock=False,
                            is_fallback=False,
                            raw_model_response=resp,
                        )
                except Exception:
                    # not JSON — wrap
                    return _build_output_envelope(
                        idea_spec={"model_response": candidate_text},
                        source_meta=source_meta,
                        is_mock=False,
                        is_fallback=False,
                        raw_model_response=resp,
                    )

        # Fallback: return raw response wrapped
        return _build_output_envelope(
            idea_spec={"model_response": resp},
            source_meta=source_meta,
            is_mock=False,
            is_fallback=False,
            raw_model_response=resp,
        )
    except Exception:
        return mock_extract_idea(input_text, source_meta)
