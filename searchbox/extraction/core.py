"""Network content extraction orchestration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urljoin

import httpx

from searchbox.text import shorten
from searchbox.urls import validate_fetch_url

from .html import html_to_text
from .pdf import pdf_to_text
from .playwright import PLAYWRIGHT_AVAILABLE, extract_with_playwright

try:
    import trafilatura
except Exception:
    trafilatura = None


@dataclass(frozen=True)
class ExtractionSettings:
    user_agent: str
    max_redirects: int = 5
    block_private_fetch_ips: bool = True
    use_playwright: bool = True
    playwright_timeout_ms: int = 15000
    playwright_max_chars: int = 60000
    min_content_chars: int = 240
    default_max_chars: int = 160000


async def extract_content(url: str, timeout_s: float, *, settings: ExtractionSettings) -> dict[str, Any]:
    validate_fetch_url(url, block_private_fetch_ips=settings.block_private_fetch_ips)
    headers = {"User-Agent": settings.user_agent}
    t0 = datetime.now()

    html = None
    body = b""
    fetch_error = None
    method = "failed"
    fetch_ms = 0
    http_status = None
    content_type = None
    canonical_url = url

    async with httpx.AsyncClient(follow_redirects=False, timeout=timeout_s) as client:
        current_url = url
        for attempt in range(2):
            try:
                for _ in range(settings.max_redirects + 1):
                    validate_fetch_url(
                        current_url,
                        block_private_fetch_ips=settings.block_private_fetch_ips,
                    )
                    response = await client.get(current_url, headers=headers)
                    http_status = response.status_code
                    canonical_url = str(response.url)
                    content_type = response.headers.get("content-type")
                    if response.status_code in (301, 302, 303, 307, 308) and response.headers.get("location"):
                        current_url = urljoin(current_url, response.headers["location"])
                        continue
                    response.raise_for_status()
                    body = response.content
                    html = response.text if "text" in (content_type or "") or "html" in (content_type or "") else None
                    fetch_ms = int((datetime.now() - t0).total_seconds() * 1000)
                    break
                break
            except Exception as exc:
                fetch_ms = int((datetime.now() - t0).total_seconds() * 1000)
                fetch_error = f"{type(exc).__name__}: {exc}"
                if attempt == 0:
                    await asyncio.sleep(0.2)
                    continue

    text = None
    if (content_type or "").lower().split(";", 1)[0] == "application/pdf" or canonical_url.lower().endswith(".pdf"):
        text = pdf_to_text(body)
        method = "pdf_pypdf" if text else "pdf_unavailable_or_empty"

    if not text and html and trafilatura is not None:
        text = trafilatura.extract(html)
        method = "trafilatura" if text else "trafilatura_empty"

    if not text:
        text = html_to_text(html)
        method = "bs4_fallback" if text else "bs4_fallback"

    if (not text or len(text) < settings.min_content_chars) and settings.use_playwright and PLAYWRIGHT_AVAILABLE:
        playwright_result = await extract_with_playwright(
            url,
            user_agent=settings.user_agent,
            timeout_ms=settings.playwright_timeout_ms,
            max_chars=settings.playwright_max_chars,
        )
        pw_method = playwright_result.get("method")
        if playwright_result.get("content") and len(playwright_result["content"]) > len(text or ""):
            text = playwright_result.get("content")
            method = pw_method
        if playwright_result.get("error") and not text:
            fetch_error = (fetch_error + " | " if fetch_error else "") + playwright_result.get("error")
        elif not fetch_error:
            fetch_error = None
        fetch_ms = max(fetch_ms, int(playwright_result.get("fetch_ms") or 0))

    text = shorten((text or "").strip(), settings.default_max_chars)

    return {
        "content": text if text else None,
        "scraped": bool(text),
        "content_chars": len(text or ""),
        "fetch_ms": int(fetch_ms),
        "error": None if text else (fetch_error or "no_content_extracted"),
        "extract_method": method if text else "failed",
        "fetch_status": "ok" if text else "failed",
        "http_status": http_status,
        "content_type": content_type,
        "failure_reason": None if text else (fetch_error or method or "no_content_extracted"),
        "canonical_url": canonical_url,
    }
