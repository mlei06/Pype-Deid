from __future__ import annotations

from pathlib import Path

import pytest

from pypedeid.config import Settings


def test_openai_from_openai_api_key_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("PYPEDEID_OPENAI_API_KEY", raising=False)
    s = Settings()
    assert s.openai_api_key == "sk-test"


def test_openai_prefers_alias_order_or_documented(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both vars: OPENAI_API_KEY is first in AliasChoices / typical precedence."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-a")
    monkeypatch.setenv("PYPEDEID_OPENAI_API_KEY", "sk-b")
    s = Settings()
    assert s.openai_api_key == "sk-a"


def test_openai_from_dotenv_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("PYPEDEID_OPENAI_API_KEY", raising=False)
    (tmp_path / ".env").write_text("OPENAI_API_KEY=sk-from-file\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    s = Settings()
    assert s.openai_api_key == "sk-from-file"


def test_openai_from_pypedeid_env_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("PYPEDEID_OPENAI_API_KEY", raising=False)
    env_path = tmp_path / "secret.env"
    env_path.write_text("OPENAI_API_KEY=sk-from-explicit-path\n", encoding="utf-8")
    monkeypatch.setenv("PYPEDEID_ENV_FILE", str(env_path))
    monkeypatch.chdir(tmp_path)
    s = Settings()
    assert s.openai_api_key == "sk-from-explicit-path"


def test_openai_chat_client_raises_without_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("PYPEDEID_OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("PYPEDEID_ALLOW_EXTERNAL_LLM", "true")
    (tmp_path / ".env").write_text("# no openai key\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    s = Settings()
    with pytest.raises(ValueError, match="OpenAI API key"):
        s.openai_chat_client()


def test_openai_chat_client_blocked_when_external_llm_disabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("PYPEDEID_ALLOW_EXTERNAL_LLM", raising=False)
    monkeypatch.chdir(tmp_path)
    s = Settings()
    with pytest.raises(ValueError, match="External LLM calls are disabled"):
        s.openai_chat_client()
