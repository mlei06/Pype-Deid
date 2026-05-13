"""LLM backends: protocol + OpenAI-compatible HTTP client."""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol, runtime_checkable

from pypedeid.synthesis.types import ChatMessage

logger = logging.getLogger(__name__)


@runtime_checkable
class LLMClient(Protocol):
    """Minimal interface for :class:`LLMSynthesizer`."""

    def complete(self, messages: list[ChatMessage], **kwargs: Any) -> str:
        """Return assistant text (one turn). kwargs may include temperature, etc."""


class OpenAICompatibleChatClient:
    """
    Chat Completions API (OpenAI or compatible base URL).

    Requires ``httpx``: ``pip install pypedeid[llm]``.
    """

    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        timeout_s: float = 120.0,
        default_headers: dict[str, str] | None = None,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.default_headers = default_headers or {}
        self._http: Any = None

    def _client(self) -> Any:
        if self._http is None:
            try:
                import httpx
            except ImportError as e:
                raise ImportError(
                    "OpenAICompatibleChatClient requires httpx; "
                    "install with: pip install pypedeid[llm]"
                ) from e
            self._http = httpx.Client(timeout=self.timeout_s)
        return self._http

    def close(self) -> None:
        if self._http is not None:
            self._http.close()
            self._http = None

    def complete(self, messages: list[ChatMessage], **kwargs: Any) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [m.model_dump() for m in messages],
        }
        if "temperature" in kwargs:
            payload["temperature"] = kwargs["temperature"]
        if "max_tokens" in kwargs:
            payload["max_tokens"] = kwargs["max_tokens"]
        if "response_format" in kwargs:
            payload["response_format"] = kwargs["response_format"]

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            **self.default_headers,
        }
        url = f"{self.base_url}/chat/completions"
        client = self._client()
        r = client.post(url, json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()

        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"LLM response missing choices: {data!r}")
        msg = choices[0].get("message") or {}
        content = msg.get("content")
        if not content:
            raise RuntimeError(f"LLM response missing message content: {data!r}")
        return str(content).strip()


_REASONING_MODEL_PREFIXES: tuple[str, ...] = ("gpt-5", "o1", "o3", "o4")

# Newer GPT-5.x families dropped "minimal" effort and added "none" / "xhigh" instead.
# Translate "minimal" -> "low" for these so old saved configs keep working.
_NO_MINIMAL_EFFORT_PREFIXES: tuple[str, ...] = (
    "gpt-5.1",
    "gpt-5.4",
    "gpt-5.5",
)


def _is_reasoning_model(model: str) -> bool:
    return any(model.startswith(p) for p in _REASONING_MODEL_PREFIXES)


def _sanitize_reasoning_effort(model: str, effort: str | None) -> str | None:
    """Translate ``effort`` to a value the model's API will accept.

    The OpenAI ``reasoning.effort`` enum is not uniform across models. As of
    GPT-5.1 the value ``"minimal"`` was removed; the rest of the API still
    accepts it. We translate transparently so saved configs targeting the old
    enum don't 400 when the user switches model.
    """
    if effort != "minimal":
        return effort
    if any(model.startswith(p) for p in _NO_MINIMAL_EFFORT_PREFIXES):
        logger.debug(
            "reasoning_effort='minimal' not supported by %s; using 'low' instead.",
            model,
        )
        return "low"
    return effort


_shared_openai_clients: dict[tuple[str, str], Any] = {}


def get_shared_openai_client(api_key: str, base_url: str | None = None) -> Any:
    """Return a process-wide cached ``openai.OpenAI`` client.

    Reusing one client lets the underlying ``httpx`` connection pool keep TCP/TLS
    sessions warm across requests, which is the dominant per-call latency cost
    for short prompts.
    """
    key = (api_key, base_url or "")
    cached = _shared_openai_clients.get(key)
    if cached is not None:
        return cached
    try:
        from openai import OpenAI
    except ImportError as e:
        raise ImportError(
            "OpenAIResponsesClient requires the openai SDK; "
            "install with: pip install 'pypedeid[llm]'"
        ) from e
    kwargs: dict[str, Any] = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    client = OpenAI(**kwargs)
    _shared_openai_clients[key] = client
    return client


class OpenAIResponsesClient:
    """Client for OpenAI's Responses API with strict JSON-schema structured outputs.

    Uses the official ``openai`` SDK and a process-wide shared client so that
    HTTP/2 + connection pooling reduces per-request TLS overhead. Returns
    parsed Python objects rather than raw text.
    """

    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        base_url: str | None = None,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.base_url = base_url

    def _client(self) -> Any:
        return get_shared_openai_client(self.api_key, self.base_url)

    def extract_structured(
        self,
        prompt: str,
        *,
        schema: dict[str, Any],
        schema_name: str = "StructuredOutput",
        temperature: float | None = None,
        reasoning_effort: str | None = None,
        max_output_tokens: int | None = None,
    ) -> Any:
        """Send a single-turn prompt and return the parsed JSON object.

        Returns ``None`` if the response is empty or unparseable.
        """
        client = self._client()
        kwargs: dict[str, Any] = {
            "model": self.model,
            "input": [
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": prompt}],
                }
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "schema": schema,
                    "strict": True,
                }
            },
        }
        if temperature is not None and not _is_reasoning_model(self.model):
            kwargs["temperature"] = temperature
        if reasoning_effort is not None and _is_reasoning_model(self.model):
            sanitized = _sanitize_reasoning_effort(self.model, reasoning_effort)
            if sanitized is not None:
                kwargs["reasoning"] = {"effort": sanitized}
        if max_output_tokens is not None:
            kwargs["max_output_tokens"] = max_output_tokens

        response = client.responses.create(**kwargs)

        # Prefer pre-parsed payload from the SDK if available.
        for output in getattr(response, "output", []) or []:
            for part in getattr(output, "content", []) or []:
                parsed = getattr(part, "parsed", None)
                if parsed is not None:
                    if hasattr(parsed, "model_dump"):
                        return parsed.model_dump()
                    return parsed

        text = getattr(response, "output_text", None)
        if not text:
            return None
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            logger.warning("OpenAIResponsesClient: response was not valid JSON")
            return None


class StaticResponseClient:
    """Test double or canned demo: always returns the same assistant string."""

    def __init__(self, text: str) -> None:
        self._text = text

    def complete(self, messages: list[ChatMessage], **kwargs: Any) -> str:
        del messages, kwargs
        return self._text
