"""Idea extraction agent.

Real Agno integration should keep this module-level API unchanged and replace
the internals of `extract_idea`.
"""

from __future__ import annotations

from typing import Any

from alpha_workbench.schemas.specs import clone_default_idea_spec


def mock_extract_idea(input_text: str, source_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    idea_spec = clone_default_idea_spec()
    idea_spec["user_input"] = input_text
    idea_spec["source_meta"] = source_meta or {"source_type": "text"}
    return idea_spec


def extract_idea(input_text: str, source_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return mock_extract_idea(input_text, source_meta)
