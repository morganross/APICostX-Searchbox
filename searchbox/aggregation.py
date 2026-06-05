"""Aggregate Searchbox source items into the one-result engine contract."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from .models import SearchItem, TavilySearchResult
from .text import truncate_payload


def aggregate_source_block(item: SearchItem, index: int, kind: str, max_chars: int) -> str:
    title = (item.title or "Untitled").strip()
    url = (item.url or item.canonical_url or "").strip()
    provider = (item.source or item.engine or kind).strip()
    content = (item.content or item.description or "").strip()
    raw = (item.extracted_content or item.raw_content or "").strip()
    body = content or raw
    body = truncate_payload(re.sub(r"\s+", " ", body), max_chars)
    parts = [f"## Source {index}: {title}"]
    if url:
        parts.append(f"URL: {url}")
    parts.append(f"Type: {kind}")
    if provider:
        parts.append(f"Provider: {provider}")
    if item.published:
        parts.append(f"Published: {item.published}")
    if body:
        parts.append(f"Context: {body}")
    return "\n".join(parts).strip()


def _first_http_source_url(items: list[SearchItem], fallback: str) -> str:
    for item in items:
        candidate = (item.url or item.canonical_url or "").strip()
        parsed = urlparse(candidate)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return candidate
    return fallback


def build_aggregate_search_result(
    *,
    query: str,
    request_id: str,
    web_results: list[SearchItem],
    science_results: list[SearchItem],
    classifier_result: dict[str, Any],
    use_science: bool,
    summary_payload: dict[str, Any] | None = None,
    content_max_chars: int,
    raw_content_max_chars: int,
) -> TavilySearchResult:
    sections: list[str] = [
        "# Searchbox Research Context",
        f"Query: {query}",
        f"Request ID: {request_id}",
        f"Scientific retrieval used: {'yes' if use_science else 'no'}",
    ]
    if classifier_result:
        sections.append(
            "Classifier: "
            f"science={bool(classifier_result.get('is_science'))}, "
            f"confidence={classifier_result.get('confidence', 0.0)}, "
            f"reason={classifier_result.get('reason') or classifier_result.get('category') or 'n/a'}"
        )

    if summary_payload:
        answer = str(summary_payload.get("answer") or "").strip()
        highlights = summary_payload.get("highlights")
        confidence = summary_payload.get("confidence")
        sections.append("\n# Summary")
        sections.append(answer or "No summary text was returned by the summarizer.")
        if isinstance(highlights, list) and highlights:
            sections.append("\n# Highlights")
            sections.extend(f"- {str(item).strip()}" for item in highlights if str(item).strip())
        if confidence is not None:
            sections.append(f"Summary confidence: {confidence}")

    science_error = (classifier_result or {}).get("science_retrieval_error")
    if science_error:
        sections.append("\n# Retrieval Notes")
        status_code = science_error.get("status_code") if isinstance(science_error, dict) else None
        detail = science_error.get("detail") if isinstance(science_error, dict) else science_error
        sections.append(
            "Scientific retrieval was selected for this query, but the scientific provider layer did not return usable results. "
            f"Status: {status_code or 'unknown'}. Detail: {detail}"
        )

    sections.append("\n# Web Context")
    if web_results:
        for idx, item in enumerate(web_results, start=1):
            sections.append(aggregate_source_block(item, idx, "web", 1800))
    else:
        sections.append("No web results were returned.")

    if use_science:
        sections.append("\n# Scientific Context")
        if science_results:
            for idx, item in enumerate(science_results, start=1):
                sections.append(aggregate_source_block(item, idx, "scientific", 3500))
        else:
            sections.append(
                "The query was classified as scientific, but no scientific provider returned usable content."
            )

    sources: list[str] = []
    all_items = [*web_results, *science_results]
    for idx, item in enumerate(all_items, start=1):
        title = (item.title or "Untitled").strip()
        url = (item.url or item.canonical_url or "").strip()
        provider = (item.source or item.engine or "").strip()
        kind = "scientific" if item in science_results else "web"
        sources.append(f"{idx}. [{kind}] {title} - {url} ({provider})".strip())
    sections.append("\n# Sources")
    sections.append("\n".join(sources) if sources else "No sources returned.")

    aggregate_content = truncate_payload("\n\n".join([s for s in sections if s]).strip(), content_max_chars)

    raw_sections: list[str] = [aggregate_content, "\n# Raw Extracted Source Text"]
    for idx, item in enumerate(all_items, start=1):
        raw = (item.extracted_content or item.raw_content or item.content or item.description or "").strip()
        if raw:
            raw_sections.append(f"\n## Raw Source {idx}: {item.title or item.url or 'Untitled'}\n{raw}")
    aggregate_raw = truncate_payload("\n".join(raw_sections).strip(), raw_content_max_chars)

    internal_url = f"searchbox://aggregate/{request_id}"
    return TavilySearchResult(
        title=f"Searchbox research context for: {query}",
        url=_first_http_source_url(all_items, internal_url),
        content=aggregate_content,
        raw_content=aggregate_raw,
        score=1.0,
        searchbox_url=internal_url,
        aggregate_url=internal_url,
    )
