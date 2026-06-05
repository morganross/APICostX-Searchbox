# Main File Refactor Plan

This document is the plan for turning `main.py` from a compact working prototype into a maintainable open-source Python service.

The goal is not to make the code look clever. The goal is to make it boring, navigable, testable, and easy for contributors to extend without breaking provider behavior.

## Current State

`main.py` is currently the application.

Measured shape:

- about 4,300 lines
- 166 top-level classes/functions
- FastAPI routes, provider adapters, extraction, LLM orchestration, quota storage, cooldowns, logging, config, and response aggregation all live in one file
- baseline public tests exist, but coverage is still low
- public repository structure and CI now exist

This is acceptable for a prototype. It is not acceptable as the long-term shape of a serious open-source service.

## Refactor Principles

### Preserve behavior first

Do not redesign behavior while moving code. The first refactor should be mostly mechanical.

### Tests before movement

Every major module extraction needs tests around the behavior being moved.

### Move by responsibility

Each module should have one reason to change.

### Keep public contracts stable

The public API contract is:

```text
POST /search
response.results[0].content
```

That contract should not change during internal refactors.

### Avoid provider rewrites during extraction

Provider adapters are fragile because each upstream API has quirks. Move them first, improve them later.

### No hidden globals in new code

New modules should accept settings/dependencies explicitly where practical. Existing globals can be wrapped during migration, then reduced later.

## Target Package Layout

Desired final structure:

```text
searchbox/
  __init__.py
  app.py
  main.py
  config.py
  models.py
  errors.py
  auth.py
  rate_limit.py
  logging_utils.py
  usage.py
  aggregation.py
  scoring.py
  text.py
  urls.py

  api/
    __init__.py
    routes.py
    health.py
    search.py
    logs.py

  providers/
    __init__.py
    base.py
    registry.py
    web.py
    serper.py
    brave.py
    searxng.py
    scientific.py
    arxiv.py
    agentic_data.py
    sciencestack.py
    oanor.py
    searchapi_scholar.py
    serpapi_scholar.py

  extraction/
    __init__.py
    core.py
    html.py
    pdf.py
    playwright.py

  llm/
    __init__.py
    options.py
    client.py
    classifier.py
    summarizer.py
    schema.py

  state/
    __init__.py
    json_store.py
    quota.py
    cooldown.py

  testing/
    __init__.py
    fixtures.py
```

Top-level compatibility files:

```text
main.py                  # temporary compatibility entrypoint: from searchbox.app import app
check_keys.py            # small CLI helper or replaced by python -m searchbox.check_keys
```

## Responsibility Map

### `searchbox.config`

Owns environment loading and typed settings.

Move from `main.py`:

- `_load_env_file`
- all top-level environment constants
- default paths
- provider limit settings
- LLM defaults
- search defaults

Target shape:

```python
@dataclass(frozen=True)
class Settings:
    auth_disabled: bool
    search_provider: str
    advanced_search_enabled: bool
    serpapi_monthly_request_limit: int
    ...

settings = Settings.from_env()
```

Rules:

- no hardcoded deployment paths
- repo-relative defaults only
- no keys printed in repr/logs
- settings object can be overridden in tests

### `searchbox.models`

Owns Pydantic request/response models.

Move:

- `LLMOptions`
- `ImageItem`
- `SourceEvidence`
- `SearchRequest`
- `SearchItem`
- `SearchResponse`
- `SearchSummaryRequest`
- `SearchSummaryResponse`
- `TavilySearchResult`
- `TavilySearchResponse`

Rules:

- models should not import providers
- models should not read environment variables directly
- default values that depend on settings should be injected or centralized

### `searchbox.api.routes`

Owns FastAPI route registration.

Move:

- `health`
- `config`
- `status`
- `health_monitor`
- `get_llm_attempt_logs`
- `get_provider_event_logs`
- `search`
- `search_get`
- `search_raw`
- `search_summary`

Rules:

- routes should orchestrate services, not parse provider payloads
- keep route functions short
- route tests should use `TestClient`

### `searchbox.auth` and `searchbox.rate_limit`

