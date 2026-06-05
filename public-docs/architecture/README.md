# Architecture

Searchbox is a small service with several responsibilities:

- HTTP API
- request validation
- web search
- science classification
- scientific provider routing
- content extraction
- long-document summarization
- aggregate response construction
- quota persistence
- cooldown persistence
- durable logs

## Request Flow

```text
POST /search
  -> validate request
  -> run web search
  -> classify query
  -> if science-like, run scientific provider chain
  -> extract content
  -> summarize long documents
  -> build one aggregate result
  -> return response
```

## Main Contract

Searchbox may call many providers internally, but engines should consume:

```text
results[0].content
```

as the complete context package.

## Guides

- [Request Lifecycle](request-lifecycle.md)
- [Aggregation](aggregation.md)
- [Extraction and Summarization](extraction-and-summarization.md)
- [Quotas and Cooldowns](quotas-and-cooldowns.md)
