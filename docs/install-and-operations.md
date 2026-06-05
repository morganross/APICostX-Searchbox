# Install and Operations

## Host

```text
host: ubuntu@163.192.42.2
hostname: searchbox
repo: /home/ubuntu/APICostX-Searchbox
service: searchbox.service
port: 9000
```

Always verify host identity before production work:

```bash
hostname
whoami
pwd
hostname -I
```

Expected:

```text
searchbox
ubuntu
/home/ubuntu
10.0.1.209 10.0.2.31
```

## Service

```bash
sudo systemctl status searchbox.service
sudo systemctl restart searchbox.service
journalctl -u searchbox.service -n 200 --no-pager
```

Unit file:

```text
/etc/systemd/system/searchbox.service
```

Exec command:

```text
/home/ubuntu/APICostX-Searchbox/venv/bin/uvicorn main:app --host 0.0.0.0 --port 9000
```

## Environment

Env file:

```text
/home/ubuntu/APICostX-Searchbox/.env
```

Secret-containing values stay in `.env`; do not print key values in logs or docs.

Important env groups:

Web providers:

```text
SEARCH_PROVIDER
SERPER_API_KEY
TAVILY_API_KEY
```

LLM:

```text
SUMMARIZER_ENABLED
OPENROUTER_API_KEY
LLM_MODEL
LLM_FALLBACK_MODELS
LLM_ALLOW_EXPENSIVE_FALLBACK
```

Scientific providers:

```text
AGENTIC_DATA_API_KEY
SCIENCESTACK_API_KEY
OANOR_API_KEY
SEARCHAPI_API_KEY
```

Daily limits and state:

```text
ADVANCED_PROVIDER_QUOTA_FILE
ADVANCED_PROVIDER_COOLDOWN_FILE
```

Logs:

```text
SEARCHBOX_LOG_DIR
LLM_ATTEMPT_LOG_FILE
PROVIDER_EVENT_LOG_FILE
```

## Code Checks

Before restart after a code edit:

```bash
cd /home/ubuntu/APICostX-Searchbox
./venv/bin/python -m py_compile main.py
```

Health check:

```bash
curl -sS http://127.0.0.1:9000/health
curl -sS http://127.0.0.1:9000/config
curl -sS http://127.0.0.1:9000/health/monitor
```

## Testing Discipline

Use one targeted live provider test unless explicitly asked for more. Provider calls consume daily quota and can trigger cooldowns.

For non-provider validation, prefer:

```text
/health
/config
/health/monitor
/logs/*
```

## Copying Docs to Private Docs Repo

Private docs repo on frontend:

```text
ubuntu@150.230.40.142:/home/ubuntu/APICostX.com-PRIVATE-docs
```

Searchbox docs should be copied under:

```text
/home/ubuntu/APICostX.com-PRIVATE-docs/searchbox
```
