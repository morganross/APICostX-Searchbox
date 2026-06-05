# Provider Guide

Searchbox supports web providers and scientific providers.

## Web Providers

Web providers handle normal search and supply baseline context for science-like queries.

Examples:

- Serper
- Brave Search
- SearXNG

## Scientific Providers

Scientific providers handle academic, scholarly, and technical retrieval.

Examples:

- ScienceStack
- SearchAPI Google Scholar
- SerpApi Google Scholar
- arXiv Export API
- Agentic Data / DeepXiv style APIs
- Oanor

## Provider Selection

Normal clients should not choose providers directly. They should call `/search`.

Direct provider selection is for diagnostics, tests, and adapter development.

## Auto Provider Order

Example:

```text
sciencestack,searchapi_scholar,serpapi_scholar,agentic_data,arxiv,oanor
```

Provider order should consider reliability, coverage, extraction quality, latency, quota, and cost.

## Failure Model

Provider failures are expected. Searchbox should log them, cool down unhealthy providers, and continue with fallbacks in auto mode.

Common failures:

- missing key
- quota exhausted
- upstream 429
- upstream 503
- account inactive
- timeout
- empty result
- extraction blocked

See [Scientific Providers](scientific.md), [Web Providers](web.md), and [Adding a Provider](adding-a-provider.md).
