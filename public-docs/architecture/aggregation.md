# Aggregation

Aggregation is the process of turning many internal retrieval results and the generated synthesis into one context package.

## Why

Research engines often fail to merge many search results correctly. Some read only one item. Searchbox avoids that by returning one primary result.

## Response

```text
results[0].title = Searchbox research context for: <query>
results[0].url = first HTTP(S) source URL when available
results[0].searchbox_url = searchbox://aggregate/<request_id>
results[0].aggregate_url = searchbox://aggregate/<request_id>
results[0].content = summary plus complete context
```

## Sections

Responses include a Summary section plus source context. Science-like responses may include:

- Web Context
- Scientific Context
- Sources
- Notes or caveats

Non-science responses include the Summary section, web context, and sources.

## Limits

Aggregation should respect configured content and raw-content caps so payloads stay bounded.
