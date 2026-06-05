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

`max_results`: compatibility field. Searchbox may fetch multiple internal sources but returns one recommended aggregate result.

`include_raw_content`: requests fuller extracted text where available.

`include_usage`: includes usage metadata.

`advanced_search`: compatibility force-science flag. Normal clients should rely on automatic classification.

`topic`: diagnostic/provider-selection field. Normal clients should not need it.

### Response Contract

Searchbox returns a Tavily-like response. The recommended engine-facing field is:

```text
results[0].content
```

Example shape:

```json
{
  "query": "...",
  "answer": null,
  "results": [
    {
      "title": "Searchbox research context for: ...",
      "url": "searchbox://aggregate/<request_id>",
      "content": "# Searchbox Research Context\n...",
      "raw_content": "...",
      "score": 1.0
    }
  ]
}
```

The `searchbox://aggregate/...` URL is a synthetic identifier, not a browser URL.

## `GET /search`

GET wrapper for manual tests. Prefer `POST /search` for integrations.

## `POST /search-summary`

Search plus LLM synthesis endpoint. Use this when you want Searchbox to generate an answer rather than only return context.

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

Lower-level diagnostic endpoint. It should not be the primary public integration path.