Move:

- `_auth_key_from_header_or_key`
- `_authorize`
- `_check_rate_limit`

Rules:

- auth behavior must remain compatible with `AUTH_DISABLED=true`
- tests must prove private endpoints do not leak secrets
- rate limit state should be injectable for tests

### `searchbox.logging_utils`

Move:

- `_json_safe`
- `_append_jsonl`
- `_tail_jsonl`
- `_log_llm_attempt`
- `_log_provider_event`
- `_summarize_events`

Rules:

- never log keys
- never log raw prompts or raw model outputs unless an explicit debug mode is designed and documented
- log file paths come from settings

### `searchbox.urls`

Move:

- `_is_private_ip`
- `_validate_fetch_url`
- `_domain_allowed`
- `_favicon_for_url`

Rules:

- SSRF protections must have tests
- private IP blocking should be default-on
- redirect and protocol behavior should be explicit

### `searchbox.text`

Move generic text helpers:

- `_shorten`
- `_boolish`
- `_bounded_int`
- `_chunk_text`
- `_truncate_payload`
- `_html_to_text`
- `_word_list`
- `_split_passages`
- `_extract_json_from_text`
- `_clean_arxiv_text` if not kept arXiv-specific

Rules:

- pure functions should have direct unit tests
- no provider imports

### `searchbox.scoring`

Move ranking/scoring helpers:

- `_score_item`
- `_summary_terms`
- `_is_domain_only_text`
- `_passage_score`
- `_select_source_passages`
- `_normalize_for_summarizer`
- `_split_result_buckets`

Rules:

- scoring should be deterministic
- tests should cover obvious ranking decisions

### `searchbox.extraction`

Move:

- `_pdf_to_text`
- `_extract_with_playwright`
- `_extract_content`
- HTML extraction helpers

Target modules:

```text
extraction/html.py
extraction/pdf.py
extraction/playwright.py
extraction/core.py
```

Rules:

- extraction result should become a typed model or dataclass
- PDF size limits enforced before expensive work
- failed extraction should return structured failure, not random dicts
- no provider-specific logic except where unavoidable

### `searchbox.state.json_store`

Move shared file-locking storage:

- `_advanced_provider_file_paths`
- `_read_json_file_locked`
- `_write_json_file_locked`

Rules:

- one shared locked JSON store implementation
- tests for corrupt/missing files
- tests for write replacement behavior

### `searchbox.state.quota`

Move:

- `_advanced_provider_daily_limits`
- `_advanced_provider_quota_day`
- `_advanced_provider_monthly_limits`
- `_advanced_provider_quota_month`
- `_advanced_provider_monthly_quota_paths`
- `_advanced_provider_monthly_quota_snapshot`
- `_reserve_advanced_provider_monthly_quota`
- `_advanced_provider_quota_paths`
- `_advanced_provider_quota_snapshot`
- `_reserve_advanced_provider_quota`

Target behavior:

```python
quota.reserve(provider_name, units=1)
quota.snapshot_daily()
quota.snapshot_monthly()
```

Rules:

- monthly and daily policies are explicit
- SerpApi monthly cap has tests
- quota reservation happens before external call
- no provider-specific special cases scattered around code

### `searchbox.state.cooldown`

Move:

- `_advanced_provider_base_cooldown_seconds`
- `_advanced_provider_cooldown_snapshot`
- `_advanced_provider_cooldown_remaining`
- `_raise_if_advanced_provider_cooling`
- `_mark_advanced_provider_success`
- `_mark_advanced_provider_failure`

Target behavior:

```python
cooldowns.raise_if_cooling(provider_name)
cooldowns.mark_success(provider_name)
cooldowns.mark_failure(provider_name, status_code, reason)
```

Rules:

- cooldown-worthy status codes documented
- repeated failures back off aggressively
- success clears failure count

### `searchbox.providers.base`

Create provider interface.

Target shape:

