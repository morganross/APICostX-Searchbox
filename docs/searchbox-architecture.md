# Searchbox Architecture

Searchbox is a FastAPI service in `/home/ubuntu/APICostX-Searchbox/main.py`.

## Runtime

```text
systemd unit: /etc/systemd/system/searchbox.service
working dir: /home/ubuntu/APICostX-Searchbox
env file: /home/ubuntu/APICostX-Searchbox/.env
command: /home/ubuntu/APICostX-Searchbox/venv/bin/uvicorn main:app --host 0.0.0.0 --port 9000
```

## Request Flow

Normal search:

```text
client -> /search -> web provider -> Tavily-compatible response
```

Science-capable search:

```text
client -> /search -> web provider
                  -> automatic scientific provider chain
                  -> content extraction / paper full text
                  -> LLM summary when raw text > 5,000 chars
                  -> combined Tavily-compatible response
```

The public goal is a single search API. Users should not need to know provider names. Internally, the scientific chain can still call specific sources.

## Important Concepts

`content`:

- Short display field.
- For long scientific documents, this is an LLM summary.
- Current summary threshold is `ARXIV_CONTENT_SUMMARY_THRESHOLD_CHARS`, default `5000`.

`raw_content`:

- Full extracted document text when available.
- For papers, this is the desired raw extraction field.

Provider quota:

- Daily counters are persisted in JSON.
- Monthly counters are persisted in JSON for providers with monthly plans, currently SerpApi Google Scholar.
- Calls are reserved before external provider requests.

Provider cooldown:

- Failures such as `402`, `429`, `502`, `503`, and `504` trigger local cooldown.
- Cooldowns are persistent, not in-memory only.

LLM orchestration:

- Uses existing LiteLLM/OpenRouter settings.
- Free/default models are tried first.
- GPT-5 mini fallback is allowed only if configured by `LLM_ALLOW_EXPENSIVE_FALLBACK=true`.

## Science Classifier

Searchbox now has a single user-facing search behavior: callers do not need to set `advanced_search` to get scientific retrieval.

Runtime behavior:

```text
/search request
  -> web search always
  -> LLM science classifier
  -> if science-related, run scientific auto provider chain
  -> combine web + scientific results
```

Compatibility note:

- `advanced_search=true` is still accepted as a force-science override for older callers.
- `advanced_search=false` or omitted does not suppress science classification.

Classifier settings:

```text
SCIENCE_CLASSIFIER_ENABLED=true
SCIENCE_CLASSIFIER_TIMEOUT=8
SCIENCE_CLASSIFIER_MAX_TOTAL_SECONDS=15
SCIENCE_CLASSIFIER_MAX_COMPLETION_TOKENS=1024
SCIENCE_CLASSIFIER_CONFIDENCE_THRESHOLD=0.55
```

The classifier uses the existing LiteLLM/OpenRouter model chain: configured default/free models first, then configured fallbacks, including GPT-5 mini when allowed.

Classifier attempts are logged with:

```text
purpose=science_classifier
```

## One-Result Context Packaging

Searchbox internally fans out to multiple sources, but returns one aggregate result object to engines.

Reason:

- GPTR, DR, AIQ, MS Agents, and OWL-like engines should not have to reliably iterate and merge many `results[i].content` fields.
- A single context field is safer: engines ask a query and get one content package back.

Current packaging:

```text
results[0].title = Searchbox research context for: <query>
results[0].url = first HTTP(S) source URL when available
results[0].searchbox_url = searchbox://aggregate/<request_id>
results[0].aggregate_url = searchbox://aggregate/<request_id>
results[0].content = web + science context package
results[0].raw_content = fuller raw extracted source text when available/requested
```

Internal target counts:

```text
web context sources: SEARCHBOX_WEB_CONTEXT_RESULTS, default 5
science context sources: at least ADVANCED_SEARCH_AUTO_MIN_PROVIDERS, default 2, when providers are available
```


Scientific auto provider order currently defaults to:

```text
sciencestack,searchapi_scholar,serpapi_scholar,agentic_data,arxiv,oanor
```
