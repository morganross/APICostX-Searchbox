# Operations

Searchbox can run as a local process, supervised service, or containerized service if the project adds container support.

## Health

```bash
curl -sS http://127.0.0.1:9000/health
```

## Monitor

```bash
curl -sS http://127.0.0.1:9000/health/monitor
```

## Persistent State

Keep these on persistent storage:

- provider daily usage file
- provider monthly usage file
- provider cooldown file
- JSONL logs if audit history matters

## Production Checklist

- Auth enabled.
- Secrets loaded from env or secret manager.
- Provider caps match plans.
- Private IP fetch blocking enabled if available.
- Log endpoints protected.
- `/config` checked for secret leakage.

## Self-Hosted Linux Service

For a normal non-container deployment, see [Systemd Self-Hosting](systemd.md).
