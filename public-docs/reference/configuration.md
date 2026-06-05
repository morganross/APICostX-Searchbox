# Configuration Reference

Searchbox is configured through environment variables.

## Rules

- Do not commit real `.env` files.
- Do not print keys from `/config`, `/health`, or logs.
- Keep provider caps aligned with account plans.
- Keep quota and cooldown files on persistent storage.

## Core

`SEARCH_API_KEY`: bearer token for Searchbox when auth is enabled.

`AUTH_DISABLED`: set `false` in public production.

`RATE_LIMIT_PER_MINUTE`: local client rate limit.

`SEARCH_PROVIDER`: selected web provider, such as `serper`, `brave`, or `searxng`.

`SEARXNG_URL`: SearXNG base URL.

`SEARXNG_RESULTS_LIMIT`: maximum SearXNG results requested internally.

## Scientific Routing

`ADVANCED_SEARCH_ENABLED`: enables scientific provider behavior.

`ADVANCED_SEARCH_DEFAULT_SOURCE`: default source for diagnostic direct advanced calls. Prefer `auto`.

`ADVANCED_SEARCH_AUTO_PROVIDER_ORDER`: comma-separated provider order.

Example:

```text
sciencestack,searchapi_scholar,serpapi_scholar,agentic_data,arxiv,oanor
```

`ADVANCED_SEARCH_AUTO_MIN_PROVIDERS`: target minimum successful scientific providers.

`ADVANCED_SEARCH_AUTO_MAX_PROVIDERS`: maximum scientific providers attempted.

## Science Classifier

`SCIENCE_CLASSIFIER_ENABLED`: enables automatic science detection.

`SCIENCE_CLASSIFIER_TIMEOUT`: timeout for one classifier attempt.

`SCIENCE_CLASSIFIER_MAX_TOTAL_SECONDS`: total classifier fallback budget.

`SCIENCE_CLASSIFIER_MAX_COMPLETION_TOKENS`: max classifier completion size.

`SCIENCE_CLASSIFIER_CONFIDENCE_THRESHOLD`: minimum confidence to run science retrieval.

## arXiv

`ARXIV_API_URL`: default `https://export.arxiv.org/api/query`.

`ARXIV_USER_AGENT`: descriptive user agent.

`ARXIV_TIMEOUT`: timeout.

`ARXIV_MAX_RESULTS`: maximum results.

`ARXIV_PDF_MAX_BYTES`: PDF fetch size cap.

`ARXIV_CONTENT_SUMMARY_THRESHOLD_CHARS`: threshold for LLM summary, commonly `5000`.

`ARXIV_PAPER_SUMMARY_MAX_SOURCE_CHARS`: maximum text sent to summarizer.

`ARXIV_MIN_INTERVAL_SECONDS`: local pacing.

`ARXIV_DAILY_REQUEST_LIMIT`: local daily cap.

`ARXIV_COOLDOWN_SECONDS`: cooldown after refusal.

## ScienceStack

`SCIENCESTACK_API_URL`: base URL.

`SCIENCESTACK_API_KEY`: key.

`SCIENCESTACK_TIMEOUT`: timeout.

`SCIENCESTACK_MAX_RESULTS`: maximum results.

`SCIENCESTACK_DAILY_REQUEST_LIMIT`: local daily cap.

## SearchAPI Scholar

`SEARCHAPI_API_URL`: default `https://www.searchapi.io/api/v1/search`.

`SEARCHAPI_API_KEY`: key.

`SEARCHAPI_TIMEOUT`: timeout.

`SEARCHAPI_MAX_RESULTS`: maximum results.

`SEARCHAPI_DAILY_REQUEST_LIMIT`: local daily cap.

## SerpApi Scholar

`SERPAPI_API_URL`: default `https://serpapi.com/search.json`.

`SERPAPI_API_KEY`: key.

`SERPAPI_TIMEOUT`: timeout.

`SERPAPI_MAX_RESULTS`: maximum results.

`SERPAPI_DAILY_REQUEST_LIMIT`: local daily cap.

`SERPAPI_MONTHLY_REQUEST_LIMIT`: local monthly cap. Example:

```text
SERPAPI_MONTHLY_REQUEST_LIMIT=250
```

## Agentic Data

`AGENTIC_DATA_ARXIV_URL`: base URL.

`AGENTIC_DATA_API_KEY`: bearer token.

`AGENTIC_DATA_TIMEOUT`: timeout.

`AGENTIC_DATA_MAX_RESULTS`: maximum results.

`AGENTIC_DATA_DAILY_REQUEST_LIMIT`: local daily cap.

## Oanor

`OANOR_ARXIV_API_URL`: base URL.

`OANOR_API_KEY`: key.

`OANOR_TIMEOUT`: timeout.

`OANOR_MAX_RESULTS`: maximum results.

`OANOR_DAILY_REQUEST_LIMIT`: local daily cap.

## Quota and Cooldown Files

`ADVANCED_PROVIDER_QUOTA_FILE`: daily usage JSON path.

`ADVANCED_PROVIDER_MONTHLY_QUOTA_FILE`: monthly usage JSON path.

`ADVANCED_PROVIDER_COOLDOWN_FILE`: provider cooldown JSON path.

`ADVANCED_PROVIDER_COOLDOWN_MAX_SECONDS`: maximum cooldown.

## Logging

`SEARCHBOX_LOG_DIR`: log directory.

`LLM_ATTEMPT_LOG_FILE`: LLM attempt JSONL file.

`PROVIDER_EVENT_LOG_FILE`: provider event JSONL file.

`SEARCHBOX_LOG_API_MAX_LINES`: max lines returned by log APIs.
