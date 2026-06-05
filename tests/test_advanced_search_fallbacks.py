from typing import Any, Dict, List

import pytest
from fastapi import HTTPException
from hypothesis import given, strategies as st

import main


def _fake_item(*, source: str, rank: int = 1, url: str = "https://example.com/paper") -> main.SearchItem:
    return main.SearchItem(
        rank=rank,
        title=f"{source} source",
        url=f"{url}-{source}",
        description="science paper summary",
        content="Extracted content for regression coverage.",
        source=source,
        engine=f"{source}_engine",
        scraped=True,
        content_chars=120,
        quality_flags=["advanced_search"],
    )


def test_classify_science_payload_normalizes_aliases_and_threshold(monkeypatch: Any):
    monkeypatch.setattr(main, "SCIENCE_CLASSIFIER_CONFIDENCE_THRESHOLD", 0.75)

    from_alias = main._normalize_science_classifier_payload(
        {"science": "true", "confidence": 0.92, "category": "materials", "reason": "term match"}
    )
    assert from_alias["is_science"] is True
    assert from_alias["raw_is_science"] is True
    assert from_alias["confidence"] == 0.92
    assert from_alias["category"] == "materials"

    below_threshold = main._normalize_science_classifier_payload(
        {"scientific": 1, "confidence": 0.74, "reason": "close"}
    )
    assert below_threshold["is_science"] is False
    assert below_threshold["raw_is_science"] is True


@given(
    st.dictionaries(
        st.text(min_size=1, max_size=24),
        st.one_of(
            st.none(),
            st.booleans(),
            st.integers(),
            st.floats(min_value=-2, max_value=2, allow_nan=False),
            st.text(min_size=1, max_size=12),
        ),
        min_size=0,
        max_size=6,
    )
)
def test_normalize_science_classifier_payload_stability(random_payload: Dict[str, Any]) -> None:
    normalized = main._normalize_science_classifier_payload(random_payload)
    assert isinstance(normalized["is_science"], bool)
    assert isinstance(normalized["raw_is_science"], bool)
    assert isinstance(normalized["confidence"], float)
    assert 0.0 <= normalized["confidence"] <= 1.0
    assert isinstance(normalized["category"], str)
    assert isinstance(normalized["reason"], str)


@pytest.mark.asyncio
async def test_run_advanced_search_auto_uses_fallback_chain(monkeypatch: Any):
    calls: List[str] = []

    async def fake_provider(provider: str, req: main.SearchRequest) -> List[main.SearchItem]:
        calls.append(provider)
        if provider == "sciencestack":
            return [_fake_item(source="sciencestack", rank=1)]
        if provider == "searchapi_scholar":
            return []
        if provider == "serpapi_scholar":
            return [_fake_item(source="serpapi_scholar", rank=2)]
        return [_fake_item(source=provider, rank=3)]

    monkeypatch.setattr(main, "_call_advanced_provider", fake_provider)
    monkeypatch.setattr(main, "_advanced_provider_cooldown_remaining", lambda _: 0)
    monkeypatch.setattr(
        main,
        "ADVANCED_SEARCH_AUTO_PROVIDER_ORDER",
        ["sciencestack", "searchapi_scholar", "serpapi_scholar", "agentic_data"],
    )
    monkeypatch.setattr(main, "ADVANCED_SEARCH_AUTO_MIN_PROVIDERS", 2)
    monkeypatch.setattr(main, "ADVANCED_SEARCH_AUTO_MAX_PROVIDERS", 4)

    req = main.SearchRequest(query="lithium dendrite interface", max_results=2, count=2)
    results = await main._run_advanced_search_auto(req)

    assert [r.url for r in results] == [
        "https://example.com/paper-sciencestack",
        "https://example.com/paper-serpapi_scholar",
    ]
    assert [item.source for item in results] == ["sciencestack", "serpapi_scholar"]
    assert calls == ["sciencestack", "searchapi_scholar", "serpapi_scholar"]
    assert "advanced_auto_provider:sciencestack" in (results[0].quality_flags or [])
    assert "advanced_auto_provider:serpapi_scholar" in (results[1].quality_flags or [])


@pytest.mark.asyncio
async def test_run_advanced_search_auto_respects_cooldown_skips(monkeypatch: Any):
    calls: List[str] = []

    async def fake_provider(provider: str, req: main.SearchRequest) -> List[main.SearchItem]:
        calls.append(provider)
        return [_fake_item(source=provider, rank=1)]

    def fake_cooldown(provider: str) -> int:
        if provider == "sciencestack":
            return 120
        return 0

    monkeypatch.setattr(main, "_call_advanced_provider", fake_provider)
    monkeypatch.setattr(main, "_advanced_provider_cooldown_remaining", fake_cooldown)
    monkeypatch.setattr(
        main,
        "ADVANCED_SEARCH_AUTO_PROVIDER_ORDER",
        ["sciencestack", "searchapi_scholar", "serpapi_scholar"],
    )
    monkeypatch.setattr(main, "ADVANCED_SEARCH_AUTO_MIN_PROVIDERS", 2)
    monkeypatch.setattr(main, "ADVANCED_SEARCH_AUTO_MAX_PROVIDERS", 4)

    req = main.SearchRequest(query="quantum battery", max_results=2, count=2)
    results = await main._run_advanced_search_auto(req)

    assert calls == ["searchapi_scholar", "serpapi_scholar"]
    assert len(results) == 2


@pytest.mark.asyncio
async def test_run_advanced_search_auto_fails_fast_when_no_provider_returns_results(monkeypatch: Any):
    async def fake_provider(_provider: str, _req: main.SearchRequest) -> List[main.SearchItem]:
        return []

    monkeypatch.setattr(main, "_call_advanced_provider", fake_provider)
    monkeypatch.setattr(main, "_advanced_provider_cooldown_remaining", lambda _: 0)
    monkeypatch.setattr(main, "ADVANCED_SEARCH_AUTO_PROVIDER_ORDER", ["sciencestack", "searchapi_scholar"])
    monkeypatch.setattr(main, "ADVANCED_SEARCH_AUTO_MIN_PROVIDERS", 1)
    monkeypatch.setattr(main, "ADVANCED_SEARCH_AUTO_MAX_PROVIDERS", 2)

    req = main.SearchRequest(query="irrelevant query", max_results=1, count=1)
    with pytest.raises(HTTPException) as exc:
        await main._run_advanced_search_auto(req)

    assert exc.value.status_code == 502
    assert exc.value.detail["reason"] == "all_advanced_providers_failed"


@pytest.mark.asyncio
async def test_run_advanced_search_rejects_unknown_source(monkeypatch: Any):
    req = main.SearchRequest(query="query", topic="no_such_source", max_results=1, count=1)
    with pytest.raises(HTTPException) as exc:
        await main._run_advanced_search(req)

    assert exc.value.status_code == 400
    assert "not supported" in str(exc.value.detail)
