"""Tests for the Allegro REST API client."""

from __future__ import annotations

import json

import httpx
import pytest

from allegro_evaluate.api import AllegroAPIClient, AllegroAPIError
from allegro_evaluate.models import Listing


class MockTransport(httpx.BaseTransport):
    """Mock httpx transport that returns canned responses."""

    def __init__(self, responses: dict[str, httpx.Response]):
        self.responses = responses
        self.requests: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key = f"{request.method} {request.url}"
        if key in self.responses:
            return self.responses[key]
        return self.responses.get("default", httpx.Response(404, json={"error": "not mocked"}))


def _ok(content: dict) -> httpx.Response:
    return httpx.Response(200, json=content)


def _err(status: int, message: str = "error") -> httpx.Response:
    return httpx.Response(status, json={"error": message})


def test_token_fetch_and_caching():
    """First call fetches token, subsequent calls reuse it."""
    token_response = _ok({"access_token": "test-token-123", "expires_in": 7200})
    search_response = _ok({
        "items": {
            "promoted": [],
            "regular": [{
                "id": "1234567890",
                "name": "Test Laptop",
                "sellingMode": {"price": {"amount": "2999.00"}},
                "parameters": [],
                "images": [{"url": "https://example.com/img.jpg"}]
            }]
        }
    })

    transport = MockTransport({
        "POST https://allegro.pl/auth/oauth/token": token_response,
        "GET https://api.allegro.pl/offers/listing?phrase=laptop&limit=10&offset=0": search_response,
    })
    http = httpx.Client(transport=transport)

    client = AllegroAPIClient("test-id", "test-secret", http_client=http)
    listings1 = client.search("laptop", limit=10)
    listings2 = client.search("laptop", limit=10)

    assert len(listings1) == 1
    assert listings1[0].title == "Test Laptop"
    assert listings1[0].price == 2999.0
    assert listings1[0].id == "1234567890"
    # Token endpoint called only once
    post_requests = [r for r in transport.requests if r.method == "POST"]
    assert len(post_requests) == 1


def test_search_respects_limit():
    """Limit parameter is passed to API."""
    transport = MockTransport({
        "POST https://allegro.pl/auth/oauth/token": _ok({"access_token": "t", "expires_in": 7200}),
        "GET https://api.allegro.pl/offers/listing?phrase=laptop&limit=25&offset=0": _ok({
            "items": {"promoted": [], "regular": [{"id": str(i), "name": f"Item {i}", "sellingMode": {"price": {"amount": "100"}}, "parameters": [], "images": []} for i in range(50)]}
        }),
    })
    http = httpx.Client(transport=transport)
    client = AllegroAPIClient("test-id", "test-secret", http_client=http)

    client.search("laptop", limit=25)

    # Check the GET request had limit=25
    get_requests = [r for r in transport.requests if r.method == "GET"]
    assert len(get_requests) == 1
    assert "limit=25" in str(get_requests[0].url)


def test_api_error_raises():
    """Non-200 responses raise AllegroAPIError."""
    transport = MockTransport({
        "POST https://allegro.pl/auth/oauth/token": _ok({"access_token": "t", "expires_in": 7200}),
        "GET https://api.allegro.pl/offers/listing?phrase=laptop&limit=10&offset=0": _err(500, "server error"),
    })
    http = httpx.Client(transport=transport)
    client = AllegroAPIClient("test-id", "test-secret", http_client=http)

    with pytest.raises(AllegroAPIError) as excinfo:
        client.search("laptop", limit=10)

    assert "500" in str(excinfo.value)


def test_parse_listings_handles_promoted_and_regular():
    """Both promoted and regular items are parsed."""
    transport = MockTransport({
        "POST https://allegro.pl/auth/oauth/token": _ok({"access_token": "t", "expires_in": 7200}),
        "GET https://api.allegro.pl/offers/listing?phrase=laptop&limit=10&offset=0": _ok({
            "items": {
                "promoted": [{
                    "id": "promo1",
                    "name": "Promoted Item",
                    "sellingMode": {"price": {"amount": "1000"}},
                    "parameters": [{"name": "Color", "values": ["Black"]}],
                    "images": [{"url": "https://example.com/promo.jpg"}]
                }],
                "regular": [{
                    "id": "reg1",
                    "name": "Regular Item",
                    "sellingMode": {"price": {"amount": "500"}},
                    "parameters": [],
                    "images": []
                }]
            }
        }),
    })
    http = httpx.Client(transport=transport)
    client = AllegroAPIClient("test-id", "test-secret", http_client=http)

    listings = client.search("laptop", limit=10)

    assert len(listings) == 2
    assert listings[0].id == "promo1"
    assert listings[0].title == "Promoted Item"
    assert listings[0].price == 1000.0
    assert "Color: Black" in listings[0].description
    assert listings[1].id == "reg1"


def test_parse_listing_missing_fields():
    """Items with missing optional fields don't crash."""
    transport = MockTransport({
        "POST https://allegro.pl/auth/oauth/token": _ok({"access_token": "t", "expires_in": 7200}),
        "GET https://api.allegro.pl/offers/listing?phrase=laptop&limit=10&offset=0": _ok({
            "items": {
                "promoted": [],
                "regular": [{
                    "id": "123",
                    "name": "Minimal Item",
                    # no sellingMode, no parameters, no images
                }]
            }
        }),
    })
    http = httpx.Client(transport=transport)
    client = AllegroAPIClient("test-id", "test-secret", http_client=http)

    listings = client.search("laptop", limit=10)

    assert len(listings) == 1
    assert listings[0].id == "123"
    assert listings[0].title == "Minimal Item"
    assert listings[0].price is None
    assert listings[0].description == ""
    assert listings[0].image_url is None