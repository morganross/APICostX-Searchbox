# LLM Logging and Health Monitor

Searchbox now has durable structured logs for LLM attempts and provider events.

## Log Files

```text
/home/ubuntu/APICostX-Searchbox/logs/llm_attempts.jsonl
/home/ubuntu/APICostX-Searchbox/logs/provider_events.jsonl
```

Configured by:

```text
SEARCHBOX_LOG_DIR
LLM_ATTEMPT_LOG_FILE
PROVIDER_EVENT_LOG_FILE
SEARCHBOX_LOG_API_MAX_LINES
```

## LLM Attempt Log

Each model attempt writes one JSON row.

Fields include:

```text
timestamp
event_type
purpose
request_id
provider
model
role
success
failure_type
reasons
latency_ms
finish_reason
usage
```

Current `purpose` values:

```text
search_summary
paper_summary
```

Planned next purpose:

```text
science_classifier
```

Never logged:

```text
prompts
messages
raw model output
API keys
```

## Provider Event Log

Provider events include:

```text
timestamp
event_type
provider
event
success
status_code
reason
retry_after_seconds
failure_count
```

## API Endpoints

```text
GET /health/monitor
GET /logs/llm-attempts?limit=100
GET /logs/provider-events?limit=100
```

`/health/monitor` aggregates recent logs and reports live runtime counters, provider daily usage, and provider cooldowns.

## Why This Exists

The free LLMs may fail silently or intermittently. These logs let us answer questions like:

- Are free models failing often?
- Which model is failing?
- Is GPT-5 mini carrying the workload?
- Are failures validation errors, missing keys, timeouts, malformed JSON, or provider errors?
- Which providers are cooling down and why?

## Reading Logs Manually

```bash
tail -n 50 /home/ubuntu/APICostX-Searchbox/logs/llm_attempts.jsonl
tail -n 50 /home/ubuntu/APICostX-Searchbox/logs/provider_events.jsonl
```
