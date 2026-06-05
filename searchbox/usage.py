"""Usage and cost estimate helpers."""

from typing import Any


def calculate_searchbox_usage(
    provider: str,
    search_queries: int = 0,
    scrapes_http: int = 0,
    scrapes_playwright: int = 0,
    llm_usage: dict[str, Any] | None = None,
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
    scrape_cost = (
        0.0
        if (is_free_advanced_source or is_metered_advanced_source)
        else (scrapes_http * 0.0) + (scrapes_playwright * 0.005)
    )

    llm_cost = 0.0
    if llm_usage:
        prompt_tokens = llm_usage.get("prompt_tokens") or llm_usage.get("input_tokens") or 0
        completion_tokens = llm_usage.get("completion_tokens") or llm_usage.get("output_tokens") or 0
        llm_cost = (prompt_tokens * 0.00000015) + (completion_tokens * 0.0000006)

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
        "cost_confidence": (
            "unknown_external_meter"
            if (is_metered_advanced_source or is_web_plus_advanced)
            else ("exact" if is_free_advanced_source else "estimated")
        ),
    }
