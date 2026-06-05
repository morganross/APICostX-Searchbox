"""Generic text and model utility helpers."""

from typing import Any
import re


def shorten(text: str, max_chars: int) -> str:
    return (text or "")[:max_chars]


def boolish(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in ("", "0", "false", "no", "off", "none")
    return bool(value)


def bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(minimum, min(maximum, parsed))


def model_dict(model: Any) -> dict[str, Any]:
    return model.model_dump() if hasattr(model, "model_dump") else model.dict()


def chunk_text(text: str, chunks_per_source: int | None) -> str:
    if not text:
        return ""
    count = bounded_int(chunks_per_source, 3, 1, 5) if chunks_per_source else 1
    chunks: list[str] = []
    cleaned = re.sub(r"\s+", " ", text).strip()
    for idx in range(count):
        start = idx * 500
        chunk = cleaned[start:start + 500].strip()
        if not chunk:
            break
        chunks.append(f"<chunk {idx + 1}> {chunk}")
    return " [...] ".join(chunks)
