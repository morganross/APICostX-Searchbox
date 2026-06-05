"""PDF-to-text extraction."""

from __future__ import annotations

import io
import re
from typing import Any

try:
    from pypdf import PdfReader

    PDF_AVAILABLE = True
except Exception:
    PdfReader: Any | None = None
    PDF_AVAILABLE = False


def pdf_to_text(data: bytes) -> str:
    if not PDF_AVAILABLE or PdfReader is None:
        return ""
    try:
        reader = PdfReader(io.BytesIO(data))
        parts = []
        for page in reader.pages:
            parts.append(page.extract_text() or "")
        return re.sub(r"\s+", " ", " ".join(parts)).strip()
    except Exception:
        return ""
