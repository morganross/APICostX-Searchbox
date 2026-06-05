# Security

Searchbox handles secrets and fetches external URLs. Public deployments should be treated as internet-facing services.

## Auth

Use:

```text
AUTH_DISABLED=false
SEARCH_API_KEY=<strong token>
```

## Secrets

Do not commit `.env` or real provider keys.

## Logs

Do not log keys, authorization headers, raw prompts, raw model outputs, or private request payloads.

## Config Endpoint

`/config` may show booleans and limits. It must not show key values.

## Network Fetching

Protect against SSRF:

- block private IP ranges
- limit redirects
- enforce timeouts
- enforce size limits
- allow only HTTP/HTTPS

## Provider Terms

Respect provider quotas, plans, and access controls.
