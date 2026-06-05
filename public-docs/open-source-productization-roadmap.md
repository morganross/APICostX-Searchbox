# From Weekend Project To Open Source Software

Searchbox already has the core product idea: one search API that can combine web search, scientific retrieval, document extraction, long-document summarization, quota enforcement, cooldowns, logs, and an engine-friendly aggregate response.

Before it is fit for public open-source release, it needs a productization pass. The codebase is small, so the problem is not code volume. The work is turning a service that works in one environment into software that strangers can clone, run, inspect, trust, test, and contribute to.

## Intended Release Shape

Searchbox should be released first as a self-hosted Python service.

Primary assumptions:

- Self-hosted by the user.
- No mandatory container.
- No mandatory auth for local/private deployments.
- Simple `uvicorn` or systemd-style operation.
- Docker may be added later as an optional convenience, not the primary install path.

Default public documentation should make clear that `AUTH_DISABLED=true` is convenient for local/private use. If a user exposes Searchbox to the public internet, they should enable auth and understand the risk.

## What Has To Change

### 1. Repository Hygiene

The public repo needs the standard open-source furniture:

- `README.md`
- `LICENSE`
- `CONTRIBUTING.md`
- `SECURITY.md`
- `CODE_OF_CONDUCT.md`
- `.env.example`
- `requirements.txt` or `pyproject.toml`
- `.gitignore`
- GitHub issue templates
- GitHub pull request template
- GitHub Actions workflows
- changelog or release notes policy

These files are not ceremony. They tell users whether the project is serious, installable, supportable, and safe to try.

### 2. Dependency Cleanup

Public users need one command that works.

Searchbox should move from "whatever is installed in the current virtualenv" to a real dependency declaration.

Preferred direction:

- `pyproject.toml` for package metadata and dependency groups.
- Python version declared, probably `>=3.11`.
- Runtime dependencies separated from development dependencies.
- Dependency versions pinned or bounded enough to avoid surprise breakage.
- No hidden system dependency surprises.

If we keep `requirements.txt`, it should still be generated or maintained deliberately.

### 3. Configuration Hardening

The project needs a complete `.env.example` with every supported setting documented.

Startup behavior should be clear:

- missing optional providers should not crash the service
- missing required runtime settings should fail with readable errors
- `/config` should report non-secret status
- no endpoint should reveal API keys

Configuration should be grouped by purpose:

- core service settings
- web search providers
- scientific providers
- LLM classifier/summarizer
- quotas
- cooldowns
- logs
- extraction/security

### 4. Code Refactor

The service is currently small, but `main.py` does too much. The goal is not a grand rewrite. The goal is clean boundaries.

Natural module split:

```text
searchbox/
  app.py                  # FastAPI app and route registration
  models.py               # request and response models
  config.py               # environment loading and validation
  aggregation.py          # one-result context package builder
  quota.py                # daily and monthly quota persistence
  cooldowns.py            # provider cooldown persistence
  logging_utils.py        # JSONL logs and redaction helpers
  security.py             # auth, URL/IP safety, fetch restrictions
  extraction/
    html.py               # HTML extraction
    pdf.py                # PDF extraction
    core.py               # shared extraction interface
  llm/
    classifier.py         # science query classifier
    summarizer.py         # long document summarizer
    client.py             # LiteLLM/OpenRouter calls
  providers/
    base.py               # provider interface
    web_serper.py
    web_brave.py
    searxng.py
    arxiv.py
    sciencestack.py
    searchapi_scholar.py
    serpapi_scholar.py
    agentic_data.py
    oanor.py
```

This should be done after tests exist around current behavior, so refactoring does not accidentally break the important weird edges we learned the hard way.

### 5. Testing

This is the biggest credibility jump.

Searchbox needs tests for:

- request model validation
- provider response parsers
- malformed provider responses
- missing provider keys
- daily quota enforcement
- monthly quota enforcement, especially SerpApi
- provider cooldown behavior
- classifier fallback behavior with mocked LLMs
- long-document summarization path with mocked LLMs
- aggregate one-result response contract
- failed provider fallback in auto mode
- `/config` never leaking secrets
- logs never containing secrets
- private IP / SSRF blocking
- extraction failures
- PDF size limits

