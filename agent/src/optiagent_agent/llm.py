"""Structured LLM calls with validation-driven retries.

Every call asks for JSON matching a Pydantic model's schema. If the reply fails to parse or
fails an extra validator, the errors go back to the model and it gets another attempt.
Each attempt is recorded so latency and call counts can be reported.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

Message = dict[str, str]


class LLMReply(BaseModel):
    content: str
    model: str
    latency_ms: float
    prompt_tokens: int = 0
    completion_tokens: int = 0


class LLM(Protocol):
    model: str

    async def chat(self, messages: list[Message], schema: dict[str, Any]) -> LLMReply: ...


class LLMCall(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    step: str
    attempt: int
    model: str
    latency_ms: float
    prompt_tokens: int = 0
    completion_tokens: int = 0
    ok: bool
    errors: list[str] = Field(default_factory=list)


class Trace(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    calls: list[LLMCall] = Field(default_factory=list)

    @property
    def total_latency_ms(self) -> float:
        return sum(c.latency_ms for c in self.calls)


class LLMError(RuntimeError):
    pass


class OllamaLLM:
    def __init__(self, base_url: str, model: str, timeout: float = 600.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    async def chat(self, messages: list[Message], schema: dict[str, Any]) -> LLMReply:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "format": schema,
            "stream": False,
            "options": {"temperature": 0},
        }
        if self.model.startswith("qwen3"):
            # Qwen3 reasons before answering by default; structured extraction does not need it.
            payload["think"] = False
        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
                response = await client.post("/api/chat", json=payload)
        except httpx.HTTPError as exc:
            raise LLMError(f"Could not reach Ollama at {self.base_url}: {exc}") from exc
        if response.is_error:
            try:
                detail = response.json().get("error", response.text)
            except ValueError:
                detail = response.text
            if response.status_code == 404:
                detail += f" (run: ollama pull {self.model})"
            raise LLMError(f"Ollama error {response.status_code}: {detail}")
        data = response.json()
        return LLMReply(
            content=data["message"]["content"],
            model=data.get("model", self.model),
            latency_ms=(time.perf_counter() - start) * 1000,
            prompt_tokens=data.get("prompt_eval_count", 0),
            completion_tokens=data.get("eval_count", 0),
        )


class OpenAICompatibleLLM:
    """Any server speaking the OpenAI chat-completions API: Groq, OpenRouter, OpenAI, vLLM,
    or Ollama's own /v1 endpoint.

    Asks for JSON matching the schema via `response_format=json_schema`. If the provider or model
    rejects that, falls back to plain JSON mode with the schema in the prompt; `structured()`
    validates and retries either way.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout: float = 120.0,
        max_retries: int = 2,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.transport = transport
        self.json_schema_supported = True

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            headers=self._headers(),
            transport=self.transport,
        )

    @staticmethod
    def _error_detail(response: httpx.Response) -> str:
        try:
            body = response.json()
        except ValueError:
            return response.text[:500]
        error = body.get("error", body) if isinstance(body, dict) else body
        if isinstance(error, dict):
            return str(error.get("message") or error)[:500]
        return str(error)[:500]

    async def _post(self, payload: dict[str, Any]) -> httpx.Response:
        """POST with retries on rate limits and server errors."""
        async with self._client() as client:
            for attempt in range(self.max_retries + 1):
                try:
                    response = await client.post("/chat/completions", json=payload)
                except httpx.HTTPError as exc:
                    if attempt == self.max_retries:
                        raise LLMError(
                            f"Could not reach the LLM at {self.base_url}: {exc}"
                        ) from exc
                    await _sleep(2**attempt)
                    continue
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt == self.max_retries:
                        return response
                    retry_after = response.headers.get("retry-after", "")
                    wait = (
                        float(retry_after)
                        if retry_after.replace(".", "", 1).isdigit()
                        else 2**attempt
                    )
                    await _sleep(min(wait, 20.0))
                    continue
                return response
        raise AssertionError("unreachable")

    async def chat(self, messages: list[Message], schema: dict[str, Any]) -> LLMReply:
        base: dict[str, Any] = {"model": self.model, "messages": messages, "temperature": 0}
        start = time.perf_counter()
        response = None
        if self.json_schema_supported:
            response = await self._post(
                {
                    **base,
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {"name": "output", "schema": schema, "strict": False},
                    },
                }
            )
            if response.status_code in (400, 422) and "response_format" in self._error_detail(
                response
            ):
                self.json_schema_supported = False  # remember for later calls
                response = None
        if response is None:
            schema_text = json.dumps(schema, separators=(",", ":"))
            guided = [
                {
                    "role": "system",
                    "content": f"{messages[0]['content']}\n\nReply with only a JSON object that "
                    f"matches this JSON schema:\n{schema_text}",
                },
                *messages[1:],
            ]
            response = await self._post(
                {**base, "messages": guided, "response_format": {"type": "json_object"}}
            )

        if response.is_error:
            detail = self._error_detail(response)
            if response.status_code == 401:
                raise LLMError(f"The LLM provider rejected the API key (401): {detail}")
            if response.status_code == 404:
                raise LLMError(f"Model {self.model!r} not found at {self.base_url} (404): {detail}")
            if response.status_code == 429:
                raise LLMError(f"The LLM provider is rate limiting requests (429): {detail}")
            raise LLMError(f"LLM error {response.status_code}: {detail}")

        data = response.json()
        usage = data.get("usage") or {}
        return LLMReply(
            content=data["choices"][0]["message"].get("content") or "",
            model=data.get("model", self.model),
            latency_ms=(time.perf_counter() - start) * 1000,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
        )


async def _sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


def _format_validation_error(exc: ValidationError) -> list[str]:
    return [f"{'.'.join(map(str, e['loc'])) or 'root'}: {e['msg']}" for e in exc.errors()]


async def structured[T: BaseModel](
    llm: LLM,
    *,
    step: str,
    system: str,
    user: str,
    output: type[T],
    trace: Trace,
    validate: Callable[[T], list[str]] | None = None,
    max_attempts: int = 3,
) -> T:
    """Ask for `output`-shaped JSON; retry with the errors until it validates.

    `validate` returns extra problems (empty list = fine). If the last attempt still has
    validator problems, the parsed value is returned anyway and the caller decides; if it
    never parses, LLMError is raised.
    """
    schema = output.model_json_schema()
    messages: list[Message] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    last_parsed: T | None = None
    last_errors: list[str] = []

    for attempt in range(1, max_attempts + 1):
        reply = await llm.chat(messages, schema)
        parsed: T | None = None
        try:
            value = output.model_validate_json(reply.content)
        except ValidationError as exc:
            errors = _format_validation_error(exc)
        else:
            errors = validate(value) if validate else []
            parsed = last_parsed = value

        trace.calls.append(
            LLMCall(
                step=step,
                attempt=attempt,
                model=reply.model,
                latency_ms=reply.latency_ms,
                prompt_tokens=reply.prompt_tokens,
                completion_tokens=reply.completion_tokens,
                ok=not errors,
                errors=errors,
            )
        )
        if not errors and parsed is not None:
            return parsed

        last_errors = errors
        messages += [
            {"role": "assistant", "content": reply.content},
            {
                "role": "user",
                "content": "That JSON has problems:\n- "
                + "\n- ".join(errors)
                + "\nReturn the full corrected JSON. Change only what is needed to fix these.",
            },
        ]

    if last_parsed is not None:
        return last_parsed
    raise LLMError(f"{step}: no valid JSON after {max_attempts} attempts: {'; '.join(last_errors)}")
