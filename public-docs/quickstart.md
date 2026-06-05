# Quickstart

This guide gets Searchbox running locally.

## Requirements

- Python 3.11 or newer
- network access to your selected providers
- at least one web provider or SearXNG instance
- optional LLM provider for science classification and summaries
- optional scientific provider keys

## Clone

```bash
git clone https://github.com/your-org/searchbox.git
cd searchbox
```

Replace the URL once the public repository is published.

## Install

```bash
python3 -m venv venv
. venv/bin/activate
pip install -r requirements.txt
```

If the repository does not yet include `requirements.txt`, add one before public release. Public users should not have to infer dependencies from import errors.

## Configure

Create `.env` from the example file when available:

```bash
cp .env.example .env
```

Minimum web-search example:

```text
SEARCH_PROVIDER=searxng
SEARXNG_URL=http://127.0.0.1:8080
```

Paid web provider example:

```text
SEARCH_PROVIDER=serper
SERPER_API_KEY=your_key
```

Scientific provider examples:

```text
SCIENCESTACK_API_KEY=your_key
SEARCHAPI_API_KEY=your_key
SERPAPI_API_KEY=your_key
SERPAPI_MONTHLY_REQUEST_LIMIT=250
```

## Run

```bash
uvicorn main:app --host 127.0.0.1 --port 9000 --reload
```

## Check Health

```bash
curl -sS http://127.0.0.1:9000/health
```

## First Search

```bash
curl -sS http://127.0.0.1:9000/search \
  -H 'content-type: application/json' \
  -d '{"query":"lithium dendrite solid electrolyte interface","max_results":1}'
```

The recommended client behavior is to read:

```text
results[0].content
```

## Monitor

```bash
curl -sS http://127.0.0.1:9000/health/monitor
```

Use this to inspect provider usage, monthly caps, cooldowns, and recent LLM/provider events.
