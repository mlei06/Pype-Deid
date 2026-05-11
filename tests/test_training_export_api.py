"""Tests for the dataset export API endpoint."""

from __future__ import annotations

import json

import pytest


@pytest.fixture
def dataset_with_docs(client, tmp_path):
    """Register a test dataset via the API."""
    # Create a JSONL file with test data
    jsonl_path = tmp_path / "data" / "corpora" / "_in" / "test_corpus.jsonl"
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    docs = [
        {
            "document": {"id": "doc1", "text": "Patient John Smith DOB 01/15/1980"},
            "spans": [
                {"start": 8, "end": 18, "label": "NAME"},
                {"start": 23, "end": 33, "label": "DATE"},
            ],
        },
        {
            "document": {"id": "doc2", "text": "Dr. Jane Doe phone 555-1234"},
            "spans": [
                {"start": 4, "end": 12, "label": "NAME"},
                {"start": 19, "end": 27, "label": "PHONE"},
            ],
        },
    ]
    jsonl_path.write_text(
        "\n".join(json.dumps(d) for d in docs) + "\n",
        encoding="utf-8",
    )

    # Register the dataset
    resp = client.post("/datasets", json={
        "name": "test-export-ds",
        "data_path": str(jsonl_path),
        "format": "jsonl",
        "description": "Test dataset for export",
    })
    assert resp.status_code == 201
    return "test-export-ds"


def test_export_conll(client, dataset_with_docs):
    resp = client.post(
        f"/datasets/{dataset_with_docs}/export",
        json={"format": "conll"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["format"] == "conll"
    assert data["document_count"] == 2
    assert data["total_spans"] == 4
    assert data["path"].endswith(".conll")


def test_export_huggingface(client, dataset_with_docs):
    resp = client.post(
        f"/datasets/{dataset_with_docs}/export",
        json={"format": "huggingface"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["format"] == "huggingface"
    assert data["document_count"] == 2


def test_export_not_found(client):
    resp = client.post(
        "/datasets/nonexistent/export",
        json={"format": "conll"},
    )
    assert resp.status_code == 404


def test_export_custom_filename(client, dataset_with_docs):
    resp = client.post(
        f"/datasets/{dataset_with_docs}/export",
        json={"format": "conll", "filename": "custom.conll"},
    )
    assert resp.status_code == 200
    assert resp.json()["path"].endswith("custom.conll")


def test_export_annotated_jsonl(client, dataset_with_docs, tmp_path):
    resp = client.post(
        f"/datasets/{dataset_with_docs}/export",
        json={"format": "jsonl"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["format"] == "jsonl"
    assert body["document_count"] == 2
    assert body["total_spans"] == 4

    from pathlib import Path

    exported = Path(body["path"])
    assert exported.is_file()
    assert exported.name == "train.jsonl"
    assert exported.parent == tmp_path / "data" / "exports" / dataset_with_docs
    lines = [ln for ln in exported.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["document"]["id"] == "doc1"
    assert len(first["spans"]) == 2


def test_export_annotated_jsonl_reimportable(client, dataset_with_docs):
    """Re-register the exported JSONL via POST /datasets (round-trip contract)."""
    resp = client.post(
        f"/datasets/{dataset_with_docs}/export",
        json={"format": "jsonl"},
    )
    assert resp.status_code == 200, resp.text
    exported_path = resp.json()["path"]

    resp2 = client.post(
        "/datasets",
        json={
            "name": "reimported-ds",
            "data_path": exported_path,
            "format": "jsonl",
        },
    )
    assert resp2.status_code == 201, resp2.text
    body = resp2.json()
    assert body["document_count"] == 2
    assert body["total_spans"] == 4


def test_export_surrogate_jsonl_line_shape(client, dataset_with_docs):
    """Surrogate export rewrites text and spans in-place."""
    import pytest
    pytest.importorskip("faker", reason="surrogate export requires faker")

    resp = client.post(
        f"/datasets/{dataset_with_docs}/export",
        json={"format": "jsonl", "target_text": "surrogate", "surrogate_seed": 42},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["format"] == "jsonl"
    assert body["target_text"] == "surrogate"

    from pathlib import Path

    exported = Path(body["path"])
    assert exported.is_file()
    lines = [ln for ln in exported.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 2
    first = json.loads(lines[0])
    # Every span in the surrogate corpus must point into the surrogate text.
    for s in first["spans"]:
        assert 0 <= s["start"] < s["end"] <= len(first["document"]["text"])
    # Seed should produce deterministic output; second run matches.
    resp2 = client.post(
        f"/datasets/{dataset_with_docs}/export",
        json={"format": "jsonl", "target_text": "surrogate", "surrogate_seed": 42},
    )
    assert resp2.status_code == 200, resp2.text
    exported2 = Path(resp2.json()["path"])
    assert exported.read_text(encoding="utf-8") == exported2.read_text(encoding="utf-8")


def test_export_surrogate_brat_round_trip(client, dataset_with_docs):
    """Exporting to BRAT with surrogate text and re-importing yields the same spans."""
    import pytest
    pytest.importorskip("faker", reason="surrogate export requires faker")

    resp = client.post(
        f"/datasets/{dataset_with_docs}/export",
        json={"format": "brat", "target_text": "surrogate", "surrogate_seed": 1},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["target_text"] == "surrogate"

    # Re-import the surrogate BRAT as a new dataset and confirm it has the same
    # document count and span count as the export indicated.
    resp_import = client.post(
        "/datasets/import/brat",
        json={"name": "surrogate-brat", "brat_path": body["path"]},
    )
    assert resp_import.status_code == 201, resp_import.text
    reimported = resp_import.json()
    assert reimported["document_count"] == body["document_count"]
    assert reimported["total_spans"] == body["total_spans"]


def test_export_surrogate_default_is_original(client, dataset_with_docs):
    resp = client.post(
        f"/datasets/{dataset_with_docs}/export",
        json={"format": "jsonl"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["target_text"] == "original"
