# Searchbox

Searchbox is a self-hosted retrieval service for agents, research engines, and applications that need useful context from web search, scientific search, document APIs, and extracted full text.

It exposes a Tavily-style `/search` API, but can do more than ordinary web search: automatic science detection, scientific provider fanout, PDF/HTML extraction, long-document summarization, quota enforcement, cooldowns, and durable provider/LLM logs.

## Why Searchbox

Many deep research engines can call a web search tool, but do not natively support every scientific or paid information API. Searchbox puts those retrievers behind one service.

The engine sends a query. Searchbox decides how much retrieval is useful.

```text
client -> /search -> web search -> optional science routing -> extraction -> one context package
```

Downstream engines should read:

```text
response.results[0].content
```

as the complete context package.

## Features

- Self-hosted Python service
- No mandatory container
- No mandatory auth for local/private deployments
- Tavily-compatible search response shape where practical
- Automatic science query classification
- Web plus scientific retrieval
- Scientific providers including arXiv, ScienceStack, SearchAPI Scholar, SerpApi Scholar, Agentic Data-style APIs, and Oanor
- PDF and HTML extraction
- LLM summary path for long documents
- Daily and monthly provider quotas
- Provider cooldowns
- JSONL logs for LLM attempts and provider events
- Health, config, monitor, and log API endpoints

## Quickstart

```bash
git clone https://github.com/searchbox/searchbox.git
cd searchbox
python3 -m venv venv
. venv/bin/activate
pip install -e .
cp .env.example .env
uvicorn main:app --host 127.0.0.1 --port 9000
```

Then:

```bash
curl -sS http://127.0.0.1:9000/health
```

Search:

```bash
curl -sS http://127.0.0.1:9000/search \
  -H 'content-type: application/json' \
  -d '{"query":"lithium dendrite solid electrolyte interface","max_results":1}'
```

## Documentation

Public documentation lives in [`public-docs/`](public-docs/README.md).

Start with:

- [Overview](public-docs/overview.md)
- [Quickstart](public-docs/quickstart.md)
- [API Reference](public-docs/reference/api.md)
- [Configuration Reference](public-docs/reference/configuration.md)
- [Provider Guide](public-docs/providers/README.md)
- [Open Source Productization Roadmap](public-docs/open-source-productization-roadmap.md)

## Auth Defaults

Searchbox is designed to be easy to self-host on a private machine or private network. Local/private deployments may run with:

```text
AUTH_DISABLED=true
```

If you expose Searchbox to the public internet, enable auth:

```text
AUTH_DISABLED=false
SEARCH_API_KEY=<strong random token>
```

## Status

Searchbox is early open-source software. The core service works, but the public project is still being hardened with tests, CI, packaging, and refactoring.

## License

Apache-2.0. See [LICENSE](LICENSE).
