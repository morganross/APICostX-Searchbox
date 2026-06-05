# Searchbox Public Documentation

Searchbox is a standalone retrieval service for agents, deep research engines, and applications that need useful context from web search, scientific search, document APIs, and extracted full text.

This folder is the public documentation set for the open-source Searchbox project. It is separate from internal operator notes and should not contain private hostnames, private IPs, account-specific details, or secrets.

## What Searchbox Does

Searchbox exposes a small search API. A caller sends a query. Searchbox can run web search, classify whether the query is science-like, call scientific providers, extract document text, summarize long documents, enforce provider quotas, and return one context package that downstream engines can consume.

The simplest path is:

```text
client -> /search -> web provider -> response
```

For scientific or technical queries, Searchbox can use:

```text
client -> /search
       -> web search
       -> science classifier
       -> scientific provider chain
       -> PDF / HTML extraction
       -> LLM summary for long documents
       -> one aggregate result
```

## Documentation Map

- [Overview](overview.md): goals, design principles, and non-goals.
- [Quickstart](quickstart.md): local setup and first requests.
- [Configuration](reference/configuration.md): environment variables and runtime behavior.
- [API Reference](reference/api.md): endpoints, request fields, response contracts.
- [Providers](providers/README.md): web and scientific provider guides.
- [Architecture](architecture/README.md): request flow, aggregation, extraction, quotas.
- [Operations](operations/README.md): logs, health, cooldowns, troubleshooting.
- [Systemd Self-Hosting](operations/systemd.md): run Searchbox as a normal Linux service without Docker.
- [Security](security.md): auth, secrets, logs, and network fetch safety.
- [Contributing](contributing.md): how to add providers and improve Searchbox.
- [Open Source Productization Roadmap](open-source-productization-roadmap.md): what must change before public release.
- [Main File Refactor Plan](main-file-refactor-plan.md): phased plan for breaking up `main.py` into a real package.
- [Examples](examples/README.md): curl, Python, JavaScript, and engine integration.

## Public Contract

The recommended integration is `POST /search`.

Downstream engines should read:

```text
response.results[0].content
```

as the complete context package. Searchbox may call several providers internally, but it returns a single engine-friendly aggregate result so integrations do not need to merge scattered provider records.

## Documentation Philosophy

Searchbox is small enough that most confusion will not come from code volume. It will come from provider behavior, quotas, throttling, extraction failures, LLM fallback behavior, and downstream engine assumptions.

The docs are intentionally large. They should make the product understandable without requiring someone to reverse-engineer the source.
