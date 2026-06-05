# Provider Limits and Cooldowns

Searchbox enforces local provider limits before external calls.

## Daily Limits

Configured in `.env`:

```text
ARXIV_DAILY_REQUEST_LIMIT=28800
AGENTIC_DATA_DAILY_REQUEST_LIMIT=10000
SCIENCESTACK_DAILY_REQUEST_LIMIT=100
OANOR_DAILY_REQUEST_LIMIT=3
SEARCHAPI_DAILY_REQUEST_LIMIT=100
SERPAPI_DAILY_REQUEST_LIMIT=250
```

Persistent usage file:

```text
/home/ubuntu/APICostX-Searchbox/data/advanced_provider_daily_usage.json
```

## Monthly Limits

Configured in `.env`:

```text
SERPAPI_MONTHLY_REQUEST_LIMIT=250
```

Persistent usage file:

```text
/home/ubuntu/APICostX-Searchbox/data/advanced_provider_monthly_usage.json
```

SerpApi is enforced against the monthly cap because its Google Scholar account quota is monthly. `/config` and `/health/monitor` expose `provider_monthly_usage` / `advanced_provider_monthly_usage` without exposing the key.

The file is protected with `fcntl` file locking so restarts and multiple processes do not forget usage.

## Why These Limits

arXiv:

- No official daily quota found.
- Official pacing is one request every three seconds, so the mathematical ceiling is 28,800/day.

Agentic Data:

- Published free daily limit: 10,000 requests/day.

ScienceStack:

- Free docs indicate 100 requests/day.

Oanor:

- Public information is inconsistent, with monthly free numbers appearing in different places.
- Searchbox uses conservative `3/day` until the account dashboard proves otherwise.

SearchAPI:

- Free tier is 100 requests.
- Searchbox caps at 100/day until a stricter reset policy is confirmed.

SerpApi:

- Configured local cap is 250 requests/month for Google Scholar requests.
- Daily cap is also set to 250 so the monthly quota is the real limiter.
- Treat dashboard plan limits as authoritative if the account changes; update `SERPAPI_MONTHLY_REQUEST_LIMIT` in `.env` to match the active plan.

## Cooldowns

Persistent cooldown file:

```text
/home/ubuntu/APICostX-Searchbox/data/advanced_provider_cooldowns.json
```

Failures that trigger cooldown:

```text
402 payment/subscription/account problem
429 throttled or refused
502 gateway/provider failure
503 unavailable
504 timeout
```

Cooldown behavior:

- Provider failure marks the provider as cooling down.
- Auto search skips cooling providers.
- Repeated failures increase cooldown aggressively up to `ADVANCED_PROVIDER_COOLDOWN_MAX_SECONDS`.
- Successful provider calls clear that provider's failure count and cooldown.

## API Visibility

Use:

```text
GET /config
GET /health/monitor
```

Both include daily usage and cooldown snapshots without exposing keys.
