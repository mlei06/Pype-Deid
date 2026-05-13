"""Dataset HTTP API — organized by concern across sub-modules.

All sub-modules share a single ``APIRouter`` so every route stays under the same
``/datasets`` prefix. Import order matters: fixed paths must register before any
``/{name}`` parametric path so FastAPI picks the literal match first.
"""

from __future__ import annotations

from fastapi import APIRouter

from pypedeid.api.auth import require_admin

router = APIRouter(
    prefix="/datasets", tags=["datasets"], dependencies=[require_admin]
)

# Register routes by importing submodules. Order matters — fixed paths before
# ``/{name}`` parametric routes.
from pypedeid.api.routers.datasets import list_and_import  # noqa: E402, F401
from pypedeid.api.routers.datasets import compose_transform  # noqa: E402, F401
from pypedeid.api.routers.datasets import generate  # noqa: E402, F401
from pypedeid.api.routers.datasets import preview_labels  # noqa: E402, F401
from pypedeid.api.routers.datasets import upload  # noqa: E402, F401
from pypedeid.api.routers.datasets import by_name  # noqa: E402, F401

__all__ = ["router"]
