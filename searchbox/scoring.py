"""Search result ranking helpers."""

from __future__ import annotations

import re

from .models import SearchItem


def score_item(item: SearchItem, query: str) -> float:
    score = max(0.0, 1.0 - ((max(item.rank, 1) - 1) * 0.05))
    haystack = f"{item.title} {item.description} {item.content or ''}".lower()
    terms = [term for term in re.findall(r"[a-z0-9]+", query.lower()) if len(term) > 2]
    if terms:
        score += min(0.3, sum(1 for term in terms if term in haystack) / len(terms) * 0.3)
    if item.scraped:
        score += 0.2
    if item.content_chars:
        score += min(0.2, item.content_chars / 10000 * 0.2)
    if item.published:
        score += 0.05
    return round(min(score, 1.0), 4)
