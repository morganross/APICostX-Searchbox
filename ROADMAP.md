# Roadmap

Searchbox is being hardened from a compact working prototype into a professional open-source retrieval service.

## Stabilize First

Before starting the package refactor, address the live operational issues that can affect real searches:

- Reduce LLM `validation_failed` errors and make malformed model output recoverable where practical.
- Reorder, replace, or disable unreliable default LLM models before they become the first path for classifier or summary work.
- Deprioritize providers that are currently unavailable because of quota, billing, or rate-limit failures.
- Tune scholar-provider cooldown behavior so rate-limited providers do not repeatedly burn attempts.
- Make `/health` distinguish between fully healthy, degraded-but-serving, and failing states.
- Keep `/health/monitor` and provider/LLM failure ratios visible enough for scheduled smoke checks.
- Document the current `/search-raw` response contract after the latest raw-search behavior change.
- Keep `/search` as the stable aggregate response contract for client integrations.
- Treat `AUTH_DISABLED=true` as private/internal deployment mode only, and document the public-exposure risk.
- Add secret-scanning expectations before broader public release.

## Stabilization Acceptance Criteria

- Core web search succeeds while optional provider failures degrade gracefully.
- LLM validation failures are rare, visible, and either repaired or cleanly bypassed.
- Providers returning payment, quota, or persistent rate-limit errors are not preferred in automatic mode.
- `/health` reports degraded state when important providers or LLM paths are unhealthy.
- `/config`, `/health`, logs, and public docs do not expose secrets.
- The documented `/search` and `/search-raw` contracts match the running API.

## Near Term

- Expand parser and quota tests.
- Add mocked provider fixtures.
- Split configuration and models out of `main.py`.
- Move provider adapters into a `providers/` package.
- Move quota, cooldown, extraction, and aggregation logic into focused modules.
- Keep `/search` response behavior stable during refactors.

## Later

- Optional Docker packaging.
- Python package publishing.
- More provider adapters.
- Better extraction benchmarks.
- Better engine-specific integration examples.

## Refactor Plan

The detailed package refactor plan lives in [`public-docs/main-file-refactor-plan.md`](public-docs/main-file-refactor-plan.md).
