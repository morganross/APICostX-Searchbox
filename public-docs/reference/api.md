# API Reference

The primary endpoint is `POST /search`.

## Authentication

If auth is enabled, send:

```http
Authorization: Bearer <SEARCH_API_KEY>
```

If `AUTH_DISABLED=true`, no auth header is required. Public deployments should not run with auth disabled.

## `GET /health`

Lightweight liveness check.

```bash
curl -sS http://127.0.0.1:9000/health
```

The response may include provider names, feature flags, and booleans indicating whether keys are configured. It must not include key values.

## `GET /config`

Non-secret runtime configuration.

Useful for:

- provider order
- classifier settings
- daily quota snapshots
- monthly quota snapshots
- cooldown snapshots
- extraction settings

```bash
curl -sS http://127.0.0.1:9000/config
```

## `GET /status`

Runtime counters and log locations. This is useful for debugging a live process.

## `POST /search`

Main search endpoint.

```bash
curl -sS http://127.0.0.1:9000/search \
  -H 'content-type: application/json' \
  -d '{
    "query": "perovskite solar cell ion migration hysteresis",
    "max_results": 1,
    "include_raw_content": false
  }'
```

### Important Request Fields

`query`: required user query.

`max_results`: compatibility/count hint. Searchbox may fetch multiple internal sources but returns one aggregate result.

`include_raw_content`: tolerated compatibility field. Searchbox may include fuller extracted text where available even when callers omit or disable this flag.

`include_usage`: includes usage metadata.

`advanced_search`: compatibility force-science flag. Normal clients should rely on automatic classification.

`topic`: diagnostic/provider-selection field. Normal clients should not need it.

### Response Contract

Searchbox returns a Tavily-like response with exactly one aggregate result. The recommended engine-facing field is:

```text
results[0].content
```

Example shape:

```json
{
  "query": "...",
  "answer": "Synthesized answer from all gathered sources...",
  "results": [
    {
      "title": "Searchbox research context for: ...",
      "url": "https://example-source.test/article",
      "searchbox_url": "searchbox://aggregate/<request_id>",
      "aggregate_url": "searchbox://aggregate/<request_id>",
      "content": "# Searchbox Research Context\n...",
      "raw_content": "...",
      "score": 1.0
    }
  ]
}
```

The `searchbox_url` and `aggregate_url` fields contain the synthetic `searchbox://aggregate/...` identifier. The primary `url` is an HTTP(S) source URL when one is available so document-oriented engines can accept the aggregate result. If scientific retrieval is selected but all scientific providers fail or are cooling down, `results[0].content` includes a `# Retrieval Notes` section and still returns the available web context.


## Usage Evidence

Searchbox emits per-request usage evidence for downstream metering systems. It does not decide final billable ACM cost. ACM Metering is the final billing authority and should use Searchbox fields as upstream facts.

When `include_usage=true` or `caller=aiq`, the response includes `usage`. Compatibility headers are also emitted on every `/search` response.

Stable compatibility fields:

```text
total_cost_usd
search_cost_usd
scrape_cost_usd
llm_cost_usd
search_requests
scrape_fetches
cost_confidence
llm_cost_source
llm_cost_confidence
```

The detailed evidence envelope lives at `usage.usage_evidence`:

```json
{
  "schema_version": "searchbox-usage-evidence-v1",
  "search": {"attempt_count": 2, "attempts": []},
  "fetch": {"attempt_count": 5, "attempts": []},
  "llm": {"attempt_count": 3, "usage_attempt_count": 2, "cost_sources": {}, "attempts": []}
}
```

LLM cost evidence prefers provider-reported values, including LiteLLM/OpenRouter `usage.cost` and `usage.cost_details.upstream_inference_cost`. Token estimates are used only when upstream providers omit cost fields, and those estimates are marked with lower confidence. Search and fetch attempts include provider/source names, success flags, result counts, HTTP/fetch metadata where available, and failure details when safe to expose.

Relevant response headers include:

```text
X-Searchbox-Usage-Total-Cost
X-Searchbox-Usage-Search-Cost
X-Searchbox-Usage-Scrape-Cost
X-Searchbox-Usage-LLM-Cost
X-Searchbox-Usage-Cost-Confidence
X-Searchbox-Usage-LLM-Cost-Confidence
X-Searchbox-Usage-LLM-Cost-Source
X-Searchbox-Usage-Search-Attempts
X-Searchbox-Usage-Fetch-Attempts
X-Searchbox-Usage-LLM-Attempts
X-Searchbox-Usage-Evidence-Schema
```

## `GET /search`

GET wrapper for manual tests. Prefer `POST /search` for integrations.

## `POST /search-summary`

Compatibility synthesis endpoint. Normal `/search` already generates the synthesized answer and aggregate context.

## `GET /health/monitor`

Operational monitor. Returns provider usage, cooldowns, and recent event summaries.

## `GET /logs/llm-attempts`

Returns recent LLM attempt log rows.

```bash
curl -sS 'http://127.0.0.1:9000/logs/llm-attempts?limit=100'
```

Logs must not include keys, raw prompts, or raw model outputs.

## `GET /logs/provider-events`

Returns recent provider event rows.

```bash
curl -sS 'http://127.0.0.1:9000/logs/provider-events?limit=100'
```

## `GET /search-raw`

Compatibility endpoint for older callers. It delegates to the same one-result intelligent search contract as `/search`.
