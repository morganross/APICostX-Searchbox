"""Playwright fallback extraction."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from searchbox.text import shorten

from .html import html_to_text

try:
    from playwright.async_api import async_playwright

    PLAYWRIGHT_AVAILABLE = True
except Exception:
    async_playwright = None
    PLAYWRIGHT_AVAILABLE = False


async def extract_with_playwright(
    url: str,
    *,
    user_agent: str,
    timeout_ms: int,
    max_chars: int,
) -> dict[str, Any]:
    if async_playwright is None:
        return {
            "method": "playwright_unavailable",
            "content": None,
            "error": "playwright_import_missing",
        }

    t0 = datetime.now()
    html = None
    page = None
    browser = None
    context = None

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=user_agent)
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            try:
                await page.wait_for_load_state("networkidle", timeout=3000)
            except Exception:
                pass
            html = await page.content()
    except Exception as exc:
        return {
            "method": "playwright_fallback",
            "content": None,
            "error": f"{type(exc).__name__}: {exc}",
            "fetch_ms": int((datetime.now() - t0).total_seconds() * 1000),
        }
    finally:
        if page is not None:
            try:
                await page.close()
            except Exception:
                pass
        if context is not None:
            try:
                await context.close()
            except Exception:
                pass
        if browser is not None:
            try:
                await browser.close()
            except Exception:
                pass

    text = html_to_text(html)
    text = shorten(text, max_chars)

    return {
        "method": "playwright_fallback",
        "content": text if text else None,
        "error": None if text else "playwright_content_empty",
        "fetch_ms": int((datetime.now() - t0).total_seconds() * 1000),
    }
