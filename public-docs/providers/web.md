# Web Providers

Web providers supply general internet context.

## Serper

Google-style web search API.

```text
SEARCH_PROVIDER=serper
SERPER_API_KEY=<key>
```

## Brave Search

Independent web search API.

```text
SEARCH_PROVIDER=brave
BRAVE_API_KEY=<key>
```

## SearXNG

Self-hosted metasearch.

```text
SEARCH_PROVIDER=searxng
SEARXNG_URL=http://127.0.0.1:8080
```

## Extraction

Searchbox may fetch web result URLs and extract text. Search success and extraction success are different. A provider can return a valid URL while extraction fails because of bot blocking, redirects, unsupported content types, or access controls.