```python
@dataclass(frozen=True)
class ProviderResult:
    items: list[SearchItem]
    provider: str
    success: bool

class SearchProvider(Protocol):
    name: str
    kind: Literal['web', 'scientific']
    async def search(self, request: SearchRequest, context: ProviderContext) -> list[SearchItem]: ...
```

Provider context should contain:

- settings
- HTTP client factory
- quota service
- cooldown service
- logger
- extractor
- summarizer

### `searchbox.providers.web`

Move web provider orchestration:

- `_normalize_search_query`
- `_resolve_country`
- `_resolve_brave_safesearch`
- `_resolve_searxng_safesearch`
- `_resolve_freshness`
- `_resolve_searxng_time_range`
- `_resolve_serper_tbs`
- `_resolve_search_depth`
- `_parse_brave_results`
- `_parse_serper_results`
- `_parse_searxng_results`
- `_search_brave`
- `_search_serper`
- `_search_searxng`
- `_search_provider`
- `_run_search`

Eventually split per provider:

```text
providers/serper.py
providers/brave.py
providers/searxng.py
```

Rules:

- parser tests use fixtures
- network tests are opt-in
- web provider failures return useful errors

### `searchbox.providers.arxiv`

Move:

- `_compile_arxiv_query`
- `_arxiv_cooldown_remaining_seconds`
- `_arxiv_parse_retry_after`
- `_arxiv_mark_refusal`
- `_arxiv_throttle_exception`
- `_arxiv_rate_limited_get`
- `_fetch_arxiv_pdf_text`
- `_arxiv_wants_pdf_text`
- `_parse_arxiv_entries`
- `_run_arxiv_search`

Rules:

- query preservation tests are mandatory
- no accidental boolean injection
- rate limiting and 429 behavior tested with mocked HTTP

### `searchbox.providers.agentic_data`

Move:

- `_agentic_data_headers`
- `_agentic_text_from_payload`
- `_agentic_response_text`
- `_fetch_agentic_full_text`
- `_run_agentic_data_search`

### `searchbox.providers.sciencestack`

Move:

- `_sciencestack_headers`
- `_sciencestack_payload_data`
- `_sciencestack_text_from_payload`
- `_fetch_sciencestack_content`
- `_run_sciencestack_search`

### `searchbox.providers.oanor`

Move:

- `_oanor_headers`
- `_oanor_data_rows`
- `_oanor_first`
- `_oanor_pdf_url`
- `_oanor_arxiv_id`
- `_run_oanor_search`

### `searchbox.providers.searchapi_scholar`

Move:

- `_searchapi_auth_params`
- `_searchapi_author_names`
- `_searchapi_best_url`
- `_run_searchapi_scholar_search`

### `searchbox.providers.serpapi_scholar`

Move:

- `_serpapi_auth_params`
- `_serpapi_publication_text`
- `_serpapi_best_url`
- `_run_serpapi_scholar_search`

Rules:

- monthly quota remains enforced
- resource URL preference tested
- no live SerpApi calls in default tests

### `searchbox.providers.scientific`

Owns advanced/scientific orchestration.

Move:

- `_advanced_provider_names`
- `_resolve_advanced_source`
- `_advanced_provider_failure_status`
- `_advanced_provider_failure_reason`
- `_call_advanced_provider`
- `_advanced_clone_for_provider`
- `_run_advanced_search_auto`
- `_run_advanced_search`

Target shape:

```python
scientific_router.search_auto(request) -> list[SearchItem]
scientific_router.search_provider(provider_name, request) -> list[SearchItem]
```

Rules:

- provider order is settings-driven
- min/max provider behavior tested
- cooldown skip behavior tested
- fallback behavior tested

### `searchbox.llm`

Move:

- `_resolve_llm_options`
- `_summarize_paper_content`
- `_normalize_science_classifier_payload`
- `_classify_science_query`
- `_litellm_api_key_for_model`
- `_litellm_api_base_for_provider`
- `_split_provider_model`
- `_build_llm_candidate_specs`
- `_is_expensive_llm_spec`
- `_extract_llm_response_payload`
- `_normalize_summary_payload`
- `_validate_summary_payload`
- `_adjust_summary_confidence`
- `_summary_json_schema`
- `_resolve_response_format`
- `_call_litellm_model`
- `_repair_summary_payload`
- `_remaining_llm_timeout`
- `_run_llm_orchestrator`
- `_summarize_query`

