# Searchbox SerpApi Google Scholar Patch

## Purpose

Add SerpApi as a native scientific provider in Searchbox for Google Scholar retrieval.

## Runtime Config

```text
SERPAPI_API_KEY=<set only in /home/ubuntu/APICostX-Searchbox/.env>
SERPAPI_API_URL=https://serpapi.com/search.json
SERPAPI_TIMEOUT=30
SERPAPI_MAX_RESULTS=8
SERPAPI_DAILY_REQUEST_LIMIT=250
SERPAPI_MONTHLY_REQUEST_LIMIT=250
ADVANCED_SEARCH_AUTO_PROVIDER_ORDER=sciencestack,searchapi_scholar,serpapi_scholar,agentic_data,arxiv,oanor
```

## Code Path

- `serpapi_scholar` is available in `/config` advanced search sources.
- Auto scientific routing includes `serpapi_scholar` after ScienceStack and SearchAPI Scholar.
- Daily quota is persisted in `data/advanced_provider_daily_usage.json`.
- Monthly quota is enforced for SerpApi and persisted in `data/advanced_provider_monthly_usage.json`.
- Provider failures use the same persistent cooldown machinery as other scientific providers.
- Content extraction prefers SerpApi `resources[]` links, then the main Scholar result link.
- Long extracted documents use the existing full-text LLM summary path.

## Verification

A direct adapter test for `lithium dendrite solid electrolyte interface` returned one `serpapi_scholar` result, fetched article text, extracted about 74k characters, and used the LLM summary path.
