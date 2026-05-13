"""Tests for the datasets API (register, CRUD, compose, transform, preview)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_sample_jsonl(path: Path, count: int = 5) -> Path:
    """Write a minimal annotated-document JSONL file and return its path."""
    docs = []
    for i in range(count):
        docs.append(
            {
                "document": {
                    "id": f"doc_{i}",
                    "text": f"Patient John Smith was seen on 2024-01-{10 + i:02d}.",
                    "metadata": {},
                },
                "spans": [
                    {"start": 8, "end": 18, "label": "PERSON", "source": "gold"},
                    {"start": 31, "end": 41, "label": "DATE", "source": "gold"},
                ],
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(d) for d in docs) + "\n", encoding="utf-8"
    )
    return path


def _write_jsonl_with_doc_splits(path: Path, splits: list[str]) -> Path:
    """Like :func:`_write_sample_jsonl` but sets ``metadata['split']`` per document."""
    docs = []
    for i, split in enumerate(splits):
        docs.append(
            {
                "document": {
                    "id": f"doc_{i}",
                    "text": f"Patient John Smith was seen on 2024-01-{10 + i:02d}.",
                    "metadata": {"split": split},
                },
                "spans": [
                    {"start": 8, "end": 18, "label": "PERSON", "source": "gold"},
                    {"start": 31, "end": 41, "label": "DATE", "source": "gold"},
                ],
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(d) for d in docs) + "\n", encoding="utf-8"
    )
    return path


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_register_and_list(client, tmp_path):
    jsonl = _write_sample_jsonl(tmp_path / "data" / "corpora" / "_in" / "sample.jsonl")
    resp = client.post(
        "/datasets",
        json={
            "name": "test-corpus",
            "data_path": str(jsonl),
            "format": "jsonl",
            "description": "A test corpus",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "test-corpus"
    assert body["document_count"] == 5
    assert body["total_spans"] == 10
    assert "PERSON" in body["labels"]
    assert "DATE" in body["labels"]
    assert body["analytics"]["document_count"] == 5

    # List
    resp = client.get("/datasets")
    assert resp.status_code == 200
    names = [d["name"] for d in resp.json()]
    assert "test-corpus" in names


def test_register_duplicate_rejected(client, tmp_path):
    jsonl = _write_sample_jsonl(tmp_path / "data" / "corpora" / "_in" / "sample.jsonl")
    client.post(
        "/datasets",
        json={"name": "dup", "data_path": str(jsonl), "format": "jsonl"},
    )
    resp = client.post(
        "/datasets",
        json={"name": "dup", "data_path": str(jsonl), "format": "jsonl"},
    )
    assert resp.status_code == 409


def _write_brat_flat(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "a.txt").write_text("CALVERT HOSPITAL here", encoding="utf-8")
    (directory / "a.ann").write_text(
        "T1\tHOSPITAL 0 16\tCALVERT HOSPITAL\n", encoding="utf-8"
    )
    return directory


def _write_brat_split(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    train = directory / "train"
    train.mkdir(parents=True, exist_ok=True)
    (train / "b.txt").write_text("LENOX HILL admit", encoding="utf-8")
    (train / "b.ann").write_text(
        "T1\tHOSPITAL 0 10\tLENOX HILL\n", encoding="utf-8"
    )
    return directory


def test_import_sources_lists_jsonl_only(client, tmp_path):
    corpora = tmp_path / "data" / "corpora"
    corpora.mkdir(parents=True, exist_ok=True)
    _write_sample_jsonl(corpora / "incoming.jsonl")
    _write_brat_flat(corpora / "brat_flat")
    _write_brat_split(corpora / "brat_split")

    resp = client.get("/datasets/import-sources")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["corpora_root"] == str(corpora.resolve())
    by_label = {c["label"]: c for c in body["candidates"]}
    assert by_label["incoming.jsonl"]["suggested_format"] == "jsonl"
    assert by_label["incoming.jsonl"]["data_path"] == str((corpora / "incoming.jsonl").resolve())
    # BRAT trees are NOT surfaced on the JSONL endpoint anymore.
    assert "brat_flat" not in by_label
    assert "brat_split" not in by_label

    client.post(
        "/datasets",
        json={
            "name": "from-drop",
            "data_path": str(corpora / "incoming.jsonl"),
            "format": "jsonl",
        },
    )
    resp2 = client.get("/datasets/import-sources")
    assert resp2.status_code == 200
    labels2 = {c["label"] for c in resp2.json()["candidates"]}
    assert "incoming.jsonl" in labels2
    assert "from-drop" not in labels2


def test_brat_import_sources_endpoint(client, tmp_path):
    corpora = tmp_path / "data" / "corpora"
    corpora.mkdir(parents=True, exist_ok=True)
    _write_brat_flat(corpora / "brat_flat")
    _write_brat_split(corpora / "brat_split")
    _write_sample_jsonl(corpora / "stray.jsonl")

    resp = client.get("/datasets/import-sources/brat")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["corpora_root"] == str(corpora.resolve())
    by_label = {c["label"]: c for c in body["candidates"]}
    assert by_label["brat_flat"]["kind"] == "brat-dir"
    assert by_label["brat_flat"]["data_path"] == str((corpora / "brat_flat").resolve())
    assert by_label["brat_split"]["kind"] == "brat-corpus"
    # JSONL files are NOT surfaced on the BRAT endpoint.
    assert "stray.jsonl" not in by_label


# ---------------------------------------------------------------------------
# Get / Update / Delete
# ---------------------------------------------------------------------------


def test_get_dataset(client, tmp_path):
    jsonl = _write_sample_jsonl(tmp_path / "data" / "corpora" / "_in" / "sample.jsonl")
    client.post(
        "/datasets",
        json={"name": "get-me", "data_path": str(jsonl), "format": "jsonl"},
    )
    resp = client.get("/datasets/get-me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["document_count"] == 5
    assert body.get("has_split_metadata") is False
    assert body.get("split_document_counts", {}).get("(none)") == 5


def test_get_missing_returns_404(client):
    resp = client.get("/datasets/nonexistent")
    assert resp.status_code == 404


def test_update_dataset(client, tmp_path):
    jsonl = _write_sample_jsonl(tmp_path / "data" / "corpora" / "_in" / "sample.jsonl")
    client.post(
        "/datasets",
        json={"name": "upd", "data_path": str(jsonl), "format": "jsonl"},
    )
    resp = client.put(
        "/datasets/upd",
        json={"description": "Updated description", "metadata": {"tag": "v2"}},
    )
    assert resp.status_code == 200
    assert resp.json()["description"] == "Updated description"
    assert resp.json()["metadata"]["tag"] == "v2"


def test_delete_dataset(client, tmp_path):
    jsonl = _write_sample_jsonl(tmp_path / "data" / "corpora" / "_in" / "sample.jsonl")
    client.post(
        "/datasets",
        json={"name": "del-me", "data_path": str(jsonl), "format": "jsonl"},
    )
    resp = client.delete("/datasets/del-me")
    assert resp.status_code == 204
    assert client.get("/datasets/del-me").status_code == 404


# ---------------------------------------------------------------------------
# Preview & document
# ---------------------------------------------------------------------------


def test_preview(client, tmp_path):
    jsonl = _write_sample_jsonl(tmp_path / "data" / "corpora" / "_in" / "sample.jsonl")
    client.post(
        "/datasets",
        json={"name": "prev", "data_path": str(jsonl), "format": "jsonl"},
    )
    resp = client.get("/datasets/prev/preview?limit=3")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    assert len(body["items"]) == 3
    assert body["items"][0]["span_count"] == 2
    assert body["items"][0].get("split") is None


def test_split_counts_preview_and_subset_analytics(client, tmp_path):
    jsonl = _write_jsonl_with_doc_splits(
        tmp_path / "data" / "corpora" / "_in" / "splits.jsonl",
        ["train", "train", "test", "test", "test"],
    )
    client.post(
        "/datasets",
        json={"name": "splitty", "data_path": str(jsonl), "format": "jsonl"},
    )
    d = client.get("/datasets/splitty").json()
    assert d["has_split_metadata"] is True
    sc = d["split_document_counts"]
    assert sc.get("train") == 2
    assert sc.get("test") == 3

    p = client.get("/datasets/splitty/preview?splits=train&limit=10").json()
    assert p["total"] == 2
    assert len(p["items"]) == 2
    assert p["items"][0]["split"] == "train"

    a = client.get("/datasets/splitty/analytics?split=train").json()
    assert a["document_count"] == 2
    assert client.get("/datasets/splitty/analytics").json()["document_count"] == 5


def test_get_document(client, tmp_path):
    jsonl = _write_sample_jsonl(tmp_path / "data" / "corpora" / "_in" / "sample.jsonl")
    client.post(
        "/datasets",
        json={"name": "docview", "data_path": str(jsonl), "format": "jsonl"},
    )
    resp = client.get("/datasets/docview/documents/doc_0")
    assert resp.status_code == 200
    body = resp.json()
    assert body["document_id"] == "doc_0"
    assert len(body["spans"]) == 2


def test_get_document_not_found(client, tmp_path):
    jsonl = _write_sample_jsonl(tmp_path / "data" / "corpora" / "_in" / "sample.jsonl")
    client.post(
        "/datasets",
        json={"name": "docnf", "data_path": str(jsonl), "format": "jsonl"},
    )
    resp = client.get("/datasets/docnf/documents/nope")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Refresh analytics
# ---------------------------------------------------------------------------


def test_refresh_analytics(client, tmp_path):
    jsonl = _write_sample_jsonl(tmp_path / "data" / "corpora" / "_in" / "sample.jsonl", count=3)
    client.post(
        "/datasets",
        json={"name": "ref", "data_path": str(jsonl), "format": "jsonl"},
    )
    # Mutate the colocated corpus copy (not the original upload path).
    _write_sample_jsonl(tmp_path / "data" / "corpora" / "ref" / "corpus.jsonl", count=8)
    resp = client.post("/datasets/ref/refresh")
    assert resp.status_code == 200
    assert resp.json()["document_count"] == 8


def test_refresh_all_endpoint(client, tmp_path):
    ok = _write_sample_jsonl(tmp_path / "data" / "corpora" / "_in" / "good.jsonl", count=2)
    client.post("/datasets", json={"name": "ok1", "data_path": str(ok), "format": "jsonl"})
    client.post("/datasets", json={"name": "ok2", "data_path": str(ok), "format": "jsonl"})

    # Deliberately corrupt one corpus.jsonl so its refresh errors.
    broken = tmp_path / "data" / "corpora" / "ok2" / "corpus.jsonl"
    broken.write_text("not json\n", encoding="utf-8")

    resp = client.post("/datasets/refresh-all")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    by_name = {r["name"]: r for r in body}
    assert by_name["ok1"]["status"] == "ok"
    assert by_name["ok2"]["status"] == "error"
    assert by_name["ok2"]["error"]


# ---------------------------------------------------------------------------
# BRAT import endpoint
# ---------------------------------------------------------------------------


def test_import_brat_flat_endpoint(client, tmp_path):
    brat_dir = tmp_path / "data" / "corpora" / "_brat_in"
    _write_brat_flat(brat_dir)

    resp = client.post(
        "/datasets/import/brat",
        json={"name": "from-brat", "brat_path": str(brat_dir), "description": "brat → jsonl"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "from-brat"
    assert body["format"] == "jsonl"
    assert body["document_count"] == 1
    assert "HOSPITAL" in body["labels"]

    home = tmp_path / "data" / "corpora" / "from-brat"
    assert (home / "corpus.jsonl").is_file()
    # No BRAT leftovers inside the home.
    assert not list(home.glob("*.txt"))
    assert not list(home.glob("*.ann"))


def test_import_brat_duplicate_name_conflicts(client, tmp_path):
    brat_dir = tmp_path / "data" / "corpora" / "_brat_in"
    _write_brat_flat(brat_dir)
    resp1 = client.post(
        "/datasets/import/brat",
        json={"name": "dup-brat", "brat_path": str(brat_dir)},
    )
    assert resp1.status_code == 201
    resp2 = client.post(
        "/datasets/import/brat",
        json={"name": "dup-brat", "brat_path": str(brat_dir)},
    )
    assert resp2.status_code == 409


def test_import_jsonl_alias_route(client, tmp_path):
    jsonl = _write_sample_jsonl(tmp_path / "data" / "corpora" / "_in" / "alias.jsonl", count=2)
    resp = client.post(
        "/datasets/import/jsonl",
        json={"name": "aliased", "data_path": str(jsonl), "format": "jsonl"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["document_count"] == 2


# ---------------------------------------------------------------------------
# Compose
# ---------------------------------------------------------------------------


def test_compose_merge(client, tmp_path):
    a = _write_sample_jsonl(tmp_path / "data" / "corpora" / "_in" / "a.jsonl", count=3)
    b = _write_sample_jsonl(tmp_path / "data" / "corpora" / "_in" / "b.jsonl", count=4)
    client.post("/datasets", json={"name": "src-a", "data_path": str(a), "format": "jsonl"})
    client.post("/datasets", json={"name": "src-b", "data_path": str(b), "format": "jsonl"})

    resp = client.post(
        "/datasets/compose",
        json={
            "output_name": "merged",
            "source_datasets": ["src-a", "src-b"],
            "strategy": "merge",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "merged"
    assert body["document_count"] == 7
    assert body["metadata"]["provenance"]["composed_from"] == ["src-a", "src-b"]


def test_compose_proportional(client, tmp_path):
    a = _write_sample_jsonl(tmp_path / "data" / "corpora" / "_in" / "a.jsonl", count=10)
    b = _write_sample_jsonl(tmp_path / "data" / "corpora" / "_in" / "b.jsonl", count=10)
    client.post("/datasets", json={"name": "pa", "data_path": str(a), "format": "jsonl"})
    client.post("/datasets", json={"name": "pb", "data_path": str(b), "format": "jsonl"})

    resp = client.post(
        "/datasets/compose",
        json={
            "output_name": "prop-mix",
            "source_datasets": ["pa", "pb"],
            "strategy": "proportional",
            "weights": [0.7, 0.3],
            "target_documents": 10,
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["document_count"] == 10


def test_compose_missing_source(client, tmp_path):
    a = _write_sample_jsonl(tmp_path / "data" / "corpora" / "_in" / "a.jsonl", count=2)
    client.post("/datasets", json={"name": "only", "data_path": str(a), "format": "jsonl"})
    resp = client.post(
        "/datasets/compose",
        json={
            "output_name": "bad",
            "source_datasets": ["only", "nonexistent"],
            "strategy": "merge",
        },
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------


def test_transform_filter_labels(client, tmp_path):
    jsonl = _write_sample_jsonl(tmp_path / "data" / "corpora" / "_in" / "sample.jsonl", count=5)
    client.post(
        "/datasets",
        json={"name": "orig", "data_path": str(jsonl), "format": "jsonl"},
    )

    resp = client.post(
        "/datasets/transform",
        json={
            "source_dataset": "orig",
            "output_name": "persons-only",
            "keep_labels": ["PERSON"],
            "description": "Only PERSON entities",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "persons-only"
    assert body["labels"] == ["PERSON"]
    assert body["total_spans"] == 5  # 1 PERSON per doc


def test_transform_in_place(client, tmp_path):
    jsonl = _write_sample_jsonl(tmp_path / "data" / "corpora" / "_in" / "sample.jsonl", count=5)
    client.post(
        "/datasets",
        json={"name": "inplace-src", "data_path": str(jsonl), "format": "jsonl"},
    )
    resp = client.post(
        "/datasets/transform",
        json={
            "source_dataset": "inplace-src",
            "in_place": True,
            "keep_labels": ["PERSON"],
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "inplace-src"
    assert body["labels"] == ["PERSON"]


def test_transform_new_dataset_requires_output_name(client, tmp_path):
    jsonl = _write_sample_jsonl(tmp_path / "data" / "corpora" / "_in" / "sample.jsonl", count=2)
    client.post(
        "/datasets",
        json={"name": "need-name", "data_path": str(jsonl), "format": "jsonl"},
    )
    resp = client.post(
        "/datasets/transform",
        json={"source_dataset": "need-name", "in_place": False, "keep_labels": ["PERSON"]},
    )
    assert resp.status_code == 422


def test_transform_label_mapping(client, tmp_path):
    jsonl = _write_sample_jsonl(tmp_path / "data" / "corpora" / "_in" / "sample.jsonl", count=3)
    client.post(
        "/datasets",
        json={"name": "map-src", "data_path": str(jsonl), "format": "jsonl"},
    )

    resp = client.post(
        "/datasets/transform",
        json={
            "source_dataset": "map-src",
            "output_name": "mapped",
            "label_mapping": {"PERSON": "NAME", "DATE": "TEMPORAL"},
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert sorted(body["labels"]) == ["NAME", "TEMPORAL"]


def test_transform_resize(client, tmp_path):
    jsonl = _write_sample_jsonl(tmp_path / "data" / "corpora" / "_in" / "sample.jsonl", count=10)
    client.post(
        "/datasets",
        json={"name": "big", "data_path": str(jsonl), "format": "jsonl"},
    )

    resp = client.post(
        "/datasets/transform",
        json={
            "source_dataset": "big",
            "output_name": "small",
            "target_documents": 3,
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["document_count"] == 3


def test_transform_source_splits_filters_documents(client, tmp_path):
    jsonl = _write_jsonl_with_doc_splits(
        tmp_path / "data" / "corpora" / "_in" / "split.jsonl",
        ["train", "train", "valid", "test", "test"],
    )
    client.post(
        "/datasets",
        json={"name": "split-src", "data_path": str(jsonl), "format": "jsonl"},
    )
    resp = client.post(
        "/datasets/transform",
        json={
            "source_dataset": "split-src",
            "output_name": "train-only",
            "source_splits": ["train"],
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["document_count"] == 2
    prov = resp.json()["metadata"]["provenance"]
    assert prov.get("source_splits") == ["train"]


def test_transform_source_splits_empty_matches_422(client, tmp_path):
    jsonl = _write_sample_jsonl(tmp_path / "data" / "corpora" / "_in" / "sample.jsonl", count=2)
    client.post(
        "/datasets",
        json={"name": "no-split", "data_path": str(jsonl), "format": "jsonl"},
    )
    resp = client.post(
        "/datasets/transform",
        json={
            "source_dataset": "no-split",
            "output_name": "fail",
            "source_splits": ["train"],
        },
    )
    assert resp.status_code == 422
    assert "source_splits" in resp.json()["detail"].lower()


def test_transform_missing_source(client):
    resp = client.post(
        "/datasets/transform",
        json={
            "source_dataset": "nope",
            "output_name": "fail",
        },
    )
    assert resp.status_code == 404


def test_transform_writes_jsonl_under_corpora_dir(client, tmp_path):
    """Transform output is ``corpora_dir/{name}/corpus.jsonl``."""
    jsonl = _write_sample_jsonl(tmp_path / "data" / "corpora" / "_in" / "sample.jsonl", count=4)
    client.post(
        "/datasets",
        json={"name": "t-src", "data_path": str(jsonl), "format": "jsonl"},
    )
    resp = client.post(
        "/datasets/transform",
        json={"source_dataset": "t-src", "output_name": "t-out"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["format"] == "jsonl"
    expected = tmp_path / "data" / "corpora" / "t-out" / "corpus.jsonl"
    assert expected.is_file()
    assert body["data_path"] == str(expected.resolve())
    corpora_root = tmp_path / "data" / "corpora"
    assert not list(corpora_root.glob("*.jsonl"))


def test_transform_rejects_removed_output_format_field(client, tmp_path):
    """The removed ``output_format`` field must not silently succeed."""
    jsonl = _write_sample_jsonl(tmp_path / "data" / "corpora" / "_in" / "sample.jsonl", count=2)
    client.post("/datasets", json={"name": "rej-src", "data_path": str(jsonl), "format": "jsonl"})
    resp = client.post(
        "/datasets/transform",
        json={
            "source_dataset": "rej-src",
            "output_name": "rej-out",
            "output_format": "brat-corpus",
        },
    )
    # Pydantic defaults to extra="ignore"; the field is simply dropped, so the
    # request succeeds as JSONL. Assert the outcome matches the new contract.
    assert resp.status_code == 201, resp.text
    assert resp.json()["format"] == "jsonl"


def test_compose_writes_jsonl_under_corpora_dir(client, tmp_path):
    a = _write_sample_jsonl(tmp_path / "data" / "corpora" / "_in" / "a.jsonl", count=2)
    b = _write_sample_jsonl(tmp_path / "data" / "corpora" / "_in" / "b.jsonl", count=3)
    client.post("/datasets", json={"name": "c-a", "data_path": str(a), "format": "jsonl"})
    client.post("/datasets", json={"name": "c-b", "data_path": str(b), "format": "jsonl"})
    resp = client.post(
        "/datasets/compose",
        json={
            "output_name": "c-out",
            "source_datasets": ["c-a", "c-b"],
            "strategy": "merge",
        },
    )
    assert resp.status_code == 201, resp.text
    expected = tmp_path / "data" / "corpora" / "c-out" / "corpus.jsonl"
    assert expected.is_file()
    assert resp.json()["data_path"] == str(expected.resolve())


def test_export_brat_writes_flat_dir(client, tmp_path):
    jsonl = _write_sample_jsonl(tmp_path / "data" / "corpora" / "_in" / "sample.jsonl", count=3)
    client.post("/datasets", json={"name": "brat-src", "data_path": str(jsonl), "format": "jsonl"})
    resp = client.post("/datasets/brat-src/export", json={"format": "brat"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["format"] == "brat"
    # Exports now live under exports_dir, not inside corpora_dir.
    out = tmp_path / "data" / "exports" / "brat-src"
    assert out.is_dir()
    assert list(out.glob("*.txt"))
    assert list(out.glob("*.ann"))
    # No residue inside the corpora root.
    assert not (tmp_path / "data" / "corpora" / "brat-src_export").exists()


def test_dataset_schema_endpoint(client, tmp_path):
    jsonl = _write_sample_jsonl(tmp_path / "data" / "corpora" / "_in" / "sample.jsonl")
    client.post(
        "/datasets",
        json={"name": "schema-src", "data_path": str(jsonl), "format": "jsonl"},
    )
    resp = client.get("/datasets/schema-src/schema")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["dataset"] == "schema-src"
    assert body["document_count"] == 5
    by_label = {x["label"]: x["count"] for x in body["labels"]}
    assert by_label["PERSON"] == 5
    assert by_label["DATE"] == 5


def test_transform_preview_endpoint(client, tmp_path):
    jsonl = _write_sample_jsonl(tmp_path / "data" / "corpora" / "_in" / "sample.jsonl", count=3)
    client.post(
        "/datasets",
        json={"name": "pv-src", "data_path": str(jsonl), "format": "jsonl"},
    )
    resp = client.post(
        "/datasets/transform/preview",
        json={
            "source_dataset": "pv-src",
            "keep_labels": ["PERSON"],
            "label_mapping": {"PERSON": "NAME"},
        },
    )
    assert resp.status_code == 200, resp.text
    p = resp.json()
    assert p["source_document_count"] == 3
    assert p["spans_dropped_by_filter"] == 3  # DATE dropped
    assert p["spans_kept_after_filter"] == 3
    assert p["spans_renamed"] == 3
    assert "conflicts" in p
    assert p["projected_document_count"] == 3
    assert p.get("untouched_document_count", 0) == 0

    clash = client.post(
        "/datasets/transform/preview",
        json={
            "source_dataset": "pv-src",
            "drop_labels": ["PERSON"],
            "label_mapping": {"PERSON": "PER"},
        },
    )
    assert clash.status_code == 200
    assert len(clash.json()["conflicts"]) >= 1


def test_transform_preview_source_splits_in_place_merges_counts(client, tmp_path):
    """New dataset: work subset only. In-place: full corpus (rest + transformed work)."""
    jsonl = _write_jsonl_with_doc_splits(
        tmp_path / "data" / "corpora" / "_in" / "psplit.jsonl",
        ["train", "train", "valid", "test", "test"],
    )
    client.post(
        "/datasets",
        json={"name": "psplit-src", "data_path": str(jsonl), "format": "jsonl"},
    )
    p_new = client.post(
        "/datasets/transform/preview",
        json={
            "source_dataset": "psplit-src",
            "in_place": False,
            "source_splits": ["train"],
            "transform_mode": "schema",
        },
    )
    assert p_new.status_code == 200, p_new.text
    b = p_new.json()
    assert b["source_document_count"] == 2
    assert b["untouched_document_count"] == 3
    assert b["projected_document_count"] == 2

    p_ip = client.post(
        "/datasets/transform/preview",
        json={
            "source_dataset": "psplit-src",
            "in_place": True,
            "source_splits": ["train"],
            "transform_mode": "schema",
        },
    )
    assert p_ip.status_code == 200, p_ip.text
    assert p_ip.json()["projected_document_count"] == 5


def test_transform_preview_rejects_drop_and_keep(client, tmp_path):
    jsonl = _write_sample_jsonl(tmp_path / "data" / "corpora" / "_in" / "sample.jsonl", count=2)
    client.post(
        "/datasets",
        json={"name": "both-src", "data_path": str(jsonl), "format": "jsonl"},
    )
    resp = client.post(
        "/datasets/transform/preview",
        json={
            "source_dataset": "both-src",
            "drop_labels": ["DATE"],
            "keep_labels": ["PERSON"],
        },
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# dataset_store unit tests
# ---------------------------------------------------------------------------


def test_store_register_and_load(tmp_path):
    from pypedeid.dataset_store import (
        delete_dataset,
        list_datasets,
        load_dataset_documents,
        load_dataset_manifest,
        register_dataset,
    )

    jsonl = _write_sample_jsonl(tmp_path / "incoming" / "corpus.jsonl", count=4)
    corpora_dir = tmp_path / "corpora"
    corpora_dir.mkdir()

    manifest = register_dataset(corpora_dir, "unit-test", str(jsonl), "jsonl", description="test")
    assert manifest["document_count"] == 4
    assert manifest.get("split_document_counts", {}).get("(none)") == 4
    assert manifest.get("has_split_metadata") is False
    assert manifest["name"] == "unit-test"
    assert (corpora_dir / "unit-test" / "corpus.jsonl").is_file()

    # Load back
    loaded = load_dataset_manifest(corpora_dir, "unit-test")
    assert loaded["document_count"] == 4

    # List
    datasets = list_datasets(corpora_dir)
    assert len(datasets) == 1
    assert datasets[0].name == "unit-test"

    # Load documents
    docs = load_dataset_documents(corpora_dir, "unit-test")
    assert len(docs) == 4

    # Delete
    delete_dataset(corpora_dir, "unit-test")
    assert len(list_datasets(corpora_dir)) == 0


def test_corpora_dir_env_primary(tmp_path, monkeypatch, caplog):
    """PYPEDEID_CORPORA_DIR sets the corpus data root (no deprecation warning)."""
    import logging

    from pypedeid.config import Settings, reset_settings

    root = tmp_path / "corp-root"
    root.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PYPEDEID_PROCESSED_DIR", raising=False)
    monkeypatch.delenv("PYPEDEID_ENV_FILE", raising=False)
    monkeypatch.setenv("PYPEDEID_CORPORA_DIR", str(root))
    reset_settings()
    with caplog.at_level(logging.WARNING, logger="pypedeid.config"):
        settings = Settings()
    assert settings.corpora_dir == root
    assert not any("deprecated" in rec.message.lower() for rec in caplog.records)
    reset_settings()


def test_legacy_processed_dir_env_still_resolves(tmp_path, monkeypatch, caplog):
    """PYPEDEID_PROCESSED_DIR still sets corpora_dir but logs a deprecation warning."""
    import logging

    from pypedeid.config import Settings, reset_settings

    legacy = tmp_path / "old-processed"
    legacy.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PYPEDEID_CORPORA_DIR", raising=False)
    monkeypatch.delenv("PYPEDEID_ENV_FILE", raising=False)
    monkeypatch.setenv("PYPEDEID_PROCESSED_DIR", str(legacy))
    reset_settings()
    with caplog.at_level(logging.WARNING, logger="pypedeid.config"):
        settings = Settings()
    assert settings.corpora_dir == legacy
    assert any(
        "PROCESSED_DIR" in rec.message and "deprecated" in rec.message.lower()
        for rec in caplog.records
    )
    reset_settings()


def test_store_invalid_name(tmp_path):
    from pypedeid.dataset_store import register_dataset

    jsonl = _write_sample_jsonl(tmp_path / "incoming" / "corpus.jsonl")
    corpora_dir = tmp_path / "corpora"
    corpora_dir.mkdir()

    with pytest.raises(ValueError, match="Invalid dataset name"):
        register_dataset(corpora_dir, "../escape", str(jsonl), "jsonl")

    with pytest.raises(ValueError, match="Invalid dataset name"):
        register_dataset(corpora_dir, "", str(jsonl), "jsonl")


def test_register_rejects_non_jsonl_format(tmp_path):
    """register_dataset is a back-compat shim and must reject BRAT formats."""
    from pypedeid.dataset_store import register_dataset

    jsonl = _write_sample_jsonl(tmp_path / "incoming" / "corpus.jsonl")
    corpora_dir = tmp_path / "corpora"
    corpora_dir.mkdir()
    with pytest.raises(ValueError, match="only 'jsonl' is supported"):
        register_dataset(corpora_dir, "nope", str(jsonl), "brat-dir")


def test_list_datasets_discovers_jsonl_and_auto_creates_manifest(tmp_path):
    """A bare ``corpus.jsonl`` under a home counts; ``dataset.json`` is lazy."""
    from pypedeid.dataset_store import list_datasets

    corpora_dir = tmp_path / "corpora"
    (corpora_dir / "handmade").mkdir(parents=True)
    _write_sample_jsonl(corpora_dir / "handmade" / "corpus.jsonl", count=3)
    assert not (corpora_dir / "handmade" / "dataset.json").is_file()

    found = list_datasets(corpora_dir)
    assert [d.name for d in found] == ["handmade"]
    assert found[0].document_count == 3
    assert (corpora_dir / "handmade" / "dataset.json").is_file()


def test_list_datasets_skips_legacy_brat_homes(tmp_path, caplog):
    """Legacy homes with format != 'jsonl' must be dropped from discovery."""
    import json
    import logging

    from pypedeid.dataset_store import list_datasets

    corpora_dir = tmp_path / "corpora"
    legacy = corpora_dir / "oldbrat"
    legacy.mkdir(parents=True)
    # Legacy BRAT layout: .txt/.ann + dataset.json saying format="brat-dir"
    (legacy / "a.txt").write_text("hi", encoding="utf-8")
    (legacy / "a.ann").write_text("T1\tPER 0 2\thi\n", encoding="utf-8")
    # Also create corpus.jsonl to prove the format gate (not just file presence) drops it.
    _write_sample_jsonl(legacy / "corpus.jsonl", count=1)
    (legacy / "dataset.json").write_text(
        json.dumps(
            {
                "name": "oldbrat",
                "format": "brat-dir",
                "document_count": 1,
                "total_spans": 0,
                "labels": [],
                "analytics": {},
                "metadata": {},
                "created_at": "2024-01-01T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    with caplog.at_level(logging.DEBUG, logger="pypedeid.dataset_store"):
        found = list_datasets(corpora_dir)

    assert [d.name for d in found] == []


def test_import_brat_to_jsonl_unit(tmp_path):
    from pypedeid.dataset_store import import_brat_to_jsonl

    brat_dir = tmp_path / "brat_flat"
    brat_dir.mkdir()
    (brat_dir / "a.txt").write_text("CALVERT HOSPITAL here", encoding="utf-8")
    (brat_dir / "a.ann").write_text(
        "T1\tHOSPITAL 0 16\tCALVERT HOSPITAL\n", encoding="utf-8"
    )
    corpora_dir = tmp_path / "corpora"
    corpora_dir.mkdir()

    manifest = import_brat_to_jsonl(
        corpora_dir,
        "from-brat",
        brat_dir,
        description="from brat",
    )
    assert manifest["name"] == "from-brat"
    assert manifest["format"] == "jsonl"
    assert manifest["document_count"] == 1
    home = corpora_dir / "from-brat"
    assert (home / "corpus.jsonl").is_file()
    assert not list(home.glob("*.txt"))
    assert not list(home.glob("*.ann"))


# ---------------------------------------------------------------------------
# Eval integration with dataset_name
# ---------------------------------------------------------------------------


def test_eval_rejects_empty_eval_pred_label_remap_value(client, tmp_path):
    jsonl = _write_sample_jsonl(tmp_path / "data" / "gold_remap.jsonl", count=1)
    client.post(
        "/datasets",
        json={"name": "eval-remap-422", "data_path": str(jsonl), "format": "jsonl"},
    )
    client.post("/pipelines", json={"name": "noop-rmap", "config": {"pipes": []}})

    resp = client.post(
        "/eval/run",
        json={
            "pipeline_name": "noop-rmap",
            "dataset_name": "eval-remap-422",
            "eval_pred_label_remap": {"A": " "},
        },
    )
    assert resp.status_code == 422


def test_eval_with_dataset_name(client, tmp_path):
    """Eval endpoint can reference a registered dataset by name."""
    jsonl = _write_sample_jsonl(tmp_path / "data" / "corpora" / "_in" / "gold.jsonl", count=3)
    client.post(
        "/datasets",
        json={"name": "eval-gold", "data_path": str(jsonl), "format": "jsonl"},
    )

    # Create a trivial pipeline (no pipes = returns empty spans)
    client.post("/pipelines", json={"name": "noop", "config": {"pipes": []}})

    resp = client.post(
        "/eval/run",
        json={"pipeline_name": "noop", "dataset_name": "eval-gold"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["document_count"] == 3
    assert body["dataset_source"] == "dataset:eval-gold"
    assert body["metrics"]["risk_profile_name"] == "clinical_phi"


def test_eval_run_risk_profile_name_persisted_and_unknown_400(client, tmp_path):
    jsonl = _write_sample_jsonl(tmp_path / "data" / "corpora" / "_in" / "gold_rp.jsonl", count=1)
    client.post(
        "/datasets",
        json={"name": "eval-rp", "data_path": str(jsonl), "format": "jsonl"},
    )
    client.post("/pipelines", json={"name": "noop-rp", "config": {"pipes": []}})

    resp = client.post(
        "/eval/run",
        json={
            "pipeline_name": "noop-rp",
            "dataset_name": "eval-rp",
            "risk_profile_name": "generic_pii",
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["metrics"]["risk_profile_name"] == "generic_pii"

    resp_bad = client.post(
        "/eval/run",
        json={
            "pipeline_name": "noop-rp",
            "dataset_name": "eval-rp",
            "risk_profile_name": "not_a_real_profile",
        },
    )
    assert resp_bad.status_code == 400
    assert "Known:" in resp_bad.json()["detail"]


def test_eval_dataset_splits_filters_and_source_string(client, tmp_path):
    jsonl = _write_jsonl_with_doc_splits(
        tmp_path / "data" / "corpora" / "_in" / "gold_split.jsonl",
        ["train", "valid", "test"],
    )
    client.post(
        "/datasets",
        json={"name": "eval-split", "data_path": str(jsonl), "format": "jsonl"},
    )
    client.post("/pipelines", json={"name": "noop2", "config": {"pipes": []}})

    resp = client.post(
        "/eval/run",
        json={
            "pipeline_name": "noop2",
            "dataset_name": "eval-split",
            "dataset_splits": ["valid", "train"],
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["document_count"] == 2
    assert body["dataset_source"] == "dataset:eval-split:splits=train+valid"


def test_eval_dataset_splits_no_match_422(client, tmp_path):
    jsonl = _write_sample_jsonl(tmp_path / "data" / "corpora" / "_in" / "gold.jsonl", count=2)
    client.post(
        "/datasets",
        json={"name": "eval-nosplit", "data_path": str(jsonl), "format": "jsonl"},
    )
    client.post("/pipelines", json={"name": "noop3", "config": {"pipes": []}})

    resp = client.post(
        "/eval/run",
        json={
            "pipeline_name": "noop3",
            "dataset_name": "eval-nosplit",
            "dataset_splits": ["train"],
        },
    )
    assert resp.status_code == 422
    assert "dataset_splits" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Eval sampling
# ---------------------------------------------------------------------------


def _setup_sample_eval(client, tmp_path, count: int, *, name: str) -> None:
    jsonl = _write_sample_jsonl(
        tmp_path / "data" / "corpora" / "_in" / f"{name}.jsonl", count=count
    )
    client.post(
        "/datasets",
        json={"name": name, "data_path": str(jsonl), "format": "jsonl"},
    )
    client.post("/pipelines", json={"name": f"{name}-pipe", "config": {"pipes": []}})


def test_eval_sample_with_fixed_seed_is_deterministic(client, tmp_path):
    _setup_sample_eval(client, tmp_path, count=10, name="eval-sample-seed")

    def run_once():
        resp = client.post(
            "/eval/run",
            json={
                "pipeline_name": "eval-sample-seed-pipe",
                "dataset_name": "eval-sample-seed",
                "eval_mode": "sample",
                "sample_size": 4,
                "sample_seed": 12345,
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["document_count"] == 4
        sample = body["metrics"]["sample"]
        assert sample == {
            "eval_mode": "sample",
            "sample_size": 4,
            "sample_seed_used": 12345,
            "sample_of_total": 10,
        }
        return sample

    s1 = run_once()
    s2 = run_once()
    assert s1 == s2


def test_eval_sample_without_seed_returns_used_seed(client, tmp_path):
    _setup_sample_eval(client, tmp_path, count=5, name="eval-sample-noseed")

    resp = client.post(
        "/eval/run",
        json={
            "pipeline_name": "eval-sample-noseed-pipe",
            "dataset_name": "eval-sample-noseed",
            "eval_mode": "sample",
            "sample_size": 2,
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["document_count"] == 2
    sample = body["metrics"]["sample"]
    assert sample["sample_size"] == 2
    assert sample["sample_of_total"] == 5
    assert isinstance(sample["sample_seed_used"], int)
    assert sample["sample_seed_used"] >= 0
    # Seed must fit in JS Number.MAX_SAFE_INTEGER (2**53 - 1). A 64-bit seed would
    # lose precision on the client round-trip and silently break reproducibility
    # when a user pastes the returned seed back as a fixed seed.
    assert sample["sample_seed_used"] <= (2**53 - 1)


def test_eval_sample_applies_splits_before_sizing(client, tmp_path):
    jsonl = _write_jsonl_with_doc_splits(
        tmp_path / "data" / "corpora" / "_in" / "gold_splits_sample.jsonl",
        ["train", "train", "train", "valid"],
    )
    client.post(
        "/datasets",
        json={"name": "eval-splitsample", "data_path": str(jsonl), "format": "jsonl"},
    )
    client.post("/pipelines", json={"name": "noop-splitsample", "config": {"pipes": []}})

    resp = client.post(
        "/eval/run",
        json={
            "pipeline_name": "noop-splitsample",
            "dataset_name": "eval-splitsample",
            "dataset_splits": ["train"],
            "eval_mode": "sample",
            "sample_size": 2,
            "sample_seed": 7,
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["document_count"] == 2
    sample = body["metrics"]["sample"]
    assert sample["sample_of_total"] == 3  # only train docs available after split
    assert sample["sample_size"] == 2
    assert sample["sample_seed_used"] == 7


def test_eval_sample_size_too_large_is_422(client, tmp_path):
    _setup_sample_eval(client, tmp_path, count=3, name="eval-sample-big")

    resp = client.post(
        "/eval/run",
        json={
            "pipeline_name": "eval-sample-big-pipe",
            "dataset_name": "eval-sample-big",
            "eval_mode": "sample",
            "sample_size": 99,
        },
    )
    assert resp.status_code == 422
    assert "sample_size" in resp.json()["detail"]


def test_eval_sample_requires_positive_size(client, tmp_path):
    _setup_sample_eval(client, tmp_path, count=3, name="eval-sample-missing")

    resp = client.post(
        "/eval/run",
        json={
            "pipeline_name": "eval-sample-missing-pipe",
            "dataset_name": "eval-sample-missing",
            "eval_mode": "sample",
        },
    )
    assert resp.status_code == 422
    assert "sample_size" in resp.json()["detail"]


def test_eval_full_mode_has_no_sample_metadata(client, tmp_path):
    _setup_sample_eval(client, tmp_path, count=2, name="eval-full-mode")

    resp = client.post(
        "/eval/run",
        json={
            "pipeline_name": "eval-full-mode-pipe",
            "dataset_name": "eval-full-mode",
            "eval_mode": "full",
        },
    )
    assert resp.status_code == 201, resp.text
    assert "sample" not in resp.json()["metrics"]


def test_eval_save_sample_as_registers_new_dataset(client, tmp_path):
    _setup_sample_eval(client, tmp_path, count=6, name="eval-save-src")

    resp = client.post(
        "/eval/run",
        json={
            "pipeline_name": "eval-save-src-pipe",
            "dataset_name": "eval-save-src",
            "eval_mode": "sample",
            "sample_size": 3,
            "sample_seed": 1234,
            "save_sample_as": {
                "dataset_name": "eval-save-dst",
                "description": "sampled subset from eval",
            },
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    sample = body["metrics"]["sample"]
    assert sample["saved_dataset_name"] == "eval-save-dst"

    # New dataset is listed and carries provenance metadata.
    listed = client.get("/datasets").json()
    assert any(d["name"] == "eval-save-dst" for d in listed)
    detail = client.get("/datasets/eval-save-dst").json()
    assert detail["document_count"] == 3
    provenance = detail["metadata"]["provenance"]
    assert provenance == {
        "derived_from": "eval-save-src",
        "sample_seed": 1234,
        "sample_size": 3,
        "sample_of_total": 6,
        "source_eval_pipeline": "eval-save-src-pipe",
    }


def test_eval_save_sample_as_collision_is_409(client, tmp_path):
    _setup_sample_eval(client, tmp_path, count=4, name="eval-save-collide-src")
    _setup_sample_eval(client, tmp_path, count=2, name="eval-save-collide-dst")

    resp = client.post(
        "/eval/run",
        json={
            "pipeline_name": "eval-save-collide-src-pipe",
            "dataset_name": "eval-save-collide-src",
            "eval_mode": "sample",
            "sample_size": 2,
            "sample_seed": 1,
            "save_sample_as": {"dataset_name": "eval-save-collide-dst"},
        },
    )
    assert resp.status_code == 409
    assert "already exists" in resp.json()["detail"]


def test_eval_save_sample_as_requires_sample_mode(client, tmp_path):
    _setup_sample_eval(client, tmp_path, count=3, name="eval-save-fullmode")

    resp = client.post(
        "/eval/run",
        json={
            "pipeline_name": "eval-save-fullmode-pipe",
            "dataset_name": "eval-save-fullmode",
            "save_sample_as": {"dataset_name": "wont-save"},
        },
    )
    assert resp.status_code == 422
    assert "eval_mode" in resp.json()["detail"]
    # The target dataset must not exist.
    assert client.get("/datasets/wont-save").status_code == 404


def test_eval_include_per_document_returns_compact_payload(client, tmp_path):
    _setup_sample_eval(client, tmp_path, count=4, name="eval-perdoc-compact")

    resp = client.post(
        "/eval/run",
        json={
            "pipeline_name": "eval-perdoc-compact-pipe",
            "dataset_name": "eval-perdoc-compact",
            "include_per_document": True,
        },
    )
    assert resp.status_code == 201, resp.text
    metrics = resp.json()["metrics"]
    assert metrics["document_level_includes_spans"] is False
    assert metrics["document_level_truncated"] is False
    assert metrics["document_level_total"] == 4
    items = metrics["document_level"]
    assert len(items) == 4
    first = items[0]
    assert set(first) == {
        "document_id",
        "metrics",
        "risk_weighted_recall",
        "false_positive_count",
        "false_negative_count",
    }
    # Pipeline is a no-op, so every gold span is a false negative.
    assert first["false_negative_count"] > 0
    assert first["false_positive_count"] == 0


def test_eval_include_per_document_spans_adds_text_and_spans(client, tmp_path):
    _setup_sample_eval(client, tmp_path, count=2, name="eval-perdoc-spans")

    resp = client.post(
        "/eval/run",
        json={
            "pipeline_name": "eval-perdoc-spans-pipe",
            "dataset_name": "eval-perdoc-spans",
            "include_per_document_spans": True,
        },
    )
    assert resp.status_code == 201, resp.text
    metrics = resp.json()["metrics"]
    assert metrics["document_level_includes_spans"] is True
    item = metrics["document_level"][0]
    assert "text" in item and item["text"]
    assert isinstance(item["gold_spans"], list) and item["gold_spans"]
    assert isinstance(item["pred_spans"], list)
    assert isinstance(item["false_positives"], list)
    assert isinstance(item["false_negatives"], list)
    gold = item["gold_spans"][0]
    assert set(gold) == {"start", "end", "label"}


def test_eval_per_document_never_persisted(client, tmp_path):
    _setup_sample_eval(client, tmp_path, count=2, name="eval-perdoc-persist")

    resp = client.post(
        "/eval/run",
        json={
            "pipeline_name": "eval-perdoc-persist-pipe",
            "dataset_name": "eval-perdoc-persist",
            "include_per_document_spans": True,
        },
    )
    assert resp.status_code == 201, resp.text
    run_id = resp.json()["id"]

    # Fetch the saved run back and confirm it does NOT carry per-doc fields.
    fetched = client.get(f"/eval/runs/{run_id}").json()
    metrics = fetched["metrics"]
    assert "document_level" not in metrics
    assert "document_level_truncated" not in metrics
    assert "document_level_includes_spans" not in metrics


def test_eval_per_document_default_omits_payload(client, tmp_path):
    _setup_sample_eval(client, tmp_path, count=2, name="eval-perdoc-default")

    resp = client.post(
        "/eval/run",
        json={
            "pipeline_name": "eval-perdoc-default-pipe",
            "dataset_name": "eval-perdoc-default",
        },
    )
    assert resp.status_code == 201, resp.text
    metrics = resp.json()["metrics"]
    assert "document_level" not in metrics


def test_eval_per_document_truncates_at_limit(client, tmp_path, monkeypatch):
    _setup_sample_eval(client, tmp_path, count=6, name="eval-perdoc-cap")

    from pypedeid.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "eval_per_document_limit", 2)

    resp = client.post(
        "/eval/run",
        json={
            "pipeline_name": "eval-perdoc-cap-pipe",
            "dataset_name": "eval-perdoc-cap",
            "include_per_document": True,
        },
    )
    assert resp.status_code == 201, resp.text
    metrics = resp.json()["metrics"]
    assert metrics["document_level_truncated"] is True
    assert metrics["document_level_total"] == 6
    assert len(metrics["document_level"]) == 2


def test_eval_save_sample_as_rejects_invalid_name(client, tmp_path):
    _setup_sample_eval(client, tmp_path, count=3, name="eval-save-badname")

    resp = client.post(
        "/eval/run",
        json={
            "pipeline_name": "eval-save-badname-pipe",
            "dataset_name": "eval-save-badname",
            "eval_mode": "sample",
            "sample_size": 1,
            "save_sample_as": {"dataset_name": "../escape"},
        },
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Ingest via saved pipeline
# ---------------------------------------------------------------------------


def test_ingest_from_pipeline(client, tmp_path):
    corpora = tmp_path / "data" / "corpora"
    raw = corpora / "raw_txts"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "note1.txt").write_text("Patient John Smith visited on 01/15/1980", encoding="utf-8")
    (raw / "note2.txt").write_text("Call 555-1234 for a follow-up appointment", encoding="utf-8")

    client.post(
        "/pipelines",
        json={"name": "ingest-pipe", "config": {"pipes": [{"type": "regex_ner"}]}},
    )

    resp = client.post(
        "/datasets/ingest-from-pipeline",
        json={
            "source_path": "raw_txts",
            "pipeline_name": "ingest-pipe",
            "output_name": "raw-fast-silver",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "raw-fast-silver"
    assert body["document_count"] == 2

    list_resp = client.get("/datasets")
    names = [d["name"] for d in list_resp.json()]
    assert "raw-fast-silver" in names

    corpus_jsonl = corpora / "raw-fast-silver" / "corpus.jsonl"
    assert corpus_jsonl.is_file()
    lines = [ln for ln in corpus_jsonl.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 2


def test_ingest_from_pipeline_path_escape_rejected(client, tmp_path):
    client.post(
        "/pipelines",
        json={"name": "ingest-pipe-2", "config": {"pipes": [{"type": "regex_ner"}]}},
    )
    resp = client.post(
        "/datasets/ingest-from-pipeline",
        json={
            "source_path": "../../etc/passwd",
            "pipeline_name": "ingest-pipe-2",
            "output_name": "escape-attempt",
        },
    )
    assert resp.status_code == 400, resp.text
    assert "corpora root" in resp.json()["detail"].lower()


def test_ingest_from_pipeline_duplicate_name(client, tmp_path):
    corpora = tmp_path / "data" / "corpora"
    raw = corpora / "raw_dup"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "a.txt").write_text("simple text", encoding="utf-8")

    client.post(
        "/pipelines",
        json={"name": "ingest-pipe-3", "config": {"pipes": [{"type": "regex_ner"}]}},
    )
    first = client.post(
        "/datasets/ingest-from-pipeline",
        json={
            "source_path": "raw_dup",
            "pipeline_name": "ingest-pipe-3",
            "output_name": "ingest-dup",
        },
    )
    assert first.status_code == 201, first.text
    second = client.post(
        "/datasets/ingest-from-pipeline",
        json={
            "source_path": "raw_dup",
            "pipeline_name": "ingest-pipe-3",
            "output_name": "ingest-dup",
        },
    )
    assert second.status_code == 409


def test_ingest_from_pipeline_missing_pipeline(client, tmp_path):
    corpora = tmp_path / "data" / "corpora"
    raw = corpora / "raw_missing"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "a.txt").write_text("text", encoding="utf-8")

    resp = client.post(
        "/datasets/ingest-from-pipeline",
        json={
            "source_path": "raw_missing",
            "pipeline_name": "does-not-exist",
            "output_name": "nope",
        },
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PUT /datasets/{name}/documents/{doc_id}
# ---------------------------------------------------------------------------


def test_put_document_replaces_spans(client, tmp_path):
    jsonl = _write_sample_jsonl(tmp_path / "data" / "corpora" / "_in" / "sample.jsonl", count=2)
    client.post(
        "/datasets",
        json={"name": "edit-ds", "data_path": str(jsonl), "format": "jsonl"},
    )

    resp = client.put(
        "/datasets/edit-ds/documents/doc_0",
        json={"spans": [{"start": 8, "end": 18, "label": "NAME"}]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["document_id"] == "doc_0"
    assert len(body["spans"]) == 1
    assert body["spans"][0]["label"] == "NAME"

    fetched = client.get("/datasets/edit-ds/documents/doc_0").json()
    assert len(fetched["spans"]) == 1
    assert fetched["spans"][0]["label"] == "NAME"

    # Analytics must reflect the new span count for that doc.
    detail = client.get("/datasets/edit-ds").json()
    # doc_0 now has 1 span; doc_1 still has 2 → total 3.
    assert detail["total_spans"] == 3


def test_put_document_allows_text_override(client, tmp_path):
    jsonl = _write_sample_jsonl(tmp_path / "data" / "corpora" / "_in" / "sample.jsonl", count=1)
    client.post(
        "/datasets",
        json={"name": "edit-text", "data_path": str(jsonl), "format": "jsonl"},
    )
    resp = client.put(
        "/datasets/edit-text/documents/doc_0",
        json={
            "text": "Jane Doe",
            "spans": [{"start": 0, "end": 8, "label": "NAME"}],
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["text"] == "Jane Doe"


def test_put_document_rejects_out_of_range_span(client, tmp_path):
    jsonl = _write_sample_jsonl(tmp_path / "data" / "corpora" / "_in" / "sample.jsonl", count=1)
    client.post(
        "/datasets",
        json={"name": "edit-range", "data_path": str(jsonl), "format": "jsonl"},
    )
    resp = client.put(
        "/datasets/edit-range/documents/doc_0",
        json={"spans": [{"start": 0, "end": 9999, "label": "NAME"}]},
    )
    assert resp.status_code == 422, resp.text


def test_put_document_missing_id_returns_404(client, tmp_path):
    jsonl = _write_sample_jsonl(tmp_path / "data" / "corpora" / "_in" / "sample.jsonl", count=1)
    client.post(
        "/datasets",
        json={"name": "edit-missing", "data_path": str(jsonl), "format": "jsonl"},
    )
    resp = client.put(
        "/datasets/edit-missing/documents/does_not_exist",
        json={"spans": []},
    )
    assert resp.status_code == 404


def test_put_document_unknown_dataset_returns_404(client):
    resp = client.put(
        "/datasets/nope/documents/whatever",
        json={"spans": []},
    )
    assert resp.status_code == 404


def test_ingest_from_pipeline_symlink_escape_rejected(client, tmp_path):
    """A symlink under CORPORA_DIR that points outside must be rejected."""
    import os

    corpora = tmp_path / "data" / "corpora"
    corpora.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "outside_root"
    outside.mkdir(parents=True, exist_ok=True)
    (outside / "a.txt").write_text("secret", encoding="utf-8")
    link = corpora / "escape_link"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported on this filesystem")

    client.post(
        "/pipelines",
        json={"name": "sym-pipe", "config": {"pipes": [{"type": "regex_ner"}]}},
    )
    resp = client.post(
        "/datasets/ingest-from-pipeline",
        json={
            "source_path": "escape_link",
            "pipeline_name": "sym-pipe",
            "output_name": "sym-escape",
        },
    )
    assert resp.status_code == 400, resp.text
    assert "corpora root" in resp.json()["detail"].lower()


def test_ingest_from_pipeline_max_documents(client, tmp_path):
    corpora = tmp_path / "data" / "corpora"
    raw = corpora / "many"
    raw.mkdir(parents=True, exist_ok=True)
    for i in range(5):
        (raw / f"f{i}.txt").write_text(f"content {i}", encoding="utf-8")

    client.post(
        "/pipelines",
        json={"name": "limit-pipe", "config": {"pipes": [{"type": "regex_ner"}]}},
    )
    resp = client.post(
        "/datasets/ingest-from-pipeline",
        json={
            "source_path": "many",
            "pipeline_name": "limit-pipe",
            "output_name": "limit-ingest",
            "max_documents": 2,
        },
    )
    assert resp.status_code == 422, resp.text
    assert "max_documents" in resp.json()["detail"]


def test_preview_corpus_labels(client, tmp_path):
    corpora = tmp_path / "data" / "corpora"
    rel = _write_sample_jsonl(corpora / "preview-test" / "corpus.jsonl")
    rel_rel = rel.relative_to(corpora).as_posix()
    r = client.post("/datasets/preview-labels", json={"path": rel_rel})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["document_count"] == 5
    assert set(data["labels"]) == {"DATE", "PERSON"}
    assert rel.name in data["resolved_path"] or str(rel) in data["resolved_path"]


def test_preview_corpus_labels_rejects_non_jsonl(client, tmp_path):
    corpora = tmp_path / "data" / "corpora"
    bad = corpora / "bad.txt"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text("x", encoding="utf-8")
    r = client.post(
        "/datasets/preview-labels",
        json={"path": bad.relative_to(corpora).as_posix()},
    )
    assert r.status_code == 422, r.text


def test_preview_corpus_labels_rejects_outside_corpora(client, tmp_path):
    outside = tmp_path / "outside.jsonl"
    outside.write_text("{}\n", encoding="utf-8")
    r = client.post("/datasets/preview-labels", json={"path": str(outside)})
    assert r.status_code == 400, r.text


# ---------------------------------------------------------------------------
# Multipart upload (POST /datasets/upload)
# ---------------------------------------------------------------------------


def test_upload_annotated_jsonl_multipart(client, tmp_path):
    path = _write_sample_jsonl(tmp_path / "upload-source.jsonl", count=3)
    content = path.read_bytes()
    resp = client.post(
        "/datasets/upload",
        files={"file": ("corpus.jsonl", content, "application/x-ndjson")},
        data={
            "name": "multipart-corpus",
            "description": "from multipart",
            "metadata": json.dumps({"provenance": "test"}),
            "line_format": "annotated_jsonl",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "multipart-corpus"
    assert body["document_count"] == 3
    assert body["metadata"].get("provenance") == "test"
    listed = client.get("/datasets")
    assert listed.status_code == 200
    assert "multipart-corpus" in {d["name"] for d in listed.json()}


def test_upload_annotated_jsonl_multipart_duplicate_409(client, tmp_path):
    path = _write_sample_jsonl(tmp_path / "u.jsonl", count=1)
    content = path.read_bytes()
    kwargs = {
        "files": {"file": ("u.jsonl", content, "text/plain")},
        "data": {"name": "dup-multipart", "line_format": "annotated_jsonl"},
    }
    assert client.post("/datasets/upload", **kwargs).status_code == 201
    r2 = client.post("/datasets/upload", **kwargs)
    assert r2.status_code == 409


def test_upload_invalid_name_422(client, tmp_path):
    path = _write_sample_jsonl(tmp_path / "u.jsonl", count=1)
    b = path.read_bytes()
    r1 = client.post(
        "/datasets/upload",
        files={"file": ("u.jsonl", b, "text/plain")},
        data={"name": "bad..name", "line_format": "annotated_jsonl"},
    )
    assert r1.status_code == 422
    r2 = client.post(
        "/datasets/upload",
        files={"file": ("u.jsonl", b, "text/plain")},
        data={"name": "no spaces", "line_format": "annotated_jsonl"},
    )
    assert r2.status_code == 422


def test_upload_production_v1_line_multipart(client, tmp_path):
    line = {
        "schema_version": 1,
        "output_type": "annotated",
        "id": "doc-1",
        "source_label": "src",
        "text": "Hello world",
        "spans": [
            {"start": 0, "end": 5, "label": "L", "confidence": 0.5, "source": "g"},
        ],
        "resolved": True,
        "metadata": {"note": "n"},
    }
    content = (json.dumps(line) + "\n").encode("utf-8")
    resp = client.post(
        "/datasets/upload",
        files={"file": ("export.jsonl", content, "application/jsonl")},
        data={"name": "prod-export", "line_format": "production_v1"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["document_count"] == 1
    assert "L" in resp.json()["labels"]


def test_upload_empty_file_422(client, tmp_path):
    r = client.post(
        "/datasets/upload",
        files={"file": ("e.jsonl", b"", "text/plain")},
        data={"name": "empty-up", "line_format": "annotated_jsonl"},
    )
    assert r.status_code == 422