Target modules:

```text
llm/options.py
llm/client.py
llm/classifier.py
llm/summarizer.py
llm/schema.py
```

Rules:

- LLM calls are mocked in default tests
- logs record attempts without raw prompts/output
- expensive fallback behavior is explicit

### `searchbox.aggregation`

Move:

- `_calculate_searchbox_usage`
- `_aggregate_source_block`
- `_build_aggregate_search_result`

Rules:

- one-result contract tested
- science and non-science contexts tested
- truncation behavior tested

## Migration Phases

## Phase 0: Freeze Current Behavior

Goal: prevent accidental behavior changes before moving code.

Add tests for:

- `/health` and `/config` public safety
- `/search` returns exactly one aggregate result
- aggregate URL starts with `searchbox://aggregate/`
- `results[0].content` includes web/science section rules
- SerpApi monthly quota snapshot and reserve behavior
- daily quota reserve behavior
- cooldown mark success/failure behavior
- private IP URL rejection
- query preservation for arXiv and Scholar providers
- provider parser fixture tests for SerpApi/SearchAPI/arXiv/ScienceStack

Do not move modules until these tests pass.

## Phase 1: Create Package Skeleton

Create empty package and compatibility entrypoint:

```text
searchbox/__init__.py
searchbox/app.py
searchbox/config.py
searchbox/models.py
main.py
```

`main.py` should become:

```python
from searchbox.app import app
```

At first, `searchbox.app` may still import legacy functions. The public app import path should continue to work.

Acceptance checks:

- `uvicorn main:app` still works
- tests pass
- CI passes

## Phase 2: Move Models

Move Pydantic classes to `searchbox.models`.

Update imports.

Acceptance checks:

- model tests pass
- API response models unchanged
- no route behavior changed

## Phase 3: Move Settings

Move environment loading and constants to `searchbox.config`.

This is one of the riskiest steps because many functions read globals.

Migration strategy:

1. Create `Settings` object with current values.
2. Keep compatibility aliases in legacy code temporarily.
3. Gradually replace global reads with `settings` fields.
4. Add tests for `.env.example` and default settings.

Acceptance checks:

- `.env.example` can be parsed
- no private path defaults
- runtime service still reads current `.env`

## Phase 4: Move Pure Utilities

Move easy pure helpers first:

- text helpers
- bool/int/float helpers
- URL/domain helpers
- JSON extraction helpers

Acceptance checks:

- pure unit tests pass
- no route behavior changes

## Phase 5: Move Logging, Quotas, Cooldowns

Move stateful infrastructure before providers.

Target:

```text
state/json_store.py
state/quota.py
state/cooldown.py
logging_utils.py
```

Acceptance checks:

- quota tests pass
- cooldown tests pass
- log redaction tests pass
- current data file compatibility preserved or migration documented

## Phase 6: Move Extraction

Move HTML/PDF/Playwright extraction.

Acceptance checks:

- HTML extraction fixture tests
- PDF extraction fixture tests
- private IP blocking tests
- extraction failure shape tests

## Phase 7: Move Web Providers

Move Serper, Brave, SearXNG adapters.

Acceptance checks:

- parser fixture tests
- mocked HTTP tests
- `/search` web-only route test

## Phase 8: Move Scientific Providers

Move one provider at a time:

1. SerpApi Scholar
2. SearchAPI Scholar
3. ScienceStack
4. arXiv
5. Agentic Data
6. Oanor

Why this order:

- SerpApi/SearchAPI are recently touched and simpler Scholar adapters.
- ScienceStack is working and structured.
- arXiv has special rate/cooldown/PDF behavior.
- Agentic/Oanor have more account/upstream failure states.

Acceptance checks per provider:

- missing key test
- parser fixture test
- quota reserve test
- extraction URL selection test
- provider failure test

## Phase 9: Move Scientific Router

