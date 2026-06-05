# Scientific Providers

Scientific providers are used for science, engineering, medical, technical, and academic queries.

## ScienceStack

Structured scientific paper discovery and content retrieval.

Typical config:

```text
SCIENCESTACK_API_KEY=<key>
SCIENCESTACK_API_URL=https://sciencestack.ai/api/v1
SCIENCESTACK_DAILY_REQUEST_LIMIT=100
```

## SearchAPI Google Scholar

Google Scholar discovery through SearchAPI.

Typical config:

```text
SEARCHAPI_API_KEY=<key>
SEARCHAPI_API_URL=https://www.searchapi.io/api/v1/search
SEARCHAPI_DAILY_REQUEST_LIMIT=100
```

Searchbox calls `engine=google_scholar`, reads `organic_results`, prefers resource links, and extracts selected URLs.

## SerpApi Google Scholar

Google Scholar discovery through SerpApi.

Typical config:

```text
SERPAPI_API_KEY=<key>
SERPAPI_API_URL=https://serpapi.com/search.json
SERPAPI_DAILY_REQUEST_LIMIT=250
SERPAPI_MONTHLY_REQUEST_LIMIT=250
```

Searchbox calls `engine=google_scholar`, reads `organic_results`, prefers `resources[]` links, enforces local monthly quota, and extracts selected URLs.

## arXiv

Free official arXiv API.

Typical config:

```text
ARXIV_API_URL=https://export.arxiv.org/api/query
ARXIV_MIN_INTERVAL_SECONDS=3.2
ARXIV_DAILY_REQUEST_LIMIT=28800
```

Searchbox preserves query terms, respects pacing, downloads PDFs within limits, and extracts text.

## Agentic Data / DeepXiv Style APIs

Provider-specific retrieval APIs for arXiv or similar corpora.

Typical config:

```text
AGENTIC_DATA_API_KEY=<key>
AGENTIC_DATA_ARXIV_URL=<base-url>
AGENTIC_DATA_DAILY_REQUEST_LIMIT=10000
```

## Oanor

Paid arXiv gateway.

Typical config:

```text
OANOR_API_KEY=<key>
OANOR_ARXIV_API_URL=https://api.oanor.com/arxiv-api
OANOR_DAILY_REQUEST_LIMIT=3
```

## Query Handling

Do not mangle user queries unless a provider requires a specific syntax. Scholar-style providers often perform better with natural keyword strings than forced boolean queries.
