# curl Examples

## Health

```bash
curl -sS http://127.0.0.1:9000/health
```

## Search

```bash
curl -sS http://127.0.0.1:9000/search \
  -H 'content-type: application/json' \
  -d '{"query":"lithium dendrite solid electrolyte interface","max_results":1}'
```

## Logs

```bash
curl -sS 'http://127.0.0.1:9000/logs/provider-events?limit=50'
```
