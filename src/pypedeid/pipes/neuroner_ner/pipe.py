"""NeuroNER LSTM-CRF detector pipe (Docker HTTP sidecar).

Inference talks to ``neuroner-cspmc/sidecar`` (see ``PYPEDEID_NEURONER_HTTP_URL``).
Training still uses ``scripts/neuroner_train.sh`` and a local Python 3.7 venv.
"""

from __future__ import annotations

import json
import logging
import pickle
import threading
import time
from pathlib import Path
from typing import Any

import urllib.error
import urllib.request
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field

from pypedeid.domain import AnnotatedDocument, EntitySpan
from pypedeid.pipes.base import ConfigurablePipe
from pypedeid.pipes.detector_label_mapping import (
    accumulate_spans,
    apply_detector_label_mapping,
    detector_label_mapping_field,
    effective_detector_labels,
)
from pypedeid.pipes.ui_schema import field_ui

logger = logging.getLogger(__name__)


def _extract_unique_entity_labels_from_dataset_pickle(pickle_path: Path) -> set[str]:
    """Entity names from ``dataset.pickle`` (BIOES prefixes stripped).

    Matches ``scripts/neuroner_export.extract_labels`` so UI label space matches exports.
    """
    with pickle_path.open("rb") as f:
        ds = pickle.load(f)
    labels: set[str] = set()
    for label in ds.unique_labels:
        if label == "O":
            continue
        if isinstance(label, str) and len(label) >= 2 and label[:2] in ("B-", "I-", "E-", "S-"):
            labels.add(label[2:])
        else:
            labels.add(label)
    return labels


def read_raw_neuroner_entity_labels(model_folder: Path) -> list[str]:
    """Load raw entity type names from an exported model directory (no TF load).

    Prefer ``model_manifest.json`` (written by ``scripts/neuroner_export``); fall back to
    ``dataset.pickle`` in the same directory.
    """
    manifest = model_folder / "model_manifest.json"
    if manifest.is_file():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            raw = data.get("labels")
            if isinstance(raw, list) and all(isinstance(x, str) for x in raw):
                return sorted(set(raw))
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    pickle_path = model_folder / "dataset.pickle"
    if pickle_path.is_file():
        try:
            return sorted(_extract_unique_entity_labels_from_dataset_pickle(pickle_path))
        except Exception:
            pass
    return []


# ── Runtime availability check (called by registry.pipe_availability) ─────

def check_neuroner_ready() -> tuple[bool, dict[str, Any]]:
    """Check whether the NeuroNER Docker sidecar and host assets are available.

    Verifies the HTTP sidecar responds at :envvar:`PYPEDEID_NEURONER_HTTP_URL` and that
    host ``models/neuroner/`` and GloVe embeddings exist (for manifests and compose mounts).
    """
    from pypedeid.config import get_settings
    from pypedeid.env_file import resolve_repo_root

    root = resolve_repo_root() or Path.cwd()
    settings = get_settings()
    base = settings.neuroner_http_url.rstrip("/")

    http_ok = False
    try:
        req = urllib.request.Request(base + "/health", method="GET")
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            http_ok = 200 <= resp.status < 300
    except Exception:
        http_ok = False

    models_dir = (root / "models/neuroner").resolve()
    models_found = (
        sorted(p.name for p in models_dir.iterdir() if p.is_dir())
        if models_dir.exists()
        else []
    )
    models_ok = len(models_found) > 0
    embedding = (root / "data/word_vectors/glove.6B.100d.txt").resolve()
    embedding_ok = embedding.exists() and embedding.is_file()

    details: dict[str, Any] = {
        "neuroner_http": {
            "ok": http_ok,
            "url": base,
        },
        "models": {
            "ok": models_ok,
            "path": str(models_dir),
            "found": models_found,
        },
        "embeddings": {
            "ok": embedding_ok,
            "path": str(embedding),
        },
    }
    all_ok = http_ok and models_ok and embedding_ok
    return all_ok, details


# ── Default entity mapping: neuroner i2b2 labels → pypedeid labels ──

