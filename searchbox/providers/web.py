"""Web search provider adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import HTTPException


@dataclass(frozen=True)
class WebSearchSettings:
    search_provider: str
    user_agent: str
    request_timeout: float
    brave_api_url: str
    brave_api_key: str
    serper_api_url: str
    serper_api_key: str
    searxng_url: str


@dataclass(frozen=True)
class WebSearchOptions:
    query: str
    count: int
    topic: str | None = None
    country: str | None = None
    brave_safesearch: str = "moderate"
    searxng_safesearch: int = 0
    freshness: str | None = None
    searxng_time_range: str | None = None
    serper_tbs: str | None = None
    search_depth: str = "basic"
    safe_search: bool = False


def searxng_query_url(searxng_url: str) -> str:
    return searxng_url.rstrip("/") + "/search"


def parse_brave_results(data: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    raw_results = data.get("web", {}).get("results", []) if isinstance(data, dict) else []
    parsed: list[dict[str, Any]] = []
    for idx, item in enumerate(raw_results or [], start=1):
        if not isinstance(item, dict):
            continue
        if len(parsed) >= limit:
            break
        parsed.append({
            "rank": idx,
            "title": (item.get("title") or "").strip(),
            "url": (item.get("url") or "").strip(),
            "description": (item.get("description") or "").strip()[:3000],
            "published": item.get("published") or None,
            "language": item.get("language") or None,
            "score": item.get("score") if isinstance(item.get("score"), (int, float)) else None,
            "source": "brave",
            "engine": "brave",
        })
    return parsed


def parse_serper_results(data: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    raw_results = data.get("organic", []) if isinstance(data, dict) else []
    parsed: list[dict[str, Any]] = []
    for idx, item in enumerate(raw_results or [], start=1):
        if not isinstance(item, dict):
            continue
        if len(parsed) >= limit:
            break
        parsed.append({
            "rank": int(item.get("position") or idx),
            "title": (item.get("title") or "").strip(),
            "url": (item.get("link") or "").strip(),
            "description": (item.get("snippet") or "").strip()[:3000],
            "published": item.get("date") or None,
            "language": None,
            "score": None,
            "source": "serper",
            "engine": "google",
            "images": [
                {
                    "url": img.get("imageUrl") or img.get("thumbnailUrl") or img.get("link") or "",
                    "description": img.get("title") or img.get("source"),
                }
                for img in (item.get("images") or [])
                if isinstance(img, dict) and (img.get("imageUrl") or img.get("thumbnailUrl") or img.get("link"))
            ],
        })
    return parsed


def parse_searxng_results(data: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    raw_results = data.get("results", []) if isinstance(data, dict) else []
    parsed: list[dict[str, Any]] = []
    for idx, item in enumerate(raw_results or [], start=1):
        if not isinstance(item, dict):
            continue
        if len(parsed) >= limit:
            break
        parsed.append({
            "rank": idx,
            "title": (item.get("title") or "").strip(),
            "url": (item.get("url") or "").strip(),
            "description": (item.get("content") or "").strip()[:3000],
            "published": item.get("publishedDate") or item.get("published") or None,
            "language": item.get("language") or None,
            "score": item.get("score") if isinstance(item.get("score"), (int, float)) else None,
            "source": "searxng",
            "engine": item.get("engine") if isinstance(item.get("engine"), str) else None,
        })
    return parsed


async def search_brave(options: WebSearchOptions, settings: WebSearchSettings) -> dict[str, Any]:
    if not settings.brave_api_key:
        raise HTTPException(status_code=500, detail="BRAVE_API_KEY is not configured")

    payload: dict[str, Any] = {
        "count": options.count,
        "q": options.query,
        "search_lang": "en",
        "safesearch": options.brave_safesearch,
        "operators": True,
    }
    if options.country:
        payload["country"] = options.country
    if options.freshness:
        payload["freshness"] = options.freshness
    if options.search_depth == "advanced":
        payload["extra_snippets"] = True
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": settings.brave_api_key,
        "User-Agent": settings.user_agent,
    }

    async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
        resp = await client.get(settings.brave_api_url, params=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()


async def search_serper(options: WebSearchOptions, settings: WebSearchSettings) -> dict[str, Any]:
    if not settings.serper_api_key:
        raise HTTPException(status_code=500, detail="SERPER_API_KEY is not configured")

    endpoint = settings.serper_api_url
    if (options.topic or "").strip().lower() == "news":
        endpoint = settings.serper_api_url.rsplit("/", 1)[0] + "/news"
    payload: dict[str, Any] = {
        "q": options.query,
        "num": options.count,
        "hl": "en",
    }
    if options.country:
        payload["gl"] = options.country.lower()
    if options.serper_tbs:
        payload["tbs"] = options.serper_tbs
    if options.safe_search:
        payload["safe"] = "active"

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-API-KEY": settings.serper_api_key,
        "User-Agent": settings.user_agent,
    }

    async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
        resp = await client.post(endpoint, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()


async def search_searxng(options: WebSearchOptions, settings: WebSearchSettings) -> dict[str, Any]:
    params: dict[str, Any] = {
        "q": options.query,
        "format": "json",
        "language": "en",
        "safesearch": options.searxng_safesearch,
        "categories": "general",
    }
    if options.searxng_time_range:
        params["time_range"] = options.searxng_time_range
    headers = {"User-Agent": settings.user_agent}
    async with httpx.AsyncClient(follow_redirects=True, timeout=settings.request_timeout) as client:
        resp = await client.get(searxng_query_url(settings.searxng_url), params=params, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    parsed = parse_searxng_results(data, options.count)
    return {"web": {"results": parsed}}


async def search_provider(options: WebSearchOptions, settings: WebSearchSettings) -> list[dict[str, Any]]:
    if settings.search_provider == "serper":
        data = await search_serper(options, settings)
        return parse_serper_results(data, options.count)
    if settings.search_provider == "brave":
        data = await search_brave(options, settings)
        return parse_brave_results(data, options.count)
    if settings.search_provider == "searxng":
        data = await search_searxng(options, settings)
        return data.get("web", {}).get("results", [])
    raise HTTPException(status_code=400, detail=f"Unknown SEARCH_PROVIDER {settings.search_provider!r}")
