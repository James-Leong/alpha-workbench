"""Plain Python workflow wrapper for isolated Role3 development."""

from __future__ import annotations

from typing import Any

from role3.idea_extractor import extract_idea


def run_role3_workflow(
    input_text: str,
    source_meta: dict[str, Any] | None = None,
    api_url: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Run the Role3 idea extraction workflow without touching the main app."""

    normalized_meta = source_meta or {"source_type": "text"}
    return {
        "workflow_mode": "role3_idea_extraction",
        "input_text": input_text,
        "source_meta": normalized_meta,
        "idea_result": extract_idea(
            input_text=input_text,
            source_meta=normalized_meta,
            api_url=api_url,
            token=token,
        ),
        "workflow_meta": {
            "agent": "IdeaExtractionAgent",
            "version": "0.1.0",
            "scope": "role3_only",
        },
    }
