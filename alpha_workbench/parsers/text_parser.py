"""Text parsing placeholder for the MVP."""

from __future__ import annotations


def parse_input_text(input_text: str) -> dict[str, str]:
    return {
        "source_type": "text",
        "text": input_text.strip(),
    }
