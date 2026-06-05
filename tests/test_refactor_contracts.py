import pytest
from fastapi import HTTPException

import main

from searchbox.search_options import (
    resolve_include_answer,
    resolve_include_content,
    resolve_max_chars_per_source,
    resolve_max_results,
    resolve_searxng_time_range,
    resolve_serper_tbs,
    resolve_search_depth,
    split_result_buckets,
)
from searchbox.scoring import score_item
from searchbox.models import SearchItem as _SearchItemForTests


def test_search_request_defaults_are_stable():
    req = main.SearchRequest(query="battery dendrites")
    assert req.count == main.SERPER_DEFAULT_COUNT
    assert req.max_results is None
    assert req.include_domains == []
    assert req.exclude_domains == []


def test_private_fetch_url_is_rejected():
    with pytest.raises(HTTPException) as exc:
        main._validate_fetch_url("http://127.0.0.1/private")
    assert exc.value.status_code == 400
    assert "private" in str(exc.value.detail).lower()


def test_daily_quota_reserve_and_limit(tmp_path, monkeypatch):
    quota_file = tmp_path / "daily.json"
    monkeypatch.setattr(main, "ADVANCED_PROVIDER_QUOTA_FILE", str(quota_file))
    monkeypatch.setattr(main, "SERPAPI_DAILY_REQUEST_LIMIT", 2)
    monkeypatch.setattr(main, "SERPAPI_MONTHLY_REQUEST_LIMIT", 10)
    monkeypatch.setattr(main, "ADVANCED_PROVIDER_MONTHLY_QUOTA_FILE", str(tmp_path / "monthly.json"))

    main._reserve_advanced_provider_quota("serpapi_scholar")
    main._reserve_advanced_provider_quota("serpapi_scholar")
    with pytest.raises(HTTPException) as exc:
        main._reserve_advanced_provider_quota("serpapi_scholar")
    assert exc.value.status_code == 429
    assert exc.value.detail["reason"] == "advanced_provider_daily_limit_reached"


def test_monthly_quota_reserve_and_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "ADVANCED_PROVIDER_MONTHLY_QUOTA_FILE", str(tmp_path / "monthly.json"))
    monkeypatch.setattr(main, "SERPAPI_MONTHLY_REQUEST_LIMIT", 1)

    main._reserve_advanced_provider_monthly_quota("serpapi_scholar")
    with pytest.raises(HTTPException) as exc:
        main._reserve_advanced_provider_monthly_quota("serpapi_scholar")
    assert exc.value.status_code == 429
    assert exc.value.detail["reason"] == "advanced_provider_monthly_limit_reached"


def test_cooldown_mark_failure_and_success(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "ADVANCED_PROVIDER_COOLDOWN_FILE", str(tmp_path / "cooldowns.json"))
    main._mark_advanced_provider_failure("serpapi_scholar", 503, "temporary outage")
    snapshot = main._advanced_provider_cooldown_snapshot()
    assert snapshot["serpapi_scholar"]["cooling_down"] is True
    assert snapshot["serpapi_scholar"]["failure_count"] == 1

    main._mark_advanced_provider_success("serpapi_scholar")
    snapshot = main._advanced_provider_cooldown_snapshot()
    assert snapshot["serpapi_scholar"]["cooling_down"] is False
    assert snapshot["serpapi_scholar"]["failure_count"] == 0


def test_serpapi_prefers_pdf_resource_url():
    row = {
        "link": "https://example.com/landing",
        "resources": [
            {"title": "HTML", "link": "https://example.com/html"},
            {"title": "PDF", "link": "https://example.com/paper.pdf"},
        ],
    }
    assert main._serpapi_best_url(row) == "https://example.com/paper.pdf"


def test_searchapi_prefers_resource_link():
    row = {
        "link": "https://example.com/landing",
        "resource": {"link": "https://example.com/paper.pdf"},
    }
    assert main._searchapi_best_url(row) == "https://example.com/paper.pdf"


def test_aggregate_science_section_toggle():
    item = main.SearchItem(rank=1, title="Example", url="https://example.com", content="Example content", source="test")
    web_only = main._build_aggregate_search_result(
        query="example",
        request_id="web",
        web_results=[item],
        science_results=[],
        classifier_result={},
        use_science=False,
    )
    science = main._build_aggregate_search_result(
        query="example",
        request_id="science",
        web_results=[item],
        science_results=[item],
        classifier_result={"is_science": True, "confidence": 0.9, "reason": "technical"},
        use_science=True,
    )
    assert "# Scientific Context" not in web_only.content
    assert "# Scientific Context" in science.content
    assert science.url == "searchbox://aggregate/science"

