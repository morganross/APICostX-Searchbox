import pytest
from fastapi import HTTPException

import main


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