DEFAULT_ENTITY_MAP: dict[str, str] = {
    # Person names
    "DOCTOR": "NAME",
    "PATIENT": "NAME",
    "USERNAME": "NAME",
    # Dates / age
    "DATE": "DATE",
    "AGE": "AGE",
    # Locations
    "HOSPITAL": "HOSPITAL",
    "CITY": "LOCATION",
    "STATE": "LOCATION",
    "COUNTRY": "LOCATION",
    "STREET": "LOCATION",
    "ZIP": "LOCATION",
    "LOCATION_OTHER": "LOCATION",
    "ORGANIZATION": "ORGANIZATION",
    # Identifiers
    "MEDICALRECORD": "ID",
    "IDNUM": "ID",
    "BIOID": "ID",
    "DEVICE": "ID",
    "HEALTHPLAN": "ID",
    # Contact
    "PHONE": "PHONE",
    "FAX": "PHONE",
    "EMAIL": "EMAIL",
    "URL": "URL",
    # Professional
    "PROFESSION": "PROFESSION",
}


def default_base_labels() -> list[str]:
    """Default label space for the neuroner_ner detector."""
    return sorted(set(DEFAULT_ENTITY_MAP.values()))


def list_neuroner_model_names() -> list[str]:
    """Names of NeuroNER model directories under ``models/neuroner/`` (for select widgets)."""
    from pypedeid.config import get_settings

    models_dir = (get_settings().models_dir / "neuroner").resolve()
    if not models_dir.is_dir():
        return []
    return sorted(p.name for p in models_dir.iterdir() if p.is_dir())


def build_neuroner_label_space_bundle() -> dict[str, Any]:
    """Payload for the generic ``GET …/neuroner_ner/label-space-bundle``.

    ``labels_by_model`` holds raw NeuroNER tags from each ``model_manifest.json``;
    the client merges with ``default_entity_map`` to project to canonical PHI labels.
    """
    from pypedeid.config import get_settings
    from pypedeid.models import list_models

    labels_by_model: dict[str, list[str]] = {}
    for info in list_models(get_settings().models_dir, framework="neuroner"):
        labels_by_model[info.name] = sorted(info.labels)
    cfg = NeuroNerConfig()
    return {
        "labels_by_model": labels_by_model,
        "default_entity_map": dict(DEFAULT_ENTITY_MAP),
        "default_model": cfg.model,
    }


class NeuroNerConfig(BaseModel):
    """Configuration for the NeuroNER LSTM-CRF detector pipe.

    Inference uses the **Docker HTTP sidecar** (
        ``docker compose -f neuroner-cspmc/sidecar/compose.yaml``
    ).
    Set :envvar:`PYPEDEID_NEURONER_HTTP_URL` or ``base_url`` if the sidecar is not on
    ``http://127.0.0.1:8765``.

    Training uses ``scripts/neuroner_train.sh`` and the local NeuroNER venv from
    ``scripts/setup_neuroner.sh`` — not this pipe config.
    """

    model_config = ConfigDict(protected_namespaces=(), extra="ignore")

    base_url: str = Field(
        default="",
        description=(
            "NeuroNER sidecar base URL. "
            "Empty uses PYPEDEID_NEURONER_HTTP_URL (default http://127.0.0.1:8765)."
        ),
        json_schema_extra=field_ui(
            ui_group="Sidecar",
            ui_order=0,
            ui_widget="text",
            ui_help="HTTP endpoint of the NeuroNER Docker service",
        ),
    )

    model: str = Field(
        default="i2b2_2014_glove_spacy_bioes",
        description="Name of the NeuroNER trained model directory (must match the sidecar mount).",
        json_schema_extra=field_ui(
            ui_group="Model",
            ui_order=1,
            ui_widget="select",
            ui_help="Model name from models/neuroner/",
            ui_options_source="neuroner_models",
        ),
    )

    model_folder: str = Field(
        default="",
        description=(
            "Optional absolute path inside the Docker sidecar to the pretrained model directory "
            "(e.g. /models/neuroner/my_model). If set, the sidecar uses this instead of ``model`` "
            "for inference; must lie under the mounted models root."
        ),
        json_schema_extra=field_ui(
            ui_group="Model",
            ui_order=2,
            ui_widget="text",
            ui_advanced=True,
            ui_help="Leave empty to use ``model`` (subdirectory name only).",
        ),
    )

    models_dir: str = Field(
        default="models/neuroner",
        description=(
            "Directory containing NeuroNER model folders "
            "(relative to the repo root if discoverable, else CWD, or absolute)."
        ),
        json_schema_extra=field_ui(
            ui_group="Model",
            ui_order=3,
            ui_widget="text",
            ui_advanced=True,
        ),
    )

    startup_timeout: float = Field(
        default=120.0,
        description="Maximum seconds to wait for the NeuroNER HTTP sidecar to become ready.",
        json_schema_extra=field_ui(
            ui_group="Performance",
            ui_order=1,
            ui_widget="number",
            ui_advanced=True,
        ),
    )

    predict_timeout: float = Field(
        default=60.0,
        description="Maximum seconds to wait for a single prediction.",
        json_schema_extra=field_ui(
            ui_group="Performance",
            ui_order=2,
            ui_widget="number",
            ui_advanced=True,
        ),
    )

    entity_map: dict[str, str] = Field(
        default_factory=lambda: dict(DEFAULT_ENTITY_MAP),
        description=(
            "Map NeuroNER entity labels to project PHI labels. "
            "Unmapped labels pass through as-is."
        ),
        json_schema_extra=field_ui(
            ui_group="Entities & mapping",
            ui_order=1,
            ui_widget="key_value",
            ui_advanced=True,
        ),
    )

    source_name: str = Field(
        default="neuroner_ner",
        json_schema_extra=field_ui(
            ui_group="General",
            ui_widget="text",
            ui_advanced=True,
        ),
    )

    label_mapping: dict[str, str | None] = detector_label_mapping_field()

    skip_overlapping: bool = Field(
        default=False,
        description="Drop new spans that overlap any existing span in the document.",
        json_schema_extra=field_ui(
            ui_group="General",
            ui_order=99,
            ui_widget="switch",
        ),
    )


