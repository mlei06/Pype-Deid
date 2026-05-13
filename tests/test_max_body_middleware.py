"""Tests for :class:`~pypedeid.api.middleware.MaxBodySizeMiddleware`."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from pypedeid.api.middleware import MaxBodySizeMiddleware


def test_rejects_request_when_content_length_exceeds_cap() -> None:
    app = FastAPI()
    app.add_middleware(MaxBodySizeMiddleware, max_bytes=10)

    @app.post("/echo")
    def echo() -> dict[str, bool]:
        return {"ok": True}

    with TestClient(app) as client:
        r = client.post("/echo", content=b"x" * 20)
    assert r.status_code == 413
    assert "exceeds" in r.json()["detail"]


def test_allows_request_within_cap() -> None:
    app = FastAPI()
    app.add_middleware(MaxBodySizeMiddleware, max_bytes=10_000)

    @app.post("/echo")
    def echo() -> dict[str, bool]:
        return {"ok": True}

    with TestClient(app) as client:
        r = client.post("/echo", content=b"hello")
    assert r.status_code == 200
    assert r.json() == {"ok": True}
