# Roadmap

Searchbox is being hardened from a compact working prototype into a professional open-source retrieval service.

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
