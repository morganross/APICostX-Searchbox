# Logging

Searchbox logs provider and LLM behavior so operators can debug failures later.

## LLM Attempt Logs

Should include purpose, model, provider, success, duration, and error class.

Should not include keys, raw prompts, or raw model outputs.

## Provider Event Logs

Should include provider, event, success, status code, failure reason, retry-after, and cooldown information.

## API

```text
GET /logs/llm-attempts?limit=100
GET /logs/provider-events?limit=100
```

Protect these endpoints in public deployments.
