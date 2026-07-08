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

    primary_error: str | None = None
    pymupdf_result: dict[str, Any] | None = None

    # Primary parser: PyMuPDF
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
        pymupdf_result = {
            "source_type": "pdf",
            "text": full_text,
            "page_count": len(pages),
            "pdf_parser": "pymupdf",
        }
        if len(full_text) >= min_text_length:
            pymupdf_result["is_fallback"] = False
            return pymupdf_result
        # Text too short — store the partial result and try pypdf.
        pymupdf_result["is_fallback"] = True
        pymupdf_result["error"] = "PyMuPDF extracted text too short."
        primary_error = "PyMuPDF extracted text too short."
    except ImportError:
        primary_error = "PyMuPDF (fitz) is not installed."
    except Exception as exc:
        primary_error = f"PyMuPDF parsing failed: {exc}"

    # Fallback parser: pypdf
    try:
        import pypdf

        reader = pypdf.PdfReader(path)
        pages = []
        for i, page in enumerate(reader.pages):
            if max_pages is not None and i >= max_pages:
                break
            text = page.extract_text() or ""
            if text.strip():
                pages.append(text)

        full_text = "\n\n".join(pages).strip()
        if len(full_text) >= min_text_length:
            return {
                "source_type": "pdf",
                "text": full_text,
                "page_count": len(pages),
                "is_fallback": False,
                "pdf_parser": "pypdf",
            }

        # pypdf also fell short — return the best result we have.
        best = pymupdf_result if (pymupdf_result and len(pymupdf_result.get("text", "")) >= len(full_text)) else {
            "source_type": "pdf",
            "text": full_text,
            "page_count": len(pages),
            "pdf_parser": "pypdf",
        }
        best.setdefault("is_fallback", True)
        best.setdefault("error", f"{primary_error}; pypdf extracted text too short.")
        if "error" not in best or primary_error:
            best["error"] = f"{primary_error}; pypdf extracted text too short." if primary_error else "pypdf extracted text too short."
        return best

    except ImportError:
        pass  # Will fall through to final return.
    except Exception as exc:
        primary_error = f"{primary_error}; pypdf failed: {exc}" if primary_error else f"pypdf failed: {exc}"

    # Return the partial PyMuPDF result if we have one, otherwise a hard-fallback.
    if pymupdf_result is not None:
        return pymupdf_result
    return {
        "source_type": "pdf",
        "text": "",
        "page_count": 0,
        "error": f"{primary_error}; pypdf is not installed either." if primary_error else "No PDF parser available.",
        "is_fallback": True,
    }


def parse_pdf_text_or_fallback(file_path: str | Path, fallback_text: str = "") -> dict[str, Any]:
    """Parse PDF and fall back to user-provided text if parsing fails."""
    result = parse_pdf(file_path)
    if result.get("is_fallback") and fallback_text.strip():
        result["text"] = fallback_text.strip()
        result["source_type"] = "pdf_fallback_text"
    return result


def maybe_parse_pdf(
    input_text: str,
    source_meta: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Detect PDF input and parse it, returning text and enriched metadata.

    If the input is not a PDF path and source_meta does not mark it as pdf,
    returns the original input unchanged. Parsing failures are logged but do
    not block downstream processing.
    """

    meta = dict(source_meta or {"source_type": "text"})

    is_pdf = meta.get("source_type") == "pdf" or str(input_text).lower().endswith(".pdf")
    if not is_pdf:
        return input_text, meta

    result = parse_pdf(input_text)
    text = result.get("text", "").strip()
    meta["source_type"] = "pdf"
    meta["pdf_page_count"] = result.get("page_count", 0)
    meta["pdf_text_chars"] = len(text)
    meta["pdf_parser"] = result.get("pdf_parser")
    meta["pdf_is_fallback"] = result.get("is_fallback", True)
    if result.get("error"):
        meta["pdf_parse_error"] = result.get("error")

    if text:
        return text, meta
    return input_text, meta
