# Searchbox API Reference

## `GET /health`

Lightweight service health.

Returns provider/key availability and summarizer availability.

## `GET /config`

Returns non-secret runtime configuration, including:

- web provider configuration
- advanced scientific provider list, including `serpapi_scholar` when configured
- daily and monthly limits
- cooldown snapshot
- LLM config names and feature switches
- security switches

Does not return API key values.

## `GET /status`

Returns in-memory runtime counters plus log file locations.

This is useful for live process state, but durable auditing should use the JSONL logs.

## `POST /search`

Main Tavily-compatible search endpoint. This is the canonical engine integration surface. Searchbox always performs its intelligent retrieval pipeline before responding, then returns one aggregate result.

Typical request:

```json
{
  "query": "perovskite solar cell ion migration hysteresis",
  "max_results": 3,
  "include_raw_content": false
}
```

Current fields still include `advanced_search` for compatibility. Searchbox also classifies science queries automatically, so clients do not need to choose scientific retrieval themselves.

Response fields:

```text
query
answer
results[]
usage, when include_usage=true or caller=aiq
_searchbox_usage, internal usage payload
```

Each result has:

```text
title
url
content
raw_content
score
```

Result behavior:

- `results` always contains exactly one aggregate result object.
- `answer` contains the synthesized answer when answer generation succeeds.
- `results[0].content` contains the same synthesis plus web/scientific context and sources.
- `raw_content` contains fuller extracted source text where available.

## `GET /search`

GET wrapper around `POST /search`.

Useful for simple manual checks.

## `POST /search-summary`

Compatibility endpoint for callers that explicitly ask for search plus synthesis. Normal `/search` already performs synthesis and should be preferred for engine integrations.

## `GET /health/monitor`

Read-only operational monitor.

Returns:

- runtime counters
- provider daily usage
- provider cooldowns
- recent LLM attempt summary
- recent provider event summary

## `GET /logs/llm-attempts?limit=100`

Returns recent durable LLM attempt log rows.

No prompts, messages, raw model outputs, or API keys are logged.

## `GET /logs/provider-events?limit=100`

Returns recent provider success/failure/cooldown events.

## `GET /search-raw`

Compatibility endpoint for older integrations. It now delegates to the same intelligent one-result aggregate contract as `/search`; it does not bypass classification, extraction, or summarization.

## Automatic Science Detection

Callers no longer need to choose scientific providers.

Every normal `/search` or `/search-raw` request now behaves like this:

- Always run web search.
- Ask the classifier whether the query is science/technical/academic enough.
- If yes, also run scientific retrieval and combine the results.
- Summarize the collected material into one answer/context package.
- Return exactly one result object.

Examples:

```json
{"query":"perovskite solar cell ion migration hysteresis","max_results":1}
```

Returns web plus scientific retrieval when classifier says science.

```json
{"query":"best pizza near times square","max_results":1}
```

Returns normal web search only.

`advanced_search=true` still forces scientific retrieval for compatibility, but clients should not need it.

## Aggregate Result Contract

`/search`, `GET /search`, and `/search-raw` are engine-compatible. They return exactly one result object in `results[]`.

Internal retrieval can still fetch several sources:

- about five web pages for web context
- at least two scientific documents when the classifier chooses science retrieval and providers are available
- SearchAPI Google Scholar and SerpApi Google Scholar as paid Google Scholar gateways when configured
- additional scientific fallbacks when needed

External response shape:

```json
{
  "query": "...",
  "results": [
    {
      "title": "Searchbox research context for: <query>",
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

The engine should read the single `results[0].content` field as the complete context package.

For science queries, `content` contains:

```text
# Web Context
multiple web source sections

# Scientific Context
scientific document sections when available

# Sources
all source titles, URLs, and providers
```

For non-science queries, `content` contains the summary, web context, and sources.

`raw_content` contains fuller extracted source text when requested, and is also included by default for science-context responses.
