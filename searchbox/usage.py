"""Usage and cost evidence helpers.

Searchbox emits upstream facts for ACM Metering to adjudicate. Compatibility
cost totals remain present for existing callers, but provider-reported facts are
preferred over local token estimates whenever they are available.
"""

from __future__ import annotations

from typing import Any


def _as_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _as_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def extract_llm_cost_usd(llm_usage: dict[str, Any] | None) -> tuple[float, str, str]:
    """Return ``(cost, source, confidence)`` for one upstream LLM usage object."""
    if not isinstance(llm_usage, dict) or not llm_usage:
        return 0.0, "none", "none"

    reported = _as_float(llm_usage.get("cost"))
    if reported is not None:
        return reported, "provider_reported", "exact"

    details = llm_usage.get("cost_details")
    if isinstance(details, dict):
        for key in ("upstream_inference_cost", "total_cost", "total_cost_usd", "cost"):
            reported = _as_float(details.get(key))
            if reported is not None:
                return reported, f"provider_cost_details.{key}", "exact"

    prompt_tokens = _as_int(llm_usage.get("prompt_tokens") or llm_usage.get("input_tokens"))
    completion_tokens = _as_int(llm_usage.get("completion_tokens") or llm_usage.get("output_tokens"))
    if prompt_tokens or completion_tokens:
        estimated = (prompt_tokens * 0.00000015) + (completion_tokens * 0.0000006)
        return estimated, "token_estimate", "estimated"

    return 0.0, "none", "none"


def _llm_usage_from_attempt(attempt: dict[str, Any]) -> dict[str, Any] | None:
    usage = attempt.get("usage") if isinstance(attempt, dict) else None
    return usage if isinstance(usage, dict) else None


def summarize_llm_attempts(
    llm_attempts: list[dict[str, Any]] | None,
    fallback_usage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    attempts = [dict(item) for item in (llm_attempts or []) if isinstance(item, dict)]
    if not attempts and isinstance(fallback_usage, dict) and fallback_usage:
        attempts = [{"role": "summary", "success": True, "usage": fallback_usage}]

    total_cost = 0.0
    total_prompt = 0
    total_completion = 0
    total_tokens = 0
    cost_sources: dict[str, int] = {}
    usage_attempts = 0
    exact_count = 0
    estimated_count = 0

    for attempt in attempts:
        usage = _llm_usage_from_attempt(attempt)
        if not usage:
            continue
        usage_attempts += 1
        cost, source, confidence = extract_llm_cost_usd(usage)
        total_cost += cost
        cost_sources[source] = cost_sources.get(source, 0) + 1
        if confidence == "exact":
            exact_count += 1
        elif confidence == "estimated":
            estimated_count += 1
        total_prompt += _as_int(usage.get("prompt_tokens") or usage.get("input_tokens"))
        total_completion += _as_int(usage.get("completion_tokens") or usage.get("output_tokens"))
        total_tokens += _as_int(usage.get("total_tokens"))

    if usage_attempts == 0:
        confidence = "none"
    elif estimated_count == 0:
        confidence = "exact"
    elif exact_count == 0:
        confidence = "estimated"
    else:
        confidence = "mixed"

    return {
        "attempt_count": len(attempts),
        "usage_attempt_count": usage_attempts,
        "success_count": sum(1 for item in attempts if item.get("success") is True),
        "failure_count": sum(1 for item in attempts if item.get("success") is False),
        "cost_usd": round(total_cost, 6),
        "cost_confidence": confidence,
        "cost_sources": cost_sources,
        "prompt_tokens": total_prompt,
        "completion_tokens": total_completion,
        "total_tokens": total_tokens or (total_prompt + total_completion),
    }


def summarize_fetch_attempts(fetch_attempts: list[dict[str, Any]] | None) -> dict[str, Any]:
    attempts = [dict(item) for item in (fetch_attempts or []) if isinstance(item, dict)]
    return {
        "attempt_count": len(attempts),
        "success_count": sum(1 for item in attempts if item.get("success") is True),
        "failure_count": sum(1 for item in attempts if item.get("success") is False),
        "http_fetches": sum(1 for item in attempts if item.get("method") != "playwright_fallback"),
        "playwright_fetches": sum(1 for item in attempts if item.get("method") == "playwright_fallback"),
        "cost_usd": 0.0,
        "cost_confidence": "exact",
    }


def calculate_searchbox_usage(
    provider: str,
    search_queries: int = 0,
    scrapes_http: int = 0,
    scrapes_playwright: int = 0,
    llm_usage: dict[str, Any] | None = None,
    llm_attempts: list[dict[str, Any]] | None = None,
    search_attempts: list[dict[str, Any]] | None = None,
    fetch_attempts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    is_free_advanced_source = provider in {"advanced:arxiv"}
    is_metered_advanced_source = provider in {
        "advanced:auto",
        "advanced:agentic_data",
        "advanced:sciencestack",
        "advanced:oanor",
        "advanced:searchapi_scholar",
        "advanced:serpapi_scholar",
    }
    is_web_plus_advanced = provider.startswith("web+advanced:")
    billable_search_queries = 1 if is_web_plus_advanced else search_queries
    search_cost = 0.0 if (is_free_advanced_source or is_metered_advanced_source) else billable_search_queries * 0.001
    # Fetches and scrapes are local Searchbox work, not pass-through paid provider usage.
    scrape_cost = 0.0

    llm_summary = summarize_llm_attempts(llm_attempts, fallback_usage=llm_usage)
    llm_cost = float(llm_summary["cost_usd"])
    fetch_summary = summarize_fetch_attempts(fetch_attempts)
    search_attempts_clean = [dict(item) for item in (search_attempts or []) if isinstance(item, dict)]
    search_confidence = (
        "unknown_external_meter"
        if (is_metered_advanced_source or is_web_plus_advanced)
        else ("exact" if is_free_advanced_source else "estimated")
    )

    total_cost = search_cost + scrape_cost + llm_cost

    return {
        "cost_schema_version": "searchbox-cost-v1",
        "search_provider": provider,
        "total_cost_usd": round(total_cost, 6),
        "search_cost_usd": round(search_cost, 6),
        "scrape_cost_usd": round(scrape_cost, 6),
        "llm_cost_usd": round(llm_cost, 6),
        "search_requests": search_queries,
        "scrape_fetches": scrapes_http + scrapes_playwright,
        "llm_cost_source": "attempt_rollup" if llm_summary["usage_attempt_count"] else "none",
        "llm_cost_confidence": llm_summary["cost_confidence"],
        "usage_evidence": {
            "schema_version": "searchbox-usage-evidence-v1",
            "search": {
                "provider": provider,
                "attempt_count": len(search_attempts_clean) or search_queries,
                "reported_request_count": search_queries,
                "cost_usd": round(search_cost, 6),
                "cost_confidence": search_confidence,
                "attempts": search_attempts_clean,
            },
            "fetch": {**fetch_summary, "attempts": fetch_attempts or []},
            "llm": {**llm_summary, "attempts": llm_attempts or ([] if llm_usage is None else [{"usage": llm_usage}])},
        },
        "cost_confidence": (
            "unknown_external_meter"
            if (is_metered_advanced_source or is_web_plus_advanced)
            else ("exact" if is_free_advanced_source and llm_summary["cost_confidence"] in {"none", "exact"} else "estimated")
        ),
    }
