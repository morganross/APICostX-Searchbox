import json

from fastapi.testclient import TestClient

import main


def test_health_is_public_safe():
    client = TestClient(main.app)
    response = client.get('/health')
    assert response.status_code == 200
    payload = response.json()
    assert payload['status'] == 'ok'
    body = json.dumps(payload)
    assert 'api_key' not in body.lower()


def test_config_does_not_expose_secret_values(monkeypatch):
    monkeypatch.setattr(main, 'SERPAPI_API_KEY', 'test-secret-value')
    client = TestClient(main.app)
    response = client.get('/config')
    assert response.status_code == 200
    body = json.dumps(response.json())
    assert 'test-secret-value' not in body
    assert 'serpapi_configured' in body


def test_advanced_provider_monthly_quota_snapshot_shape(tmp_path, monkeypatch):
    quota_file = tmp_path / 'monthly.json'
    monkeypatch.setattr(main, 'ADVANCED_PROVIDER_MONTHLY_QUOTA_FILE', str(quota_file))
    monkeypatch.setattr(main, 'SERPAPI_MONTHLY_REQUEST_LIMIT', 250)
    snapshot = main._advanced_provider_monthly_quota_snapshot()
    assert snapshot['serpapi_scholar']['limit'] == 250
    assert snapshot['serpapi_scholar']['used'] == 0
    assert snapshot['serpapi_scholar']['remaining'] == 250


def test_single_aggregate_url_contract():
    request_id = 'test-request'
    item = main.SearchItem(
        rank=1,
        title='Example',
        url='https://example.com',
        content='Example content',
        source='test',
    )
    aggregate = main._build_aggregate_search_result(query='example query', request_id=request_id, web_results=[item], science_results=[], classifier_result={}, use_science=False)
    assert aggregate.url == 'searchbox://aggregate/test-request'
    assert aggregate.title.startswith('Searchbox research context for:')
