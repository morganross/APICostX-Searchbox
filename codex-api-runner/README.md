# CodexExecAPI

CodexExecAPI is APICostX's private OpenAI-compatible bridge to the Codex CLI.
It accepts authenticated chat-completion requests, executes `codex exec`, and
returns the final response with token usage.

## Production location

The active service runs on the Searchbox host:

- Private address: `http://10.0.1.209:8765`
- Service: `codex-api-runner.service`
- Working directory: `/home/ubuntu/codex-api-runner`
- Health endpoint: `GET /health`

The ACM backend reads this address from `CODEX_EXEC_API_URL`. The service is
private and should not be exposed through public DNS.

## Files excluded from Git

Never commit these runtime files:

- `.env`, which contains the bearer token and local paths
- `.codex/auth.json`, which contains Codex authentication
- `data/jobs.sqlite`
- `data/jobs/`, which contains prompts, logs, and generated responses

The repository-level `.gitignore` excludes `.env` and all `data/` directories.

## Installation

```bash
sudo install -d -o ubuntu -g ubuntu /home/ubuntu/codex-api-runner
python3 -m venv /home/ubuntu/codex-api-runner/.venv
/home/ubuntu/codex-api-runner/.venv/bin/pip install -r requirements.txt
cp app.py requirements.txt /home/ubuntu/codex-api-runner/
cp environment.example /home/ubuntu/codex-api-runner/.env
chmod 600 /home/ubuntu/codex-api-runner/.env
```

Set a unique random `CODEX_RUNNER_TOKEN`, verify all workspace paths, and then
install the service:

```bash
sudo cp codex-api-runner.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now codex-api-runner.service
```

Do not replace or restart the production service without operator permission.

## Verification

The unauthenticated health endpoint should return `200`:

```bash
curl --fail http://10.0.1.209:8765/health
```

Authenticated endpoints require the same bearer token configured in ACM:

```bash
curl --fail \
  -H "Authorization: Bearer $CODEX_RUNNER_TOKEN" \
  http://10.0.1.209:8765/v1/models
```

The API intentionally supports non-streaming requests only. Allowed models,
sandboxes, concurrency, prompt size, and timeout behavior are defined in
`app.py` and the environment file.

## Deployment note

The service was originally deployed with Uvicorn from the Searchbox virtual
environment. The checked-in unit gives CodexExecAPI its own `.venv` so future
Searchbox dependency changes cannot silently alter this service.
