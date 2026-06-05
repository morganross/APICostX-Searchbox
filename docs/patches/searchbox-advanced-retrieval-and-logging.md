# Searchbox Advanced Retrieval and Logging Patch Notes

This document records the recent Searchbox changes for advanced scientific retrieval and observability.

## Query Preservation

Removed the arXiv query compiler behavior that rewrote user terms into `all:term AND all:term` expressions.

Current behavior:

- Preserve the literal user query.
- Normalize whitespace only.

## arXiv PDF Extraction

- Advanced arXiv results always fetch PDF text.
- PDF extraction now reads all pages instead of only the first 10 pages.
- `raw_content` stores extracted PDF text.
- `content` is raw text only when the extracted text is <= 5,000 chars.
- Longer text is summarized by the LLM and placed in `content`.

## Scientific Provider Adapters

Added adapters:

```text
arxiv
agentic_data
sciencestack
oanor
searchapi_scholar
```

Working in live tests:

```text
sciencestack
searchapi_scholar
```

Reachable but currently blocked/failing upstream:

```text
agentic_data -> 503
oanor -> 402
arxiv -> intermittent 429/capacity/refusal
```

## Automatic Provider Chain

Added internal auto mode:

```text
sciencestack,searchapi_scholar,agentic_data,arxiv,oanor
```

The auto chain tries for at least two scientific providers when possible and falls back through the rest.

## Web Plus Scientific Search

Advanced behavior was changed from either web or science to web plus science.

Current product direction:

- Remove user-facing `advanced_search` flag.
- Run web search for every request.
- Add an LLM query classifier.
- If the query is science-related, also run the scientific auto chain.

## Daily Caps

Added persistent daily caps per provider.

State:

```text
/home/ubuntu/APICostX-Searchbox/data/advanced_provider_daily_usage.json
```

## Cooldowns

Added persistent provider cooldowns.

State:

```text
/home/ubuntu/APICostX-Searchbox/data/advanced_provider_cooldowns.json
```

## Observability

Added durable JSONL logs:

```text
/home/ubuntu/APICostX-Searchbox/logs/llm_attempts.jsonl
/home/ubuntu/APICostX-Searchbox/logs/provider_events.jsonl
```

Added API endpoints:

```text
GET /health/monitor
GET /logs/llm-attempts
GET /logs/provider-events
```

## Next Planned Patch

Science classifier:

- Remove the public `advanced_search` decision from callers.
- Use existing LLM fallback path to classify whether a query is scientific.
- Always run web search.
- Run scientific auto providers when classifier says the query is science-related.
- Log classifier attempts with `purpose=science_classifier`.

## Science Classifier Patch

Implemented automatic science-query detection.

- User-facing callers no longer need to set `advanced_search`.
- `/search` always performs web search.
- A lightweight LLM classifier decides whether to add scientific retrieval.
- `advanced_search=true` remains as a compatibility force-science override.
- `advanced_search=false` or omitted no longer disables science classification.
- Classifier uses the same configured LLM/fallback chain as summaries.
- Classifier attempts are logged as `purpose=science_classifier`.

Live verification:

```text
query: perovskite solar cell ion migration hysteresis
provider: web+advanced:auto
result: web + scientific result
```

```text
query: best pizza near times square
provider: serper
result: web only
```

## Aggregate Result Contract Patch

Changed `/search` response packaging from multiple result rows to one aggregate context result.

Before:

```text
results[0] = web result
results[1] = scientific result
...
```

After:

```text
results[0] = one Searchbox aggregate result containing web context, scientific context, and sources
```

Live verification:

```text
science query: perovskite solar cell ion migration hysteresis
provider: web+advanced:auto
RESULT_COUNT: 1
content includes web context and scientific context
```

```text
ordinary query: best pizza near times square
provider: serper
RESULT_COUNT: 1
content includes web context only
```
