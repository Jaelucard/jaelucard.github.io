"""The server has no login, so it refuses requests another website could forge."""

from __future__ import annotations


def test_cross_origin_post_is_refused(client):
    response = client.post("/", headers={"Origin": "https://evil.example"})
    assert response.status_code == 403


def test_cross_site_fetch_metadata_is_refused(client):
    response = client.post("/", headers={"Sec-Fetch-Site": "cross-site"})
    assert response.status_code == 403


def test_null_origin_is_refused(client):
    assert client.post("/", headers={"Origin": "null"}).status_code == 403


def test_same_origin_post_passes_the_check(client):
    response = client.post("/", headers={"Origin": "http://127.0.0.1:8765", "Sec-Fetch-Site": "same-origin"})
    assert response.status_code == 405  # reached routing; "/" only answers GET


def test_unknown_host_is_refused(client):
    assert client.get("/", headers={"Host": "evil.example:8765"}).status_code == 400


def test_localhost_host_is_allowed(client):
    assert client.get("/", headers={"Host": "localhost:8765"}).status_code == 200


def test_pages_cannot_be_framed(client):
    response = client.get("/")
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]


def test_api_docs_are_disabled(client):
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404, path
