# Scientific Providers

Searchbox has provider adapters for scientific retrieval. The caller should not normally choose providers directly; the internal router chooses them.

## Auto Provider Order

Configured by `ADVANCED_SEARCH_AUTO_PROVIDER_ORDER`.

Current default:

```text
sciencestack,searchapi_scholar,serpapi_scholar,agentic_data,arxiv,oanor
```

The auto chain tries for at least two successful scientific providers when possible, then falls back through more providers if needed.

## ScienceStack

Purpose:

- Structured arXiv paper discovery and full paper Markdown.

Auth:

```text
SCIENCESTACK_API_KEY
header: x-api-key
base: SCIENCESTACK_API_URL, default https://sciencestack.ai/api/v1
```

Endpoints used:

```text
GET /search?q=<query>&limit=<n>
GET /papers/{arxivId}/content?format=markdown
```

Observed status:

- End-to-end working in live tests.
- Returns large `raw_content` and LLM summaries.

## SearchAPI Google Scholar

Purpose:

- Google Scholar discovery and PDF/HTML link retrieval.

Auth:

```text
SEARCHAPI_API_KEY
base: SEARCHAPI_API_URL, default https://www.searchapi.io/api/v1/search
```

Params used:

```text
engine=google_scholar
q=<query>
num=<n>
```

Extraction:

- Prefer `resource.link` when present.
- Fall back to main result link.
- Use Searchbox extraction for PDF/HTML.

Observed status:

- End-to-end working in live tests.

## SerpApi Google Scholar

Purpose:

- Google Scholar discovery through SerpApi, with PDF/HTML link retrieval and Searchbox content extraction.

Auth:

```text
SERPAPI_API_KEY
base: SERPAPI_API_URL, default https://serpapi.com/search.json
```

Monthly limit:

```text
SERPAPI_MONTHLY_REQUEST_LIMIT=250
```

Params used:

```text
engine=google_scholar
q=<query>
num=<n>
```

Extraction:

- Prefer `resources[].link` when present, especially PDF resources.
- Fall back to the main result link.
- Use Searchbox extraction for PDF/HTML.
- If extracted text exceeds 5,000 characters, send the full text through the configured LLM summary path and keep fuller text in `raw_content` for science responses.

Observed status:

- End-to-end working in live tests.
- Test query `lithium dendrite solid electrolyte interface` returned a Google Scholar result, fetched article text, extracted about 74k characters, and used the LLM summary path.

## Agentic Data / DeepXiv

Purpose:

- arXiv/PMC retrieval and raw full text.

Auth:

```text
AGENTIC_DATA_API_KEY
Authorization: Bearer <key>
base: AGENTIC_DATA_ARXIV_URL, default https://data.rag.ac.cn/arxiv/
```

Endpoints used:

```text
type=retrieve
source=arxiv
type=raw&arxiv_id=<id>
```

Observed status:

- Adapter reaches API.
- Live retrieval returned upstream `503 Retrieval service is temporarily unavailable`.

## arXiv Export API

Purpose:

- Official arXiv search and PDF extraction.

Auth:

- No key.

Endpoint:

```text
ARXIV_API_URL=https://export.arxiv.org/api/query
```

Important behavior:

- Query string is preserved literally except whitespace normalization.
- No injected `AND`, no stopword removal, no `all:` rewriting.
- PDF extraction is non-configurable for advanced scientific arXiv results.
- Full PDF text is extracted with `pypdf`.

Observed status:

- Works when arXiv accepts requests.
- arXiv can return `429` under capacity/rate policy even when Searchbox is locally paced.

## Oanor

Purpose:

- Paid arXiv gateway.

Auth:

```text
OANOR_API_KEY
header: x-oanor-key
base: OANOR_ARXIV_API_URL, default https://api.oanor.com/arxiv-api
```

Endpoint used:

```text
GET /v1/search?q=<query>&limit=<n>
```

Observed status:

- Adapter reaches API.
- Test key returned `402`, indicating subscription/payment/account state is not currently active for successful retrieval.