def test_extraction_helpers_are_available():
    from searchbox.extraction import ExtractionSettings, html_to_text, pdf_to_text

    html = '<html><script>bad()</script><p>Hello <b>world</b></p></html>'
    assert html_to_text(html) == "Hello world"
    assert pdf_to_text(b"not a pdf") == ""
    assert ExtractionSettings(user_agent="test-agent").user_agent == "test-agent"

def test_web_provider_parsers_are_available():
    from searchbox.providers.web import WebSearchOptions, parse_serper_results

    rows = parse_serper_results({"organic": [{"title": "Result", "link": "https://example.com", "snippet": "Text"}]}, 5)
    assert rows[0]["source"] == "serper"
    assert rows[0]["url"] == "https://example.com"
    assert WebSearchOptions(query="query", count=1).query == "query"

def test_auth_module_preserves_status_codes():
    from searchbox.auth import AuthSettings, auth_key_from_header_or_key

    disabled = AuthSettings(auth_disabled=True, search_api_key="")
    assert auth_key_from_header_or_key(None, settings=disabled) == "anonymous"

    enabled = AuthSettings(auth_disabled=False, search_api_key="secret")
    assert auth_key_from_header_or_key("Bearer secret", settings=enabled) == "authorized"
    with pytest.raises(HTTPException) as missing:
        auth_key_from_header_or_key(None, settings=enabled)
    assert missing.value.status_code == 401
    with pytest.raises(HTTPException) as invalid:
        auth_key_from_header_or_key("Bearer wrong", settings=enabled)
    assert invalid.value.status_code == 403


def test_rate_limiter_enforces_minute_bucket():
    from searchbox.rate_limit import InMemoryRateLimiter

    now = 1000.0
    limiter = InMemoryRateLimiter(clock=lambda: now)
    limiter.check("bucket", 2)
    limiter.check("bucket", 2)
    with pytest.raises(HTTPException) as exc:
        limiter.check("bucket", 2)
    assert exc.value.status_code == 429


def _test_req_factory(**kwargs):
    return type('Req', (), kwargs)()


def _new_test_item(**kwargs):
    return _SearchItemForTests(
        rank=kwargs.pop('rank', 1),
        title=kwargs.pop('title', 'Example'),
        url=kwargs.pop('url', 'https://example.com'),
        content=kwargs.pop('content', 'sample content about science'),
        description=kwargs.pop('description', 'summary'),
        source=kwargs.pop('source', 'test'),
        **kwargs,
    )


def test_refactored_search_option_helpers():
    assert resolve_max_results(_test_req_factory(max_results=3), default_count=5, max_count=10) == 3
    assert resolve_include_content(_test_req_factory(response_mode='search_with_content')) is True
    assert resolve_include_answer(_test_req_factory(response_mode='search_only')) is False
    assert resolve_searxng_time_range(_test_req_factory(time_range='month')) == 'month'
    assert resolve_serper_tbs(_test_req_factory(days=7)) == 'qdr:d7'
    assert resolve_search_depth(_test_req_factory(search_depth='advanced')) == 'advanced'


def test_refactored_scoring_rules():
    ranked = _new_test_item(
        rank=1,
        title='Lithium dendrite suppression mechanism',
        description='solid electrolyte interface study',
        scraped=True,
        content_chars=9000,
        content='This is about lithium dendrites and solid electrolyte interface.',
        published='2026-01-01',
    )
    unranked = _new_test_item(
        rank=10,
        title='Weather forecast',
        description='daily report',
        scraped=False,
        content_chars=120,
        content='Not related.',
        published=None,
    )
    assert score_item(ranked, 'lithium dendrite solid electrolyte interface') > score_item(
        unranked,
        'lithium dendrite solid electrolyte interface',
    )


def test_buckets_and_chunks_still_work():
    items = [
        _new_test_item(rank=1, content='a', scraped=True, url='https://a', title='A'),
        _new_test_item(rank=2, content='b', scraped=True, url='https://b', title='B'),
        _new_test_item(rank=3, content='', scraped=False, url='https://c', title='C'),
    ]
    assert resolve_max_chars_per_source(_test_req_factory(chunks_per_source=2)) == 1000
    buckets = split_result_buckets(items, max_sources=1)
    assert [item.title for item in buckets['not_summarized']] == ['B']
    assert [item.title for item in buckets['excluded_results']] == ['C']


def test_max_results_falls_back_to_count():
    assert resolve_max_results(_test_req_factory(count=12), default_count=5, max_count=10) == 10
