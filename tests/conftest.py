from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    db_file = data_dir / "app.sqlite"
    pipelines_dir = data_dir / "pipelines"
    evaluations_dir = data_dir / "evaluations"
    inference_runs_dir = data_dir / "inference_runs"
    corpora_dir = data_dir / "corpora"
    exports_dir = data_dir / "exports"
    dictionaries_dir = data_dir / "dictionaries"
    pipelines_dir.mkdir(parents=True)
    evaluations_dir.mkdir()
    inference_runs_dir.mkdir()
    corpora_dir.mkdir()
    exports_dir.mkdir()
    dictionaries_dir.mkdir()

    monkeypatch.setenv("PYPEDEID_DATABASE_URL", f"sqlite:///{db_file.as_posix()}")
    monkeypatch.setenv("PYPEDEID_PIPELINES_DIR", str(pipelines_dir))
    monkeypatch.setenv("PYPEDEID_MODES_PATH", str(data_dir / "modes.json"))
    monkeypatch.setenv("PYPEDEID_EVALUATIONS_DIR", str(evaluations_dir))
    monkeypatch.setenv("PYPEDEID_INFERENCE_RUNS_DIR", str(inference_runs_dir))
    monkeypatch.setenv("PYPEDEID_CORPORA_DIR", str(corpora_dir))
    monkeypatch.setenv("PYPEDEID_EXPORTS_DIR", str(exports_dir))
    monkeypatch.setenv("PYPEDEID_DICTIONARIES_DIR", str(dictionaries_dir))

    from pypedeid.config import reset_settings
    from pypedeid.db import init_db, reset_engine

    reset_settings()
    reset_engine()
    init_db()

    from pypedeid.api.app import create_app

    test_app = create_app()

    with TestClient(test_app) as test_client:
        yield test_client
