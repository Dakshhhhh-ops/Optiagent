"""Structured LLM calls with validation-driven retries.

Every call asks for JSON matching a Pydantic model's schema. If the reply fails to parse or
fails an extra validator, the errors go back to the model and it gets another attempt.
Each attempt is recorded so latency and call counts can be reported.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, Field, ValidationError

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
    step: str
    attempt: int
    model: str
    latency_ms: float
    prompt_tokens: int = 0
    completion_tokens: int = 0
    ok: bool
    errors: list[str] = Field(default_factory=list)


class Trace(BaseModel):
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
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMError(f"Ollama request failed: {type(exc).__name__}: {exc}") from exc
        data = response.json()
        return LLMReply(
            content=data["message"]["content"],
            model=data.get("model", self.model),
            latency_ms=(time.perf_counter() - start) * 1000,
            prompt_tokens=data.get("prompt_eval_count", 0),
            completion_tokens=data.get("eval_count", 0),
        )


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
