"""HTML rendering utilities for DOCX content."""

from __future__ import annotations

from io import BytesIO
from typing import Any

from app.core.errors import OptionalDependencyError, RenderError

_OUTLOOK_CSS = (
    "body {\n"
    "  margin: 0;\n"
    "  padding: 0;\n"
    '  font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", Arial, sans-serif;\n'
    "  font-size: 14px;\n"
    "  line-height: 1.5;\n"
    "}\n"
    "p {\n"
    "  margin: 0 0 12px 0;\n"
    "}\n"
    "table {\n"
    "  border-collapse: collapse;\n"
    "}\n"
)


def docx_bytes_to_html(docx_bytes: bytes) -> str:
    """Render a DOCX payload into a full HTML document.

    Args:
        docx_bytes: Raw DOCX bytes to convert.

    Returns:
        A complete HTML document string ready for Outlook-friendly emails.

    Raises:
        RenderError: If the DOCX cannot be converted.
        OptionalDependencyError: If mammoth is not available.
    """
    if not isinstance(docx_bytes, (bytes, bytearray)):
        raise RenderError("DOCX payload must be bytes.")
    if not docx_bytes:
        raise RenderError("DOCX payload is empty.")

    mammoth = _load_mammoth()
    try:
        result = mammoth.convert_to_html(BytesIO(bytes(docx_bytes)))
    except Exception as exc:
        raise RenderError("Failed to convert DOCX bytes to HTML.") from exc

    html_fragment = result.value or ""
    return _wrap_html_document(html_fragment)


def _wrap_html_document(html_fragment: str) -> str:
    css = _OUTLOOK_CSS.strip()
    body = html_fragment or ""
    return (
        "<!doctype html>\n"
        "<html>\n"
        "<head>\n"
        '<meta charset="utf-8">\n'
        "<style>\n"
        f"{css}\n"
        "</style>\n"
        "</head>\n"
        "<body>\n"
        f"{body}\n"
        "</body>\n"
        "</html>\n"
    )


def _load_mammoth() -> Any:
    """Import mammoth and translate missing dependency errors."""
    try:
        import mammoth
    except ModuleNotFoundError as exc:
        raise OptionalDependencyError(
            "mammoth is required to render DOCX files to HTML."
        ) from exc
    return mammoth