Live paid-provider tests should exist, but must be opt-in. Public CI should not burn SerpApi, SearchAPI, ScienceStack, or other paid credits.

### 6. GitHub Actions

Minimum useful CI:

- format check
- lint
- unit tests
- type check if feasible
- secret scanning
- dependency vulnerability scan

Likely tools:

- `ruff` for linting and formatting
- `pytest` for tests
- `mypy` or `pyright` for type checking if we commit to typing
- `pip-audit` for Python dependency vulnerabilities
- GitHub Dependabot
- GitHub CodeQL
- Gitleaks or TruffleHog for secret scanning

CI should run on pull requests and pushes to the main branch.

### 7. Security Posture

Searchbox fetches URLs and handles provider keys, so security needs to be explicit.

The public docs and tests should be able to say:

- API keys come from environment variables
- keys are never returned by `/health`, `/config`, or log endpoints
- auth can be disabled for local/private self-hosting
- auth should be enabled for public internet exposure
- private IP fetch blocking exists
- redirects are capped
- timeouts are enforced
- response size limits exist
- log endpoints are protected when auth is enabled
- provider terms and rate limits are respected

The SSRF story matters because Searchbox may fetch URLs returned by providers or influenced by user queries.

### 8. Provider Abstraction

Provider code should become boring.

A clean provider interface might expose:

```text
Provider.name
Provider.kind
Provider.requires_key
Provider.daily_limit
Provider.monthly_limit
Provider.search(request) -> list[SearchItem]
```

Each provider should be responsible for:

- auth headers or params
- provider-specific request params
- response parsing
- URL selection
- metadata normalization

Shared infrastructure should handle:

- quota reservation
- cooldown decisions
- logging
- extraction
- scoring
- aggregation

Adding a provider should feel like filling in a known adapter shape, not spelunking through the entire application.

### 9. Public Install Story

The primary install story should be non-container self-hosting:

```bash
git clone <repo>
cd searchbox
python3 -m venv venv
. venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --host 127.0.0.1 --port 9000
```

A systemd example is useful for users running Searchbox on a VPS.

Docker can be added later as optional, but it should not be required for the first public release.

### 10. Examples That Actually Run

The repo should include working examples:

- local web-only mode with SearXNG
- paid web mode with Serper
- arXiv-only science mode
- SerpApi Scholar mode
- SearchAPI Scholar mode
- Python client
- JavaScript client
- curl examples
- GPT Researcher / deep research engine integration pattern

Examples should avoid real keys and should not require paid providers unless clearly marked.

### 11. Versioning And Releases

Public users need release boundaries.

Searchbox should use:

- semantic versioning
- GitHub releases
- changelog
- migration notes for breaking env var or response contract changes

Even if the project is young, versioning gives users something stable to pin.

### 12. License Choice

We need to choose the license intentionally.

Likely options:

- MIT: maximum adoption and simplicity
- Apache-2.0: permissive, with patent language
- AGPL: forces hosted modifications to remain open

If the goal is broad adoption, MIT or Apache-2.0 is the likely choice. If the goal is preventing cloud wrappers from closing improvements, AGPL is the stronger choice.

## Recommended Refactor Path

Do not refactor everything first. Stabilize current behavior first.

Recommended order:

1. Add public repo files and `.env.example`.
2. Add tests around current behavior.
3. Add CI.
4. Split config and models out of `main.py`.
5. Add provider interface.
6. Move provider adapters into `providers/`.
7. Split extraction, quota, cooldown, logging, and aggregation modules.
8. Add systemd/self-host install docs.
9. Add optional Docker only if we want it.
10. Run security and secret-leak tests.
11. Polish public docs against the final structure.

This keeps us from breaking working behavior while making the codebase more professional.

## The Product Already Exists

The weekend-project smell is real, but the actual product is already there:

- one search API
- automatic science routing
- web plus scientific retrieval
- provider fanout
- PDF and HTML extraction
- long-document summarization
- daily and monthly caps
- provider cooldowns
- durable logs
- health and monitor endpoints
- one-result engine-facing context package

The open-source work is to make it boring, testable, installable, safe, and understandable for people who were not here while it was built.
