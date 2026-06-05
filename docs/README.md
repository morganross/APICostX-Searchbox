# Searchbox Documentation

Searchbox is the ACM retrieval gateway. It exposes a Tavily-compatible search API while hiding provider-specific details behind one service.

Current behavior:

- Normal `/search` returns regular web search results.
- `/search` with science-detected or explicitly advanced internal mode returns web results plus scientific retrieval results.
- Scientific retrieval uses an automatic provider chain rather than asking callers to choose arXiv, ScienceStack, SearchAPI, Agentic Data, or Oanor.
- Full paper text is stored in `raw_content` when available.
- If extracted paper text exceeds 5,000 characters, `content` becomes an LLM-generated summary of the full text.
- Provider daily caps and cooldowns are enforced before provider calls.
- LLM attempts and provider events are durably logged as JSONL and exposed through read-only API endpoints.

Key docs:

- [Architecture](searchbox-architecture.md)
- [API Reference](searchbox-api.md)
- [Scientific Providers](scientific-providers.md)
- [Provider Limits and Cooldowns](provider-limits-and-cooldowns.md)
- [LLM Logging and Health Monitor](llm-logging-and-health.md)
- [Install and Operations](install-and-operations.md)
- [Function and Endpoint Inventory](function-and-endpoint-inventory.md)
- [Patch Notes](patches/searchbox-advanced-retrieval-and-logging.md)
- [Testing and Quality Gates](testing-and-quality.md)

Production node:

```text
ubuntu@163.192.42.2
hostname: searchbox
repo: /home/ubuntu/APICostX-Searchbox
service: searchbox.service
port: 9000
```
