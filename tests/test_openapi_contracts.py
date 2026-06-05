from fastapi.testclient import TestClient

import main


def _openapi() -> dict:
    """Load OpenAPI contract JSON for assertions."""
    return main.app.openapi()


def test_openapi_contracts_cover_search_and_health_apis():
    spec = _openapi()

    paths = spec["paths"]
    assert "/search" in paths
    assert "/search-summary" in paths
    assert "/search-raw" in paths
    assert "/health" in paths
    assert "/health/monitor" in paths

    search_post = paths["/search"]["post"]
    request_ref = search_post["requestBody"]["content"]["application/json"]["schema"].get("$ref")
    response_ref = search_post["responses"]["200"]["content"]["application/json"]["schema"].get("$ref")
    assert request_ref == "#/components/schemas/SearchRequest"
    assert response_ref == "#/components/schemas/TavilySearchResponse"

    search_summary = paths["/search-summary"]["post"]
    summary_request_ref = search_summary["requestBody"]["content"]["application/json"]["schema"].get("$ref")
    summary_response_ref = search_summary["responses"]["200"]["content"]["application/json"]["schema"].get("$ref")
    assert summary_request_ref == "#/components/schemas/SearchSummaryRequest"
    assert summary_response_ref == "#/components/schemas/SearchSummaryResponse"

    assert "TavilySearchResponse" in spec["components"]["schemas"]


def test_openapi_route_is_public_and_stable_json_contract():
    client = TestClient(main.app)
    response = client.get("/openapi.json")

    assert response.status_code == 200
    payload = response.json()
    assert payload["openapi"].startswith("3.")
    assert payload["components"]["schemas"]["SearchRequest"]["properties"]["query"]["maxLength"] == 512
    assert payload["components"]["schemas"]["SearchSummaryRequest"]["properties"]["query"]["maxLength"] == 512
    assert payload["components"]["schemas"]["SearchSummaryResponse"]["properties"]["provider"]["type"] == "string"
