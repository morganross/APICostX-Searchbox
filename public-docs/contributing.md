# Contributing

Searchbox should stay small but well explained.

## Principles

- Keep `/search` the main public endpoint.
- Preserve the one-result aggregate contract.
- Never log secrets.
- Add quota controls for paid providers.
- Make provider failure visible.
- Do not mutate user queries unnecessarily.
- Keep paid live tests opt-in.

## New Provider PRs

Update:

- provider docs
- configuration reference
- quota notes
- troubleshooting notes
- tests or fixtures

## Tests

Recommended tests:

- parser fixtures
- missing key
- quota reached
- cooldown behavior
- extraction failure
- aggregate response shape
- secret redaction
