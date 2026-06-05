# Adding a Provider

A provider adapter should preserve the public `/search` contract while adding one new retrieval source.

## Adapter Checklist

- Accept the existing request model.
- Preserve the user's query unless transformation is required.
- Define environment variables for URL, key, timeout, max results, and limits.
- Enforce quota before external calls.
- Parse provider responses defensively.
- Prefer direct PDF/full-text links when available.
- Populate normalized result fields.
- Extract content when appropriate.
- Summarize long content through the existing summarizer.
- Add useful quality flags.
- Raise clear errors for missing config, quota, timeout, and upstream failure.
- Avoid logging secrets.

## Recommended Env Vars

```text
PROVIDER_API_URL
PROVIDER_API_KEY
PROVIDER_TIMEOUT
PROVIDER_MAX_RESULTS
PROVIDER_DAILY_REQUEST_LIMIT
PROVIDER_MONTHLY_REQUEST_LIMIT
```

Use monthly limits when the provider plan is monthly.

## Tests

Add parser fixtures, missing-key tests, quota tests, cooldown tests, and extraction failure tests. Live paid-provider tests should be opt-in.
