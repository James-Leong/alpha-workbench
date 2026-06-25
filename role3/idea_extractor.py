"""Role3 Idea Agent entrypoint."""

from __future__ import annotations

import json
import re
from typing import Any

from role3.fallback import mock_idea_spec
from role3.finance_taxonomy import infer_finance_concepts
from role3.huawei_api import call_huawei_model
from role3.pdf_parser import maybe_parse_pdf
from role3.prompt_templates import build_idea_extraction_prompt
from role3.validators import validate_idea_spec


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

    if isinstance(raw_response, dict):
        if isinstance(raw_response.get("idea_spec"), dict):
            return raw_response
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


def _fallback_with_error(
    input_text: str,
    source_meta: dict[str, Any],
    error: Exception,
    raw_model_response: Any = None,
) -> dict[str, Any]:
    envelope = mock_idea_spec(input_text, source_meta)
    envelope["is_fallback"] = True
    envelope["source_meta"] = {**source_meta, "fallback_error": f"{type(error).__name__}: {error}"}
    if raw_model_response is not None:
        envelope["raw_model_response"] = raw_model_response
    return envelope


def extract_idea(
    input_text: str,
    source_meta: dict[str, Any] | None = None,
    *,
    api_url: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Extract a stable IdeaSpec envelope from text or a PDF path."""

    try:
        parsed_text, normalized_meta = maybe_parse_pdf(input_text, source_meta)
    except Exception as exc:
        normalized_meta = dict(source_meta or {"source_type": "text"})
        return _fallback_with_error(input_text, normalized_meta, exc)

    if not api_url or not token:
        return mock_idea_spec(parsed_text, normalized_meta)

    raw_response: Any = None
    try:
        prompt = build_idea_extraction_prompt(parsed_text, normalized_meta)
        raw_response = call_huawei_model(prompt=prompt, api_url=api_url, token=token)
        parsed_response = parse_model_response(raw_response)
        candidate = parsed_response.get("idea_spec", parsed_response)
        if not isinstance(candidate, dict):
            raise TypeError("Parsed model response does not contain a dict idea_spec.")

        idea_spec = _enrich_with_taxonomy(candidate, parsed_text)
        idea_spec, missing_fields = validate_idea_spec(idea_spec)
        return {
            "idea_spec": idea_spec,
            "is_mock": False,
            "is_fallback": False,
            "source_meta": normalized_meta,
            "raw_model_response": raw_response,
            "missing_fields": missing_fields,
        }
    except Exception as exc:
        return _fallback_with_error(parsed_text, normalized_meta, exc, raw_response)
