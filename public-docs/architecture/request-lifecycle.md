# Request Lifecycle

## 1. Request

The client sends a query to `/search`.

## 2. Web Search

Searchbox always runs web search for normal context.

## 3. Science Classification

If enabled, an LLM classifies whether the query is science-like. Science-like includes academic, technical, engineering, medical, mathematical, and scientific questions.

## 4. Scientific Provider Chain

If science retrieval is needed, Searchbox tries providers in configured order. It checks cooldowns and quotas before calls.

## 5. Extraction

Searchbox fetches selected URLs and extracts HTML or PDF text when possible.

## 6. Summarization

Long extracted documents are summarized with the configured LLM path.

## 7. Aggregation

Web context, scientific context, and sources are merged into one result object.

## 8. Response

The client reads `results[0].content`.
