import json
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient
from hypothesis import given, strategies as st

import main


async def _fake_summary(*_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    return {
        "found": True,
        "answer": "Test summary synthesized from all returned sources.",
        "highlights": ["All sources were considered."],
        "follow_up_questions": [],
        "confidence": 0.91,
    }


def _stub_item(**kwargs: Any) -> main.SearchItem:
    return main.SearchItem(
        rank=kwargs.pop("rank", 1),
        title=kwargs.pop("title", "Example title"),
        url=kwargs.pop("url", "https://example.com"),
        description=kwargs.pop("description", "Example description"),
        content=kwargs.pop("content", "Example content for science testing"),
        source=kwargs.pop("source", "web"),
        **kwargs,
    )


@pytest.mark.asyncio
async def test_post_search_returns_single_aggregate_result_and_usage(monkeypatch):
    calls: Dict[str, int] = {"advanced": 0}

    async def fake_run_search(_req: main.SearchRequest):
        return [_stub_item(source="serper")]

    async def fake_classify(_query: str, _llm_options=None, request_id=None, **_kwargs):
        return {
            "is_science": False,
            "raw_is_science": False,
            "confidence": 0.21,
            "category": "general",
            "reason": "test routing",
        }

    async def fake_run_advanced(_req: main.SearchRequest):
        calls["advanced"] += 1
        return [_stub_item(source="arxiv", title="Science fallback")]

    monkeypatch.setattr(main, "_run_search", fake_run_search)
    monkeypatch.setattr(main, "_classify_science_query", fake_classify)
    monkeypatch.setattr(main, "_run_advanced_search", fake_run_advanced)
    monkeypatch.setattr(main, "_summarize_query", _fake_summary)

    client = TestClient(main.app)
    response = client.post("/search", json={"query": "lithium dendrite interface", "include_usage": True})

    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "lithium dendrite interface"
    assert isinstance(body["results"], list)
    assert len(body["results"]) == 1
    assert body["results"][0]["url"].startswith("https://")
    assert body["results"][0]["searchbox_url"].startswith("searchbox://aggregate/")
    assert "# Summary" in body["results"][0]["content"]
    assert "Test summary synthesized" in body["results"][0]["content"]
    assert calls["advanced"] == 0
    assert body["usage"]["search_requests"] == 1
    assert body["usage"]["usage_evidence"]["schema_version"] == "searchbox-usage-evidence-v1"
    assert body["usage"]["usage_evidence"]["search"]["attempt_count"] >= 1
    assert response.headers["X-Searchbox-Usage-Evidence-Schema"] == "searchbox-usage-evidence-v1"
    assert int(response.headers["X-Searchbox-Usage-Search-Attempts"]) >= 1
    assert "serper_api_key" not in json.dumps(body).lower()


@pytest.mark.asyncio
async def test_post_search_routes_to_science_when_classifier_marks_science(monkeypatch):
    async def fake_run_search(_req: main.SearchRequest):
        return [_stub_item(source="serper", title="Science seed", rank=1)]

    async def fake_classify(_query: str, _llm_options=None, request_id=None, **_kwargs):
        return {
            "is_science": True,
            "raw_is_science": True,
            "confidence": 0.99,
            "category": "materials",
            "reason": "test routing",
        }

    async def fake_run_advanced(req: main.SearchRequest):
        return [
            _stub_item(
                source="serpapi_scholar",
                title="Science paper",
                url="https://example.com/paper.pdf",
                rank=1,
            ),
            _stub_item(
                source="serpapi_scholar",
                title="Second paper",
                url="https://example.com/paper-2.pdf",
                rank=2,
            ),
        ]

    monkeypatch.setattr(main, "_run_search", fake_run_search)
    monkeypatch.setattr(main, "_classify_science_query", fake_classify)
    monkeypatch.setattr(main, "_run_advanced_search", fake_run_advanced)
    monkeypatch.setattr(main, "_summarize_query", _fake_summary)

    client = TestClient(main.app)
    response = client.get("/search", params={"q": "lithium dendrite interface", "max_results": 2})

    assert response.status_code == 200
    body = response.json()
    assert body["results"][0]["url"].startswith("https://")
    assert body["results"][0]["searchbox_url"].startswith("searchbox://aggregate/")
    assert "# Scientific Context" in body["results"][0]["content"]
    assert "results" in body


@pytest.mark.asyncio
async def test_post_search_keeps_web_aggregate_when_science_provider_layer_fails(monkeypatch):
    async def fake_run_search(_req: main.SearchRequest):
        return [_stub_item(source="serper", title="Web source", rank=1)]

    async def fake_classify(_query: str, _llm_options=None, request_id=None, **_kwargs):
        return {"is_science": True, "confidence": 0.98, "reason": "test science"}

    async def fake_run_advanced(_req: main.SearchRequest):
        raise main.HTTPException(status_code=502, detail={"reason": "all_advanced_providers_failed"})

    monkeypatch.setattr(main, "_run_search", fake_run_search)
    monkeypatch.setattr(main, "_classify_science_query", fake_classify)
    monkeypatch.setattr(main, "_run_advanced_search", fake_run_advanced)
    monkeypatch.setattr(main, "_summarize_query", _fake_summary)

    client = TestClient(main.app)
    response = client.post("/search", json={"query": "lithium dendrite interface"})

    assert response.status_code == 200
    body = response.json()
    assert len(body["results"]) == 1
    content = body["results"][0]["content"]
    assert "# Retrieval Notes" in content
    assert "all_advanced_providers_failed" in content
    assert "# Web Context" in content


@pytest.mark.asyncio
async def test_search_raw_uses_one_aggregate_summary_contract(monkeypatch):
    async def fake_run_search(req: main.SearchRequest):
        assert req.include_content is True
        assert req.include_raw_content is True
        return [_stub_item(source="serper", title="Raw compatibility source")]

    async def fake_classify(_query: str, _llm_options=None, request_id=None, **_kwargs):
        return {"is_science": False, "confidence": 0.9, "reason": "test"}

    async def fake_run_advanced(_req: main.SearchRequest):
        raise AssertionError("non-science raw compatibility request should not call advanced providers")

    monkeypatch.setattr(main, "_run_search", fake_run_search)
    monkeypatch.setattr(main, "_classify_science_query", fake_classify)
    monkeypatch.setattr(main, "_run_advanced_search", fake_run_advanced)
    monkeypatch.setattr(main, "_summarize_query", _fake_summary)

    client = TestClient(main.app)
    response = client.get("/search-raw", params={"q": "compatibility query", "count": 3})

    assert response.status_code == 200
    body = response.json()
    assert len(body["results"]) == 1
    assert body["answer"] == "Test summary synthesized from all returned sources."
    assert body["results"][0]["url"].startswith("https://")
    assert body["results"][0]["searchbox_url"].startswith("searchbox://aggregate/")
    assert "# Summary" in body["results"][0]["content"]
    assert "# Web Context" in body["results"][0]["content"]


def test_search_raw_rejects_missing_serper_key(monkeypatch):
    monkeypatch.setattr(main, "SEARCH_PROVIDER", "serper")
    monkeypatch.setattr(main, "SERPER_API_KEY", "")

    client = TestClient(main.app)
    response = client.get("/search-raw", params={"q": "test term"})

    assert response.status_code == 500
    assert response.json()["detail"] == "SERPER_API_KEY is not configured"


def test_search_raw_rejects_unknown_provider(monkeypatch):
    monkeypatch.setattr(main, "SEARCH_PROVIDER", "mystery-provider")

    client = TestClient(main.app)
    response = client.get("/search-raw", params={"q": "test term"})

    assert response.status_code == 400
    assert response.json()["detail"].startswith("Unknown SEARCH_PROVIDER")


@given(st.text(min_size=0, max_size=3000))
def test_truncate_payload_property(text):
    limit = 120
    payload = main._truncate_payload(text, limit)
    assert len(payload) <= limit + len("\n[truncated]")
    if len(text) <= limit:
        assert payload == text
    else:
        assert payload.startswith(text[:limit])
