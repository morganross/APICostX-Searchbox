"""Request option and result-bucket resolution helpers.

Pure functions here intentionally do not require any side effects so they can be
unit-tested in isolation.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .models import SearchItem
from .text import boolish as _boolish
from .text import bounded_int as _bounded_int


def resolve_max_results(req: Any, *, default_count: int, max_count: int) -> int:
    value = getattr(req, "max_results", None)
    if value is None:
        value = getattr(req, "count", default_count)
    return _bounded_int(value, default_count, 0, max_count)


def resolve_include_content(req: Any, default: bool = False) -> bool:
    mode = (getattr(req, "response_mode", None) or "").strip().lower()
    if mode in ("search_with_content", "search_with_answer", "answer", "debug"):
        return True
    include_content = bool(getattr(req, "include_content", default))
    include_raw = getattr(req, "include_raw_content", None)
    if include_raw is not None:
        return _boolish(include_raw, default=False)
    return include_content


def resolve_include_answer(req: Any, default: bool = False) -> bool:
    mode = (getattr(req, "response_mode", None) or "").strip().lower()
    if mode in ("search_only", "search_with_content"):
        return False
    if mode in ("search_with_answer", "answer", "debug"):
        return True
    return _boolish(getattr(req, "include_answer", None), default=default)


def resolve_debug(req: Any) -> bool:
    mode = (getattr(req, "response_mode", None) or "").strip().lower()
    return bool(getattr(req, "debug", False) or mode == "debug")


def resolve_unused_results(items: List[SearchItem], max_sources: int) -> List[SearchItem]:
    usable_seen = 0
    unused: List[SearchItem] = []
    for item in items:
        if item.url and item.scraped and item.content and usable_seen < max_sources:
            usable_seen += 1
            continue
        unused.append(item)
    return unused


def resolve_country(req: Any) -> Optional[str]:
    country = (getattr(req, "country", None) or "").strip()
    if not country:
        return None
    return country[:2].upper()


def resolve_brave_safesearch(req: Any) -> str:
    return "strict" if getattr(req, "safe_search", False) else "moderate"


def resolve_searxng_safesearch(req: Any) -> int:
    return 1 if getattr(req, "safe_search", False) else 0


def resolve_freshness(req: Any) -> Optional[str]:
    start_date = (getattr(req, "start_date", None) or "").strip()
    end_date = (getattr(req, "end_date", None) or "").strip()
    if start_date and end_date:
        return f"{start_date}to{end_date}"

    value = (getattr(req, "time_range", None) or "").strip().lower()
    mapping: Dict[str, str] = {
        "day": "pd",
        "d": "pd",
        "24h": "pd",
        "week": "pw",
        "w": "pw",
        "7d": "pw",
        "month": "pm",
        "m": "pm",
        "31d": "pm",
        "year": "py",
        "y": "py",
        "365d": "py",
    }
    return mapping.get(value)


def resolve_searxng_time_range(req: Any) -> Optional[str]:
    value = (getattr(req, "time_range", None) or "").strip().lower()
    mapping: Dict[str, str] = {
        "day": "day",
        "d": "day",
        "24h": "day",
        "month": "month",
        "m": "month",
        "31d": "month",
        "year": "year",
        "y": "year",
        "365d": "year",
    }
    return mapping.get(value)


def resolve_serper_tbs(req: Any) -> Optional[str]:
    days = getattr(req, "days", None)
    if days:
        return f"qdr:d{int(days)}"
    start_date = (getattr(req, "start_date", None) or "").strip()
    end_date = (getattr(req, "end_date", None) or "").strip()
    if start_date and end_date:
        return f"cdr:1,cd_min:{start_date},cd_max:{end_date}"

    value = (getattr(req, "time_range", None) or "").strip().lower()
    mapping: Dict[str, str] = {
        "day": "qdr:d",
        "d": "qdr:d",
        "24h": "qdr:d",
        "week": "qdr:w",
        "w": "qdr:w",
        "7d": "qdr:w",
        "month": "qdr:m",
        "m": "qdr:m",
        "31d": "qdr:m",
        "year": "qdr:y",
        "y": "qdr:y",
        "365d": "qdr:y",
    }
    return mapping.get(value)


def resolve_search_depth(req: Any) -> str:
    depth = (getattr(req, "search_depth", None) or "basic").strip().lower()
    return depth if depth else "basic"


def resolve_summarize_top_n(req: Any, *, default: int = 5, max_count: int) -> int:
    return _bounded_int(getattr(req, "summarize_top_n", None), default, 1, max_count)


def resolve_max_chars_per_source(req: Any, default: int = 4000) -> int:
    explicit = getattr(req, "max_chars_per_source", None)
    if explicit is not None:
        return _bounded_int(explicit, default, 500, 16000)
    chunks = getattr(req, "chunks_per_source", None)
    if chunks is not None:
        return _bounded_int(chunks, 3, 1, 5) * 500
    return default


def resolve_timeout(req: Any, *, default: float = 20) -> float:
    return float(getattr(req, "timeout", None) or default)


def split_result_buckets(items: List[SearchItem], max_sources: int) -> Dict[str, List[SearchItem]]:
    used = 0
    not_summarized: List[SearchItem] = []
    excluded: List[SearchItem] = []
    for item in items:
        usable = bool(item.url and item.scraped and item.content)
        if usable and used < max_sources:
            used += 1
        elif usable:
            not_summarized.append(item)
        else:
            excluded.append(item)
    return {"not_summarized": not_summarized, "excluded_results": excluded}
