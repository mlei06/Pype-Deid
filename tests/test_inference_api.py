from __future__ import annotations

from pypedeid.api.schemas import SaveInferenceSnapshotRequest


def test_inference_save_list_load_delete(client) -> None:
    body = SaveInferenceSnapshotRequest(
        request_id="req-1",
        original_text="Patient Jane Doe visited.",
        redacted_text="Patient [NAME] visited.",
        spans=[
            {
                "start": 8,
                "end": 16,
                "label": "NAME",
                "text": "Jane Doe",
                "confidence": None,
                "source": None,
            }
        ],
        pipeline_name="test-pipe",
        processing_time_ms=12.5,
        intermediary_trace=None,
    )

    r = client.post("/inference/runs", json=body.model_dump(mode="json"))
    assert r.status_code == 200
    saved = r.json()
    assert "id" in saved
    assert saved["saved_at"]
    assert saved["original_text"] == body.original_text
    run_id = saved["id"]

    r = client.get("/inference/runs")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["id"] == run_id
    assert rows[0]["pipeline_name"] == "test-pipe"
    assert rows[0]["span_count"] == 1
    assert "Jane" in rows[0]["text_preview"]

    r = client.get(f"/inference/runs/{run_id}")
    assert r.status_code == 200
    loaded = r.json()
    assert loaded["id"] == run_id
    assert len(loaded["spans"]) == 1

    r = client.delete(f"/inference/runs/{run_id}")
    assert r.status_code == 204

    r = client.get("/inference/runs")
    assert r.json() == []
