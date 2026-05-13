"""Auth/scope contract tests.

Boot the single API with real API keys configured and assert:

- Every mutating route (POST/PUT/DELETE/PATCH) returns 401 when called with no
  key or an unknown key.
- Inference-scoped callers cannot call admin routes (403).
- The deploy allowlist is enforced on ``/process/{name}`` for inference-scoped
  callers (403) but not for admin callers.
- ``/health`` stays open.

This is the guardrail from the design doc (§9.8): new mutating routes added
later must opt into an auth dep, or this test will catch them.
"""

from __future__ import annotations

import json

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

ADMIN_KEY = "test-admin-key"
INFERENCE_KEY = "test-inference-key"

MUTATING_METHODS = {"POST", "PUT", "DELETE", "PATCH"}

# Routes that are intentionally available to inference-scoped callers
# (not admin-only). Paths here are the FastAPI templated paths.
#
# ``POST /pipelines/pipe-types/{name}/labels`` uses POST because it takes a
# config body, but it's a read-only compute endpoint — label-space info, no
# server state changes. Leave it open to any authenticated caller.
INFERENCE_OK = {
    ("POST", "/pipelines/pipe-types/{name}/labels"),
    ("POST", "/process/redact"),
    ("POST", "/process/scrub"),
    ("POST", "/process/{pipeline_name}"),
    ("POST", "/process/{pipeline_name}/batch"),
}


@pytest.fixture
def secured_client(tmp_path, monkeypatch):
    """Client for an app with admin + inference keys configured."""
    data_dir = tmp_path / "data"
    db_file = data_dir / "app.sqlite"
    pipelines_dir = data_dir / "pipelines"
    evaluations_dir = data_dir / "evaluations"
    inference_runs_dir = data_dir / "inference_runs"
    corpora_dir = data_dir / "corpora"
    dictionaries_dir = data_dir / "dictionaries"
    for d in (
        pipelines_dir, evaluations_dir, inference_runs_dir,
        corpora_dir, dictionaries_dir,
    ):
        d.mkdir(parents=True)

    monkeypatch.setenv("PYPEDEID_DATABASE_URL", f"sqlite:///{db_file.as_posix()}")
    monkeypatch.setenv("PYPEDEID_PIPELINES_DIR", str(pipelines_dir))
    monkeypatch.setenv("PYPEDEID_MODES_PATH", str(data_dir / "modes.json"))
    monkeypatch.setenv("PYPEDEID_EVALUATIONS_DIR", str(evaluations_dir))
    monkeypatch.setenv("PYPEDEID_INFERENCE_RUNS_DIR", str(inference_runs_dir))
    monkeypatch.setenv("PYPEDEID_CORPORA_DIR", str(corpora_dir))
    monkeypatch.setenv("PYPEDEID_DICTIONARIES_DIR", str(dictionaries_dir))
    # pydantic-settings reads list envs as JSON arrays.
    monkeypatch.setenv("PYPEDEID_ADMIN_API_KEYS", json.dumps([ADMIN_KEY]))
    monkeypatch.setenv("PYPEDEID_INFERENCE_API_KEYS", json.dumps([INFERENCE_KEY]))

    from pypedeid.config import reset_settings
    from pypedeid.db import init_db, reset_engine

    reset_settings()
    reset_engine()
    init_db()

    from pypedeid.api.app import create_app

    app = create_app()
    with TestClient(app) as tc:
        yield tc, app


def _enumerate_mutating_routes(app) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for r in app.routes:
        if not isinstance(r, APIRoute):
            continue
        for m in r.methods or []:
            if m in MUTATING_METHODS:
                out.append((m, r.path))
    return out


def test_health_is_open(secured_client):
    client, _ = secured_client
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json().get("api_key_scope") is None


def test_health_reflects_api_key_scope(secured_client):
    client, _ = secured_client
    assert (
        client.get("/health", headers={"X-API-Key": ADMIN_KEY}).json()["api_key_scope"]
        == "admin"
    )
    assert (
        client.get("/health", headers={"X-API-Key": INFERENCE_KEY}).json()["api_key_scope"]
        == "inference"
    )


