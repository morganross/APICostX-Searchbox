from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import main
import searchbox.urls as urls
from searchbox.aggregation import aggregate_source_block, build_aggregate_search_result
from searchbox.extraction.html import html_to_text
from searchbox.extraction.pdf import pdf_to_text
from searchbox.logging_utils import append_jsonl, summarize_events, tail_jsonl
from searchbox.models import SearchItem
from searchbox.providers.web import parse_brave_results, parse_serper_results, parse_searxng_results
from searchbox.state import cooldown as cooldown_state
from searchbox.state import json_store, quota as quota_state
from searchbox.text import boolish, bounded_int, chunk_text, truncate_payload
from searchbox.usage import calculate_searchbox_usage
from searchbox.urls import domain_allowed, validate_fetch_url


def test_json_store_reads_and_writes_while_adding_lock_file(tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"

    assert not state_file.exists()
    assert json_store.read_json_file_locked(str(state_file)) == {}

    stored = json_store.write_json_file_locked(
        str(state_file),
        lambda state: {"count": int(state.get("count", 0)) + 1},
    )
    assert stored == {"count": 1}
    assert json_store.read_json_file_locked(str(state_file)) == {"count": 1}

    stored = json_store.write_json_file_locked(
        str(state_file),
        lambda state: state,
    )
    assert stored == {"count": 1}
    assert json_store.read_json_file_locked(str(state_file)) == {"count": 1}


def test_json_store_recovers_from_corrupt_payload(tmp_path: Path) -> None:
    state_file = tmp_path / "corrupt.json"
    state_file.write_text("not-json")
    assert json_store.read_json_file_locked(str(state_file)) == {}

    def mutator(state: Dict[str, Any]) -> Dict[str, Any]:
        state["repaired"] = True
        return state

    result = json_store.write_json_file_locked(str(state_file), mutator)
    assert result == {"repaired": True}
    assert json_store.read_json_file_locked(str(state_file)) == {"repaired": True}


def test_cooldown_failure_and_success_updates_state_with_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cooldown_file = str(tmp_path / "cooldown.json")
    t = 1000.0
    monkeypatch.setattr(cooldown_state.time, "time", lambda: t)

    retry = cooldown_state.mark_failure(
        cooldown_file,
        provider="serpapi_scholar",
        status_code=429,
        reason="too many requests",
        max_cooldown_seconds=100000,
        arxiv_cooldown_seconds=30,
        log_event=lambda event: None,
    )
    assert retry >= 900

    state = cooldown_state.snapshot(cooldown_file, ["serpapi_scholar", "arxiv"])
    assert state["serpapi_scholar"]["failure_count"] == 1
    assert state["serpapi_scholar"]["last_status_code"] == 429

    retry = cooldown_state.mark_failure(
        cooldown_file,
        provider="serpapi_scholar",
        status_code=429,
        reason="too many requests",
        max_cooldown_seconds=100000,
        arxiv_cooldown_seconds=30,
        log_event=lambda event: None,
    )
    assert retry >= 1800

    state = cooldown_state.snapshot(cooldown_file, ["serpapi_scholar", "arxiv"])
    assert state["serpapi_scholar"]["failure_count"] == 2
    assert state["serpapi_scholar"]["retry_after_seconds"] > 0

    cooldown_state.mark_success(cooldown_file, "serpapi_scholar", lambda event: None)
    state = cooldown_state.snapshot(cooldown_file, ["serpapi_scholar", "arxiv"])
    assert state["serpapi_scholar"]["cooling_down"] is False
    assert state["serpapi_scholar"]["failure_count"] == 0
    assert state["serpapi_scholar"]["retry_after_seconds"] == 0


def test_cooldown_raises_for_blocked_provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cooldown_file = str(tmp_path / "cooldown.json")
    monkeypatch.setattr(cooldown_state.time, "time", lambda: 2000.0)

    cooldown_state.mark_failure(
        cooldown_file,
        provider="arxiv",
        status_code=429,
        reason="rate limited",
        max_cooldown_seconds=1200,
        arxiv_cooldown_seconds=600,
        log_event=lambda event: None,
    )

    with pytest.raises(HTTPException) as exc:
        cooldown_state.raise_if_cooling(cooldown_file, ["arxiv"], "arxiv")

    assert exc.value.status_code == 429
    assert exc.value.detail["reason"] == "advanced_provider_cooldown_active"


def test_quota_daily_and_monthly_limits_and_snapshots(tmp_path: Path) -> None:
    daily = str(tmp_path / "daily.json")
    monthly = str(tmp_path / "monthly.json")
    limits = {"serpapi_scholar": 2}
    monthly_limits = {"serpapi_scholar": 3}

    quota_state.reserve_daily(
        "serpapi_scholar",
        daily,
        limits,
        monthly_quota_file=monthly,
        monthly_limits=monthly_limits,
        units=1,
    )
    quota_state.reserve_daily(
        "serpapi_scholar",
        daily,
        limits,
        monthly_quota_file=monthly,
        monthly_limits=monthly_limits,
        units=1,
    )

    daily_snapshot = quota_state.daily_snapshot(daily, limits)
    monthly_snapshot = quota_state.monthly_snapshot(monthly, monthly_limits)
    assert daily_snapshot["serpapi_scholar"]["used"] == 2
    assert daily_snapshot["serpapi_scholar"]["remaining"] == 0
    assert monthly_snapshot["serpapi_scholar"]["used"] == 2

    with pytest.raises(HTTPException) as exc:
        quota_state.reserve_daily(
            "serpapi_scholar",
            daily,
            limits,
            monthly_quota_file=monthly,
            monthly_limits=monthly_limits,
            units=1,
        )
    assert exc.value.status_code == 429
    assert exc.value.detail["reason"] == "advanced_provider_daily_limit_reached"

    with pytest.raises(HTTPException) as exc:
        quota_state.reserve_monthly(
            "serpapi_scholar",
            monthly,
            {"serpapi_scholar": 2},
            units=1,
        )
    assert exc.value.status_code == 429
    assert exc.value.detail["reason"] == "advanced_provider_monthly_limit_reached"


def test_quota_daily_limit_does_not_consume_monthly_units(tmp_path: Path) -> None:
    daily = str(tmp_path / "daily.json")
    monthly = str(tmp_path / "monthly.json")

    quota_state.reserve_daily(
        "serpapi_scholar",
        daily,
        {"serpapi_scholar": 1},
        monthly_quota_file=monthly,
        monthly_limits={"serpapi_scholar": 5},
        units=1,
    )

    with pytest.raises(HTTPException) as exc:
        quota_state.reserve_daily(
            "serpapi_scholar",
            daily,
            {"serpapi_scholar": 1},
            monthly_quota_file=monthly,
            monthly_limits={"serpapi_scholar": 5},
            units=1,
        )

    assert exc.value.detail["reason"] == "advanced_provider_daily_limit_reached"
    assert quota_state.monthly_snapshot(monthly, {"serpapi_scholar": 5})["serpapi_scholar"]["used"] == 1


def test_logging_utils_append_tail_and_summarize(tmp_path: Path) -> None:
    log_file = tmp_path / "events.jsonl"
    append_jsonl(str(log_file), {"provider": "arxiv", "success": True, "purpose": "search"})
    append_jsonl(str(log_file), {"provider": "arxiv", "success": False, "purpose": "search"})
    append_jsonl(str(log_file), {"provider": "serpapi", "success": False, "purpose": "raw"})
    append_jsonl(str(log_file), {"provider": "serpapi", "purpose": "search", "success": True})

    rows = tail_jsonl(str(log_file), 3)
    assert len(rows) == 3
    assert rows[0]["provider"] == "arxiv"

    summary = summarize_events(rows, ["provider", "purpose"])
    assert summary["total"] == 3
    assert summary["groups"]["arxiv|search"]["failure"] == 1
    assert summary["groups"]["serpapi|search"]["success"] == 1


def test_provider_parser_helpers_handle_empty_and_malformed_inputs() -> None:
    brave = parse_brave_results({"web": {"results": [{"title": "x", "url": "https://x"}]}}, 1)
    assert brave and len(brave) == 1

    searxng = parse_searxng_results(
        {"results": [{"title": "y", "url": "https://y", "content": "abc", "engine": "google", "score": 0.9}]}, 2
    )
    assert searxng and searxng[0]["source"] == "searxng"
    assert searxng[0]["score"] == 0.9

    serper = parse_serper_results(
        {
            "organic": [
                {
                    "title": "z",
                    "link": "https://z",
                    "snippet": "s",
                    "position": 9,
                    "images": [{"title": "pdf", "link": "/bad-pdf.pdf", "imageUrl": "https://cdn/img.png"}],
                }
            ]
        },
        5,
    )
    assert serper[0]["rank"] == 9
    assert serper[0]["source"] == "serper"
    assert serper[0]["images"][0]["url"] == "https://cdn/img.png"


def test_fetch_url_validation_blocks_private_hosts(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_getaddrinfo(hostname, port, *args, **kwargs):
        return [(2, 1, 6, "", ("127.0.0.1", 80))]

    monkeypatch.setattr(urls.socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(HTTPException):
        validate_fetch_url("https://127.0.0.1/safe", block_private_fetch_ips=True)

    validate_fetch_url("https://127.0.0.1/safe", block_private_fetch_ips=False)


def test_domain_filtering_with_include_and_exclude() -> None:
    assert domain_allowed("https://api.arxiv.org/paper", ["arxiv.org"], [])
    assert domain_allowed("https://api.arxiv.org/paper", ["example.com"], []) is False
    assert domain_allowed("https://news.example.com", [], ["example.com"]) is False
    assert domain_allowed("https://deep.example.net", [], ["example.com"])
    assert domain_allowed("https://science.example.com", [], ["other.com"])


def test_text_helpers_trim_and_chunk_invariants() -> None:
    assert boolish("false") is False
    assert boolish("TRUE") is True
    assert boolish(None) is False
    assert bounded_int("9", default=1, minimum=2, maximum=5) == 5
    assert bounded_int("abc", default=3, minimum=1, maximum=10) == 3

    assert chunk_text("one two three four", 3).startswith("<chunk 1>")
    assert chunk_text(" ".join(str(i) * 10 for i in range(1, 200)), 1) != ""
    assert truncate_payload("abc", 10) == "abc"


def test_html_and_pdf_extractors_are_safe_for_bad_inputs() -> None:
    html = "<html><head><title>x</title></head><body><script>alert(1)</script>A   <p>Text</p></body></html>"
    assert html_to_text(html) == "x A Text"
    assert pdf_to_text(b"not a pdf") == ""


def test_usage_cost_is_consistent_for_metered_and_free_sources() -> None:
    free = calculate_searchbox_usage("advanced:arxiv", search_queries=5, scrapes_http=4, scrapes_playwright=5)
    assert free["search_cost_usd"] == 0.0
    assert free["scrape_cost_usd"] == 0.0
    assert free["cost_confidence"] == "exact"

    pay = calculate_searchbox_usage(
        "brave", search_queries=2, scrapes_playwright=2, llm_usage={"input_tokens": 1000, "output_tokens": 200}
    )
    assert pay["search_cost_usd"] == 0.002
    assert pay["scrape_cost_usd"] == 0.0
    assert pay["scrape_fetches"] == 2
    assert pay["cost_confidence"] == "estimated"


def test_usage_evidence_prefers_provider_reported_llm_costs() -> None:
    usage = calculate_searchbox_usage(
        "brave",
        search_queries=1,
        llm_attempts=[
            {
                "provider": "openrouter",
                "model": "openai/gpt-5-mini",
                "success": True,
                "usage": {"prompt_tokens": 1000, "completion_tokens": 200, "cost": 0.123456},
            }
        ],
    )

    assert usage["llm_cost_usd"] == 0.123456
    assert usage["llm_cost_confidence"] == "exact"
    assert usage["usage_evidence"]["llm"]["cost_sources"] == {"provider_reported": 1}
    assert usage["usage_evidence"]["llm"]["prompt_tokens"] == 1000
    assert usage["usage_evidence"]["llm"]["completion_tokens"] == 200


def test_usage_evidence_records_exact_provider_cost_details_and_attempts() -> None:
    usage = calculate_searchbox_usage(
        "web+advanced:serpapi_scholar",
        search_queries=2,
        llm_attempts=[
            {
                "provider": "openrouter",
                "model": "free-model",
                "success": False,
                "failure_type": "RateLimitError",
            },
            {
                "provider": "openrouter",
                "model": "paid-model",
                "success": True,
                "usage": {
                    "prompt_tokens": 20,
                    "completion_tokens": 5,
                    "cost_details": {"upstream_inference_cost": 0.0042},
                },
            },
        ],
        search_attempts=[{"provider": "serper", "success": True}, {"provider": "serpapi_scholar", "success": True}],
        fetch_attempts=[{"url": "https://example.com", "method": "http", "success": True}],
    )

    evidence = usage["usage_evidence"]
    assert evidence["schema_version"] == "searchbox-usage-evidence-v1"
    assert usage["cost_confidence"] == "unknown_external_meter"
    assert evidence["search"]["attempt_count"] == 2
    assert evidence["fetch"]["attempt_count"] == 1
    assert evidence["llm"]["attempt_count"] == 2
    assert evidence["llm"]["failure_count"] == 1
    assert evidence["llm"]["cost_sources"] == {"provider_cost_details.upstream_inference_cost": 1}


def test_default_llm_candidate_order_uses_free_models_before_paid_backstop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "LLM_MODEL", "openrouter/qwen/qwen3-coder:free")
    monkeypatch.setattr(main, "LLM_PROVIDER", "openrouter")
    monkeypatch.setattr(main, "LLM_QUALITY_TIER", "balanced")
    monkeypatch.setattr(main, "OPENROUTER_MODEL_BALANCED", "openrouter/qwen/qwen3-coder:free")
    monkeypatch.setattr(
        main,
        "LLM_FALLBACK_MODELS",
        ["openrouter/moonshotai/kimi-k2.6:free", "openrouter/openai/gpt-5-mini"],
    )

    resolved = main._resolve_llm_options(None)
    specs = main._build_llm_candidate_specs(resolved)

    assert [spec["model"] for spec in specs] == [
        "openrouter/qwen/qwen3-coder:free",
        "openrouter/moonshotai/kimi-k2.6:free",
        "openrouter/openai/gpt-5-mini",
    ]
    assert main._is_free_llm_spec(specs[0]) is True
    assert main._is_free_llm_spec(specs[1]) is True
    assert main._is_expensive_llm_spec(specs[2]) is True


def test_free_llm_retry_after_parser_bounds_sleep() -> None:
    error = RuntimeError(
        'RateLimitError: {"metadata":{"retry_after_seconds_raw":28.139,"headers":{"Retry-After":"29"}}}'
    )

    assert main._extract_llm_retry_after_seconds(error) == 28.139
    assert main._free_llm_retry_sleep_seconds(error, retry_index=0, remaining_seconds=10) == 9.0
    assert main._free_llm_retry_sleep_seconds(error, retry_index=0, remaining_seconds=60) == 28.139


def test_aggregate_builder_includes_science_section_and_single_result_shape() -> None:
    web = SearchItem(
        rank=1,
        title="Web title",
        url="https://example.com/web",
        content="Web content",
        description="web summary",
        source="web",
        extracted_content="raw web content",
        content_chars=11,
        scraped=True,
    )
    sci = SearchItem(
        rank=2,
        title="Paper title",
        url="https://example.com/paper.pdf",
        content="Paper content",
        description="paper summary",
        source="arxiv",
        extracted_content="raw paper content",
        content_chars=13,
        scraped=True,
    )

    result = build_aggregate_search_result(
        query="lithium dendrite solid electrolyte interface",
        request_id="req-1",
        web_results=[web],
        science_results=[sci],
        classifier_result={"is_science": True, "confidence": 0.99, "reason": "science"},
        use_science=True,
        content_max_chars=8000,
        raw_content_max_chars=20000,
    )

    assert result.url == "https://example.com/web"
    assert result.searchbox_url == "searchbox://aggregate/req-1"
    assert "# Scientific Context" in result.content
    assert "Web title" in result.content
    assert "Paper title" in result.content
    assert "raw web content" in result.raw_content
    assert result.score == 1.0


def test_aggregate_source_block_formats_source_blocks() -> None:
    item = SearchItem(
        rank=1,
        title="Title",
        url="https://example.com/a",
        content="a " * 10,
        description="",
        source="web",
        engine="serper",
        published="2026-01-01",
    )

    block = aggregate_source_block(item, index=2, kind="web", max_chars=20)
    assert block.startswith("## Source 2: Title")
    assert "Type: web" in block
    assert "Published: 2026-01-01" in block
    assert "Context:" in block


def test_api_health_and_logs_endpoints_work_with_auth(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(main, "AUTH_DISABLED", False)
    monkeypatch.setattr(main, "SEARCH_API_KEY", "secret")
    monkeypatch.setattr(main, "LLM_ATTEMPT_LOG_FILE", str(tmp_path / "llm.jsonl"))
    monkeypatch.setattr(main, "PROVIDER_EVENT_LOG_FILE", str(tmp_path / "provider.jsonl"))
    monkeypatch.setattr(main, "SEARCHBOX_LOG_API_MAX_LINES", 200)

    append_jsonl(main.LLM_ATTEMPT_LOG_FILE, {"purpose": "health", "provider": "openai", "success": True})
    append_jsonl(main.PROVIDER_EVENT_LOG_FILE, {"provider": "serpapi", "event": "failure", "success": False})

    client = TestClient(main.app)

    unauthorized = client.get("/health/monitor")
    assert unauthorized.status_code == 401

    bad = client.get("/health/monitor", headers={"authorization": "Bearer wrong"})
    assert bad.status_code == 403

    headers = {"authorization": "Bearer secret"}
    ok = client.get("/health/monitor", headers=headers)
    body = ok.json()
    assert ok.status_code == 200
    assert body["llm_attempts_recent"]["total"] == 1
    assert body["provider_events_recent"]["total"] == 1

    logs = client.get("/logs/provider-events?limit=20", headers=headers)
    assert logs.status_code == 200
    payload: Dict[str, Any] = logs.json()
    assert payload["log"] == "provider_events"
    assert payload["count"] == 20
    assert isinstance(payload["events"], list)
    assert len(payload["events"]) == 1


def test_api_logs_endpoints_respect_limits_when_auth_disabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(main, "AUTH_DISABLED", True)
    monkeypatch.setattr(main, "LLM_ATTEMPT_LOG_FILE", str(tmp_path / "llm_attempts.jsonl"))

    client = TestClient(main.app)
    logs = client.get("/logs/llm-attempts?limit=0")
    assert logs.status_code == 200
    payload = logs.json()
    assert payload["count"] == 1
    assert payload["events"] == []