Move advanced search orchestration after individual providers move.

Acceptance checks:

- auto order test
- min provider success test
- max provider attempts test
- cooldown skip test
- fallback after provider failure test

## Phase 10: Move LLM

Move classifier and summarizer after providers are stable.

Acceptance checks:

- classifier mocked success/failure tests
- malformed classifier response test
- summarizer schema validation test
- expensive fallback disabled/enabled tests
- no raw prompts/output in logs

## Phase 11: Move Routes And App Factory

Create app factory:

```python
def create_app(settings: Settings | None = None) -> FastAPI:
    ...

app = create_app()
```

This allows tests to create isolated apps with temp quota/log paths.

Acceptance checks:

- `uvicorn main:app` works
- tests use app factory
- route files are thin

## Phase 12: Remove Legacy Globals

Once behavior is stable:

- remove compatibility aliases
- remove legacy imports
- make dependencies explicit
- reduce global mutable state
- isolate runtime status counters

Acceptance checks:

- tests pass
- lint passes
- no circular imports
- no provider imports from models/config

## Test Expansion Plan

Target test tree:

```text
tests/
  test_api_contract.py
  test_config.py
  test_auth.py
  test_urls.py
  test_logging_redaction.py
  test_quota.py
  test_cooldown.py
  test_aggregation.py
  test_extraction_html.py
  test_extraction_pdf.py
  providers/
    test_arxiv.py
    test_sciencestack.py
    test_searchapi_scholar.py
    test_serpapi_scholar.py
    test_agentic_data.py
    test_oanor.py
  llm/
    test_classifier.py
    test_summarizer.py
```

Coverage should increase in stages:

- after Phase 0: 35%+
- after provider fixture tests: 55%+
- after LLM and extraction tests: 70%+
- after route/app factory tests: 80%+

Coverage should not become a vanity number. The important goal is coverage over contracts and failure behavior.

## Import Rules

To avoid circular import soup:

- `models` imports nothing from Searchbox except maybe shared enums.
- `config` imports no providers.
- providers may import models, config types, extraction interfaces, quota/cooldown interfaces, and logging interfaces.
- routes import service orchestration, not individual provider helpers.
- LLM modules do not import routes.
- extraction modules do not import providers.
- state modules do not import providers.

## Compatibility Rules

During refactor:

- `uvicorn main:app` must keep working.
- `/health` response stays public-safe.
- `/config` never exposes keys.
- `/search` returns one aggregate result.
- `advanced_search=true` compatibility remains until intentionally deprecated.
- no paid provider live tests run by default.

## Pull Request Strategy

Do not make one enormous refactor PR.

Recommended PR sequence:

1. Add missing tests around current behavior.
2. Add package skeleton and app compatibility entrypoint.
3. Move models.
4. Move config.
5. Move pure utilities.
6. Move quota/cooldown/logging.
7. Move extraction.
8. Move web providers.
9. Move scientific providers one by one.
10. Move LLM modules.
11. Move routes into app factory.
12. Remove legacy globals and dead compatibility code.

Each PR should be reviewable and behavior-preserving.

## Definition Of Done

The refactor is done when:

- `main.py` is only a compatibility entrypoint
- source code lives under `searchbox/`
- tests cover provider parsers, quota, cooldown, extraction, LLM, aggregation, and API contracts
- default CI passes
- no private deployment paths or secrets appear in tracked files
- docs match the new module layout
- adding a provider means adding one adapter module, fixtures, tests, and docs

## What Not To Do

Do not:

- rewrite provider behavior while moving files
- rename public fields casually
- remove compatibility flags without a migration note
- run live paid-provider tests in CI
- add a container as the only supported install path
- hide low coverage by weakening tests
- create a clever framework when plain modules are enough

## First Concrete Step

The smallest serious next step is Phase 0:

1. Add provider parser fixture tests for SerpApi Scholar and SearchAPI Scholar.
2. Add quota reserve tests for daily and monthly caps.
3. Add private IP URL blocking tests.
4. Add aggregate science/non-science response tests.

Once those pass, start the package skeleton.
