"""API key authentication and scope enforcement.

Design:

- Two scopes: ``admin`` (full API) and ``inference`` (``/process/*`` + deploy health +
  audit reads + ``POST /pipelines/pipe-types/{name}/labels``, subject to the deploy
  allowlist on process routes).
- Keys are configured via ``PYPEDEID_ADMIN_API_KEYS`` and
  ``PYPEDEID_INFERENCE_API_KEYS`` (JSON arrays or pydantic-settings list envs).
- When **both** lists are empty, auth is **disabled** — every request is served as
  if presented by an admin. This preserves local dev and the existing test suite.
- Keys are accepted as ``Authorization: Bearer <key>`` or ``X-API-Key: <key>``.
  Admin keys also satisfy inference-scoped routes.
- The matched key is returned as a short hashed ``client_id`` for audit use; the
  raw key is never logged.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal

from fastapi import Depends, Header, HTTPException

from pypedeid.config import get_settings

Scope = Literal["admin", "inference"]


@dataclass(frozen=True)
class AuthenticatedCaller:
    """Result of a successful auth check.

    ``scope`` is whatever the caller's key authorised. When auth is disabled,
    a synthetic ``admin`` caller is returned so dep-gated routes stay open.
    """

    id: str
    scope: Scope


def auth_enabled() -> bool:
    """``True`` if either admin or inference keys are configured."""
    s = get_settings()
    return bool(s.admin_api_keys) or bool(s.inference_api_keys)


def _client_id(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:12]


def _extract_key(authorization: str | None, x_api_key: str | None) -> str | None:
    if x_api_key:
        return x_api_key
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip() or None
    return None


def _require_scope(required: Scope, authorization: str | None, x_api_key: str | None) -> AuthenticatedCaller:
    if not auth_enabled():
        return AuthenticatedCaller(id="", scope="admin")

    key = _extract_key(authorization, x_api_key)
    if not key:
        raise HTTPException(status_code=401, detail="missing API key")

    s = get_settings()
    if key in s.admin_api_keys:
        return AuthenticatedCaller(id=_client_id(key), scope="admin")
    if required == "inference" and key in s.inference_api_keys:
        return AuthenticatedCaller(id=_client_id(key), scope="inference")

    raise HTTPException(status_code=403, detail="insufficient scope")


def require_admin_dep(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> AuthenticatedCaller:
    return _require_scope("admin", authorization, x_api_key)


def require_inference_dep(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> AuthenticatedCaller:
    return _require_scope("inference", authorization, x_api_key)


def require_authenticated_dep(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> AuthenticatedCaller:
    """Accept any configured scope. When auth is disabled, returns synthetic admin."""
    if not auth_enabled():
        return AuthenticatedCaller(id="", scope="admin")

    key = _extract_key(authorization, x_api_key)
    if not key:
        raise HTTPException(status_code=401, detail="missing API key")

    s = get_settings()
    if key in s.admin_api_keys:
        return AuthenticatedCaller(id=_client_id(key), scope="admin")
    if key in s.inference_api_keys:
        return AuthenticatedCaller(id=_client_id(key), scope="inference")

    raise HTTPException(status_code=401, detail="invalid API key")


def require_admin_or_inference_dep(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> AuthenticatedCaller:
    """Accept admin or inference keys (for shared read/compute routes like ``GET /deploy/health``)."""
    if not auth_enabled():
        return AuthenticatedCaller(id="", scope="admin")

    key = _extract_key(authorization, x_api_key)
    if not key:
        raise HTTPException(status_code=401, detail="missing API key")

    s = get_settings()
    if key in s.admin_api_keys:
        return AuthenticatedCaller(id=_client_id(key), scope="admin")
    if key in s.inference_api_keys:
        return AuthenticatedCaller(id=_client_id(key), scope="inference")

    raise HTTPException(status_code=401, detail="invalid API key")


def get_api_key_scope_for_health(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> Scope | None:
    """Reflect which scope the request key has, without requiring a key.

    Used by ``GET /health`` so UIs can enable admin-only actions (e.g. dataset
    register) when ``VITE_API_KEY`` is an admin key, and keep them disabled for
    inference-scoped keys.

    - When auth is **disabled** (no keys configured), returns ``"admin"`` so
      local dev matches full access.
    - When auth is **enabled** and no key is sent, returns ``None``.
    - When auth is **enabled** and the key is unknown, returns ``None``.
    """
    if not auth_enabled():
        return "admin"

    key = _extract_key(authorization, x_api_key)
    if not key:
        return None

    s = get_settings()
    if key in s.admin_api_keys:
        return "admin"
    if key in s.inference_api_keys:
        return "inference"
    return None


# Convenient ``Depends(...)`` sentinels for route signatures.
require_admin = Depends(require_admin_dep)
require_inference = Depends(require_inference_dep)
require_authenticated = Depends(require_authenticated_dep)
require_admin_or_inference = Depends(require_admin_or_inference_dep)

# Type alias for readability in route signatures (caller param annotation stays
# ``AuthenticatedCaller`` — the ``Depends`` sentinel is the default value).
AdminCaller = AuthenticatedCaller
InferenceCaller = AuthenticatedCaller