def test_docs_require_admin_when_auth_enabled(secured_client):
    client, _ = secured_client
    # Anonymous callers cannot access schema or UI.
    assert client.get("/docs").status_code == 401
    assert client.get("/redoc").status_code == 401
    assert client.get("/openapi.json").status_code == 401
    # Inference-scoped callers are rejected.
    hdr_inf = {"X-API-Key": INFERENCE_KEY}
    assert client.get("/docs", headers=hdr_inf).status_code == 403
    assert client.get("/openapi.json", headers=hdr_inf).status_code == 403
    # Admin callers can introspect.
    hdr_admin = {"X-API-Key": ADMIN_KEY}
    assert client.get("/docs", headers=hdr_admin).status_code == 200
    assert client.get("/redoc", headers=hdr_admin).status_code == 200
    assert client.get("/openapi.json", headers=hdr_admin).status_code == 200


def test_all_mutating_routes_require_auth(secured_client):
    """Every POST/PUT/DELETE route rejects unauthenticated callers."""
    client, app = secured_client
    routes = _enumerate_mutating_routes(app)
    assert routes, "no mutating routes discovered — contract test is broken"

    failures: list[str] = []
    for method, path in routes:
        # Concretize path params so FastAPI's router can match.
        concrete = path.replace("{", "__").replace("}", "")
        resp = client.request(method, concrete)
        if resp.status_code not in (401, 403):
            failures.append(f"{method} {path} → {resp.status_code}")

    assert not failures, (
        "routes that should have required auth but didn't:\n  "
        + "\n  ".join(failures)
    )


def test_inference_key_cannot_reach_admin_routes(secured_client):
    """An inference-scoped caller gets 403 on admin-only mutations."""
    client, app = secured_client
    routes = _enumerate_mutating_routes(app)

    failures: list[str] = []
    for method, path in routes:
        if (method, path) in INFERENCE_OK:
            continue
        concrete = path.replace("{", "__").replace("}", "")
        resp = client.request(
            method, concrete,
            headers={"X-API-Key": INFERENCE_KEY},
        )
        if resp.status_code != 403:
            failures.append(f"{method} {path} → {resp.status_code}")

    assert not failures, (
        "admin-only routes that accepted an inference key:\n  "
        + "\n  ".join(failures)
    )


def test_process_allowlist_blocks_inference_scope(secured_client, tmp_path):
    """Inference scope can only call pipelines on the deploy allowlist."""
    client, _ = secured_client

    data_dir = tmp_path / "data"
    pipelines_dir = data_dir / "pipelines"
    (pipelines_dir / "secret.json").write_text(json.dumps({
        "pipes": [{"type": "regex_ner"}],
    }))

    # No allowlist written → everything allowed. Now write a modes.json that
    # allowlists a different pipeline and confirm "secret" is rejected for
    # inference callers but accepted for admin.
    modes = {
        "modes": {"fast": {"pipeline": "secret"}},
        "default_mode": "fast",
        "allowed_pipelines": ["only-this-one"],
    }
    (data_dir / "modes.json").write_text(json.dumps(modes))

    inf = client.post(
        "/process/secret",
        json={"text": "hello"},
        headers={"X-API-Key": INFERENCE_KEY},
    )
    assert inf.status_code == 403, inf.text

    adm = client.post(
        "/process/secret",
        json={"text": "hello"},
        headers={"X-API-Key": ADMIN_KEY},
    )
    # Admin bypasses the allowlist; the call should succeed (200) since
    # the pipeline file exists and regex_ner is always registered.
    assert adm.status_code == 200, adm.text


def test_inference_blocked_from_admin_read_routes(secured_client):
    """Inference keys cannot list pipelines, deploy config, dicts, or models."""
    client, _ = secured_client
    hdr = {"X-API-Key": INFERENCE_KEY}
    assert client.get("/pipelines", headers=hdr).status_code == 403
    assert client.get("/pipelines/foo", headers=hdr).status_code == 403
    assert client.get("/deploy", headers=hdr).status_code == 403
    assert client.get("/deploy/pipelines", headers=hdr).status_code == 403
    assert client.get("/dictionaries", headers=hdr).status_code == 403
    assert client.get("/models", headers=hdr).status_code == 403


def test_inference_can_reach_deploy_health_and_audit_reads(secured_client):
    """Production-style callers may read mode health and audit query endpoints."""
    client, _ = secured_client
    hdr = {"X-API-Key": INFERENCE_KEY}
    assert client.get("/deploy/health", headers=hdr).status_code == 200
    assert client.get("/audit/logs", headers=hdr).status_code == 200
    assert client.get("/audit/stats", headers=hdr).status_code == 200
