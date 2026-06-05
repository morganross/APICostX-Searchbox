# Research Engine Integration

Searchbox is designed for engines that expect a search tool.

## Recommended Use

Send the user query to `/search` and read:

```text
response.results[0].content
```

## Query Handling

Send the query plainly. Avoid adding artificial boolean operators unless the user requested them.

Good:

```text
lithium dendrite solid electrolyte interface
```

Risky:

```text
lithium AND dendrite AND solid AND electrolyte AND interface
```

## Timeouts

Science retrieval can take longer because Searchbox may call several providers, fetch PDFs, extract text, and summarize documents. Use a client timeout around 60-120 seconds for full scientific retrieval.
