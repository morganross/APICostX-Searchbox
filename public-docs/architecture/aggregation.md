# Aggregation

Aggregation is the process of turning many internal retrieval results into one context package.

## Why

Research engines often fail to merge many search results correctly. Some read only one item. Searchbox avoids that by returning one primary result.

## Response

```text
results[0].title = Searchbox research context for: <query>
results[0].url = searchbox://aggregate/<request_id>
results[0].content = complete context
```

## Sections

Science-like responses may include:

- Web Context
- Scientific Context
- Sources
- Notes or caveats

Non-science responses may include only web context and sources.

## Limits

Aggregation should respect configured content and raw-content caps so payloads stay bounded.
