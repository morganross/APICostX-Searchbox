# Searchbox

<p align="center">
  <strong>Self-hosted retrieval for web search, scientific search, document extraction, and agent-ready context.</strong>
</p>

<p align="center">
  <a href="https://github.com/morganross/APICostX-Searchbox/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/morganross/APICostX-Searchbox/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://github.com/morganross/APICostX-Searchbox/actions/workflows/codeql.yml"><img alt="CodeQL" src="https://github.com/morganross/APICostX-Searchbox/actions/workflows/codeql.yml/badge.svg"></a>
  <a href="https://github.com/morganross/APICostX-Searchbox/actions/workflows/secret-scan.yml"><img alt="Secret Scan" src="https://github.com/morganross/APICostX-Searchbox/actions/workflows/secret-scan.yml/badge.svg"></a>
  <a href="https://scorecard.dev/viewer/?uri=github.com/morganross/APICostX-Searchbox"><img alt="OpenSSF Scorecard" src="https://api.securityscorecards.dev/projects/github.com/morganross/APICostX-Searchbox/badge"></a>
  <img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11%2B-blue">
  <a href="LICENSE"><img alt="License: Apache-2.0" src="https://img.shields.io/badge/license-Apache--2.0-blue"></a>
</p>

Searchbox is a self-hosted retrieval gateway for agents, research engines, and applications that need useful context from web search, scientific search, document APIs, and extracted full text.

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
git clone https://github.com/morganross/APICostX-Searchbox.git
cd APICostX-Searchbox
python3 -m venv venv
. venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --host 127.0.0.1 --port 9000
```

Then:

```bash
curl -sS http://127.0.0.1:9000/health
```

Search:

```bash
curl -sS http://127.0.0.1:9000/search   -H 'content-type: application/json'   -d '{"query":"lithium dendrite solid electrolyte interface","max_results":1}'
```

## Response Contract

Searchbox may call several providers internally, but the recommended integration contract is intentionally simple:

```python
context = response["results"][0]["content"]
```

The first result is a Searchbox aggregate context package. It may include web context, scientific context, extracted text summaries, and source listings.

## Configuration

Start with `.env.example` and set only the providers you need. The one-result contract requires the summarizer path, so set `SUMMARIZER_ENABLED=true` and configure an LLM key for production-quality answers.

For local/private self-hosting, the convenient default is:

```text
AUTH_DISABLED=true
```

If Searchbox is exposed outside a trusted private network, enable auth:

```text
AUTH_DISABLED=false
SEARCH_API_KEY=<strong random token>
```

## Documentation

Public documentation lives in [`public-docs/`](public-docs/README.md).

Start with:

- [Overview](public-docs/overview.md)
- [Quickstart](public-docs/quickstart.md)
- [API Reference](public-docs/reference/api.md)
- [Configuration Reference](public-docs/reference/configuration.md)
- [Provider Guide](public-docs/providers/README.md)
- [Systemd Self-Hosting](public-docs/operations/systemd.md)
- [Open Source Productization Roadmap](public-docs/open-source-productization-roadmap.md)
- [Main File Refactor Plan](public-docs/main-file-refactor-plan.md)

## Project Health

Searchbox uses the normal public-repo checks people expect from a serious Python service:

- GitHub Actions CI on supported Python versions
- Ruff linting
- Pytest test suite
- CodeQL security analysis
- Gitleaks secret scanning
- OpenSSF Scorecard workflow
- Dependabot update checks
- Community health files: contributing, security, code of conduct, issue templates, and PR template

## Development

```bash
python3 -m venv venv
. venv/bin/activate
pip install -r requirements-dev.txt
pytest
ruff check .
python -m py_compile main.py check_keys.py
```

## Status

Searchbox is early open-source software. The service works, but the internals are still being refactored from a compact prototype into a cleaner package structure. Public API behavior and provider contracts should be protected by tests before large internal moves.

## License

Apache-2.0. See [LICENSE](LICENSE).


## Transitional Import Path

During the refactor both import paths are expected to work:

```bash
uvicorn main:app
uvicorn searchbox.app:app
```

The `searchbox.app:app` path currently bridges to the legacy top-level app until the route layer moves into the package.
