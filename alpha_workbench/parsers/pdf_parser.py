"""PDF parser for research report input."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def parse_pdf(
    file_path: str | Path,
    *,
    max_pages: int | None = None,
    min_text_length: int = 50,
) -> dict[str, Any]:
    """Extract text from a PDF file.

    Args:
        file_path: Path to the PDF file.
        max_pages: Maximum number of pages to extract (None for all).
        min_text_length: Minimum total text length to consider successful.

    Returns:
        Dict with source_type, text, page_count, and is_fallback.
    """
    path = Path(file_path)
    if not path.exists():
        return {
            "source_type": "pdf",
            "text": "",
            "page_count": 0,
            "error": f"File not found: {path}",
            "is_fallback": True,
        }

    try:
        import fitz  # PyMuPDF

        doc = fitz.open(path)
        pages = []
        for i, page in enumerate(doc):
            if max_pages is not None and i >= max_pages:
                break
            text = page.get_text()
            if text.strip():
                pages.append(text)
        doc.close()

        full_text = "\n\n".join(pages).strip()
        if len(full_text) < min_text_length:
            return {
                "source_type": "pdf",
                "text": full_text,
                "page_count": len(pages),
                "error": "Extracted text is too short; PDF may be image-based or empty.",
                "is_fallback": True,
            }

        return {
            "source_type": "pdf",
            "text": full_text,
            "page_count": len(pages),
            "is_fallback": False,
        }
    except ImportError:
        return {
            "source_type": "pdf",
            "text": "",
            "page_count": 0,
            "error": "PyMuPDF (fitz) is not installed. Install it with: uv add pymupdf",
            "is_fallback": True,
        }
    except Exception as exc:
        return {
            "source_type": "pdf",
            "text": "",
            "page_count": 0,
            "error": f"PDF parsing failed: {exc}",
            "is_fallback": True,
        }


def parse_pdf_text_or_fallback(file_path: str | Path, fallback_text: str = "") -> dict[str, Any]:
    """Parse PDF and fall back to user-provided text if parsing fails."""
    result = parse_pdf(file_path)
    if result.get("is_fallback") and fallback_text.strip():
        result["text"] = fallback_text.strip()
        result["source_type"] = "pdf_fallback_text"
    return result
