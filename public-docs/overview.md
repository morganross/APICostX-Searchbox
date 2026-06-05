# Overview

Searchbox is a retrieval gateway. It sits between clients and information providers, then returns context in a shape that agents and research engines can use directly.

## Core Use Cases

Searchbox is useful when you want to:

- provide a Tavily-like search API from your own service
- combine web search with scientific search
- add Google Scholar-style providers to engines that only understand web search
- fetch and extract text from papers, PDFs, and article pages
- summarize long scientific documents
- enforce local daily and monthly caps for paid providers
- observe provider failures and LLM failures through durable logs
- return one complete context package to a downstream engine

## Why Searchbox Exists

Many research engines support web search but do not cleanly support specialized retrievers. Even when they support custom tools, each engine may expect a different result shape. Searchbox puts retriever-specific complexity behind one API.

The engine asks a query. Searchbox decides how much retrieval is appropriate.

## Design Principles

### One public search endpoint

The public surface should be simple. Most clients should call `/search` and should not choose providers directly.

### Automatic science retrieval

Scientific retrieval should happen because the query needs it, not because the caller knows a special flag.

### Web plus science

Science-like queries still benefit from web context. Publisher pages, lab pages, standards, documentation, news, and institutional pages often matter.

### Internal fanout, external simplicity

Searchbox may call multiple providers internally, but the response should be easy for a research engine to consume.

### Quotas are behavior

Provider limits should be enforced in code, persisted across restarts, and visible through health/config endpoints.

### Failure is normal

Provider failures, cooldowns, empty results, blocked extraction, and LLM fallback failures are normal operational states. Searchbox should make them explainable.

### Secrets stay secret

Keys live in environment variables or secret managers. Public endpoints and logs must not reveal them.

## Non-Goals

Searchbox is not:

- a fully autonomous research agent
- a vector database
- a permanent document archive
- a guarantee that every result URL can be extracted
- a way to bypass provider terms, paywalls, access controls, or rate limits
- a substitute for domain expertise
