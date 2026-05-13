from __future__ import annotations

from pathlib import Path

from pypedeid.env_file import resolve_env_file_path


def test_resolve_explicit_pypedeid_env_file(monkeypatch, tmp_path: Path) -> None:
    p = tmp_path / "custom.env"
    p.write_text("X=1\n", encoding="utf-8")
    monkeypatch.setenv("PYPEDEID_ENV_FILE", str(p))
    assert resolve_env_file_path() == p


def test_resolve_walks_cwd_parents(tmp_path: Path, monkeypatch) -> None:
    sub = tmp_path / "a" / "b"
    sub.mkdir(parents=True)
    env_at_root = tmp_path / ".env"
    env_at_root.write_text("Y=2\n", encoding="utf-8")
    monkeypatch.delenv("PYPEDEID_ENV_FILE", raising=False)
    monkeypatch.chdir(sub)
    assert resolve_env_file_path() == env_at_root


def test_resolve_missing_explicit_returns_none(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PYPEDEID_ENV_FILE", str(tmp_path / "nope.env"))
    monkeypatch.chdir(tmp_path)
    assert resolve_env_file_path() is None