class NeuroNerPipe(ConfigurablePipe):
    """Detector that delegates to NeuroNER via the HTTP Docker sidecar."""

    def __init__(self, config: NeuroNerConfig | None = None) -> None:
        self._config = config or NeuroNerConfig()
        self._lock = threading.Lock()
        self._model_labels: list[str] | None = None
        self._labels_model_key: str | None = None

    def _manifest_model_name(self) -> str:
        """Registry / on-disk folder name (basename when ``model_folder`` is set)."""
        mf = (self._config.model_folder or "").strip()
        if mf:
            return Path(mf.rstrip("/")).name
        return self._config.model

    def _labels_cache_key(self) -> str:
        mf = (self._config.model_folder or "").strip()
        if mf:
            return "folder:" + mf
        return "model:" + self._config.model

    def _raw_entity_labels(self) -> list[str]:
        """Raw NeuroNER entity names (before ``entity_map``).

        Prefer the same ``model_manifest.json`` registry as ``GET /models`` / :func:`~pypedeid.models.get_model`
        (``models/<framework>/<name>/model_manifest.json``), then the pipe ``models_dir`` folder, then I2B2 defaults.
        """
        if (
            self._model_labels is not None
            and self._labels_model_key == self._labels_cache_key()
        ):
            return list(self._model_labels)
        name = self._manifest_model_name()
        try:
            from pypedeid.config import get_settings
            from pypedeid.models import get_model

            info = get_model(get_settings().models_dir, name)
            if info.framework == "neuroner" and info.labels:
                return sorted(info.labels)
        except (KeyError, ValueError, OSError):
            pass
        folder = Path(self._config.models_dir).resolve() / name
        on_disk = read_raw_neuroner_entity_labels(folder)
        if on_disk:
            return on_disk
        return list(DEFAULT_ENTITY_MAP.keys())

    def _http_base_url(self) -> str:
        raw = (self._config.base_url or "").strip()
        if raw:
            return raw.rstrip("/")
        from pypedeid.config import get_settings

        return get_settings().neuroner_http_url.rstrip("/")

    def _http_request_json(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        timeout: float,
    ) -> dict[str, Any]:
        url = self._http_base_url() + path
        payload = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=payload, method=method)
        if payload is not None:
            req.add_header("Content-Type", "application/json; charset=utf-8")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode()
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as e:
            err_body = e.read().decode() if e.fp else ""
            raise RuntimeError(f"NeuroNER HTTP {e.code} {path}: {err_body}") from e

    def _poll_http_sidecar_ready(self) -> None:
        """Wait until GET /health returns 200 (model loaded in sidecar)."""
        base = self._http_base_url()
        deadline = time.monotonic() + self._config.startup_timeout
        last_exc: Exception | None = None
        while time.monotonic() < deadline:
            try:
                req = urllib.request.Request(base + "/health", method="GET")
                with urllib.request.urlopen(req, timeout=10.0) as resp:
                    if resp.status == 200:
                        return
            except urllib.error.HTTPError as e:
                last_exc = e
                if e.code == 503:
                    try:
                        detail = json.loads(e.read().decode())
                    except Exception:
                        detail = {}
                    if detail.get("status") == "error":
                        raise RuntimeError(
                            "NeuroNER sidecar failed to load model: "
                            f"{detail.get('detail', e.reason)}"
                        ) from e
                    time.sleep(0.5)
                    continue
                raise RuntimeError(
                    f"NeuroNER HTTP /health failed: {e.code} {e.reason}"
                ) from e
            except Exception as e:
                last_exc = e
                time.sleep(0.5)
        raise TimeoutError(
            f"NeuroNER HTTP sidecar at {base} did not become ready within "
            f"{self._config.startup_timeout}s. Last error: {last_exc!r}"
        )

    def _ensure_http_ready(self) -> None:
        with self._lock:
            if (
                self._model_labels is not None
                and self._labels_model_key == self._labels_cache_key()
            ):
                return
        self._poll_http_sidecar_ready()
        mf = (self._config.model_folder or "").strip()
        if mf:
            labels_path = "/v1/labels?model_folder=" + quote(mf, safe="")
        else:
            labels_path = "/v1/labels?model=" + quote(self._config.model, safe="")
        labels_payload = self._http_request_json(
            "GET",
            labels_path,
            timeout=min(60.0, self._config.startup_timeout),
        )
        labs = labels_payload.get("labels")
        parsed: list[str] = (
            [str(x) for x in labs] if isinstance(labs, list) else []
        )
        with self._lock:
            self._model_labels = parsed
            self._labels_model_key = self._labels_cache_key()
            logger.info(
                "NeuroNER HTTP sidecar ready (model=%s, labels=%s)",
                self._manifest_model_name(),
                self._model_labels,
            )

    def _http_predict(self, text: str) -> dict[str, Any]:
        mf = (self._config.model_folder or "").strip()
        body: dict[str, Any] = {"text": text}
        if mf:
            body["model_folder"] = mf
        else:
            body["model"] = self._config.model
        return self._http_request_json(
            "POST",
            "/v1/predict",
            body=body,
            timeout=self._config.predict_timeout,
        )

    def model_labels(self) -> list[str]:
        """Return the entity labels the loaded model can produce.

        These are the *raw* neuroner labels (before ``entity_map``).
        """
        self._ensure_http_ready()
        return list(self._model_labels or [])

    @property
    def base_labels(self) -> set[str]:
        """Labels after ``entity_map`` (inputs to ``label_mapping``).

        Derived from the *selected model's* label space so the playground can refresh
        when ``model`` changes (see ``read_raw_neuroner_entity_labels``).
        """
        m = self._config.entity_map
        return {m.get(r, r) for r in self._raw_entity_labels()}

    @property
    def label_mapping(self) -> dict[str, str | None]:
        return dict(self._config.label_mapping)

    @property
    def labels(self) -> set[str]:
        return effective_detector_labels(self.base_labels, self._config.label_mapping)

    def forward(self, doc: AnnotatedDocument) -> AnnotatedDocument:
        text = doc.document.text
        if not text.strip():
            return doc

        self._ensure_http_ready()
        response = self._http_predict(text)

        entities = response.get("entities", [])
        found: list[EntitySpan] = []
        text_len = len(text)
        for ent in entities:
            raw_label = ent["type"]
            label = self._config.entity_map.get(raw_label, raw_label)
            try:
                start = int(ent["start"])
                end = int(ent["end"])
            except (KeyError, TypeError, ValueError):
                continue
            raw_conf = ent.get("confidence")
            if raw_conf is None:
                span_conf = None
            else:
                try:
                    span_conf = float(raw_conf)
                except (TypeError, ValueError):
                    span_conf = None
            if 0 <= start < end <= text_len:
                found.append(
                    EntitySpan(
                        start=start,
                        end=end,
                        label=label,
                        confidence=span_conf,
                        source=self._config.source_name,
                    )
                )

        found.sort(key=lambda s: (s.start, s.end, s.label))
        found = apply_detector_label_mapping(found, self._config.label_mapping)
        return accumulate_spans(
            doc, found, skip_overlapping=self._config.skip_overlapping
        )

    def shutdown(self) -> None:
        """No persistent process — HTTP sidecar runs independently."""

    def __del__(self) -> None:
        try:
            self.shutdown()
        except Exception:
            pass
