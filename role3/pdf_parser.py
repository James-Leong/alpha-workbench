"""Optional lightweight PDF parsing for Role3."""

from __future__ import annotations

import os
from importlib import import_module
from typing import Any


def _looks_like_pdf(input_text: str, source_meta: dict[str, Any]) -> bool:
    return source_meta.get("source_type") == "pdf" or str(input_text).lower().endswith(".pdf")


def maybe_parse_pdf(
    input_text: str,
    source_meta: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Parse a PDF path when possible, without making PDF support a hard dependency."""

    meta = dict(source_meta or {"source_type": "text"})
    if not _looks_like_pdf(input_text, meta):
        return input_text, meta

    meta["source_type"] = "pdf"
    path = input_text
    if not os.path.exists(path):
        meta["pdf_parse_error"] = "pdf_path_not_found"
        return input_text, meta

    try:
        pymupdf = import_module("fitz")
        doc = pymupdf.open(path)
        try:
            text = "\n\n".join(page.get_text("text") for page in doc)
        finally:
            doc.close()
        meta["pdf_parser"] = "pymupdf"
        meta["pdf_text_chars"] = len(text)
        return text or input_text, meta
    except Exception as exc:
        first_error = f"{type(exc).__name__}: {exc}"

    try:
        pypdf = import_module("pypdf")
        reader = pypdf.PdfReader(path)
        text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
        meta["pdf_parser"] = "pypdf"
        meta["pdf_text_chars"] = len(text)
        return text or input_text, meta
    except Exception as exc:
        meta["pdf_parse_error"] = f"{first_error}; {type(exc).__name__}: {exc}"
        return input_text, meta
