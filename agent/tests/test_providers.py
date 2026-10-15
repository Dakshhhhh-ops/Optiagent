import json
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from optiagent_agent import llm as llm_module
from optiagent_agent.llm import LLMError, OpenAICompatibleLLM
from optiagent_agent.providers import LLMConfig, llm_status, make_llm

SCHEMA = {"type": "object", "properties": {"x": {"type": "integer"}}}
MESSAGES = [{"role": "system", "content": "Extract."}, {"role": "user", "content": "x is 3"}]


def ok(content: str = '{"x": 3}') -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": "m",
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 4},
        },
    )


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    async def instant(_: float) -> None:
        return None

    monkeypatch.setattr(llm_module, "_sleep", instant)


def make(handler: Any, **kw: Any) -> tuple[OpenAICompatibleLLM, list[dict[str, Any]]]:
    seen: list[dict[str, Any]] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append({"headers": dict(request.headers), "body": json.loads(request.content)})
        return handler(request, len(seen))  # type: ignore[no-any-return]

    client = OpenAICompatibleLLM(
        "https://llm.example/v1", "m", transport=httpx.MockTransport(record), **kw
    )
    return client, seen


async def test_sends_json_schema_and_key() -> None:
    client, seen = make(lambda r, n: ok(), api_key="secret")
    reply = await client.chat(MESSAGES, SCHEMA)
    assert reply.content == '{"x": 3}'
    assert (reply.prompt_tokens, reply.completion_tokens) == (10, 4)
    body = seen[0]["body"]
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["schema"] == SCHEMA
    assert body["temperature"] == 0
    assert seen[0]["headers"]["authorization"] == "Bearer secret"


async def test_falls_back_to_json_mode_when_schema_is_unsupported() -> None:
    def handler(request: httpx.Request, n: int) -> httpx.Response:
        if n == 1:
            return httpx.Response(
                400, json={"error": {"message": "response_format json_schema is not supported"}}
            )
        return ok()

    client, seen = make(handler)
    await client.chat(MESSAGES, SCHEMA)
    assert seen[1]["body"]["response_format"] == {"type": "json_object"}
    assert "matches this JSON schema" in seen[1]["body"]["messages"][0]["content"]
    assert client.json_schema_supported is False

    await client.chat(MESSAGES, SCHEMA)  # remembered: no second schema attempt
    assert seen[2]["body"]["response_format"] == {"type": "json_object"}


async def test_bad_key_gives_a_clear_error() -> None:
    client, _ = make(
        lambda r, n: httpx.Response(401, json={"error": {"message": "Invalid API Key"}})
    )
    with pytest.raises(LLMError, match="rejected the API key"):
        await client.chat(MESSAGES, SCHEMA)


async def test_retries_rate_limits_then_succeeds() -> None:
    client, seen = make(
        lambda r, n: httpx.Response(429, headers={"retry-after": "1"}) if n == 1 else ok()
    )
    reply = await client.chat(MESSAGES, SCHEMA)
    assert reply.content == '{"x": 3}'
    assert len(seen) == 2


async def test_gives_up_after_repeated_server_errors() -> None:
    client, seen = make(lambda r, n: httpx.Response(503, text="overloaded"), max_retries=2)
    with pytest.raises(LLMError, match="503"):
        await client.chat(MESSAGES, SCHEMA)
    assert len(seen) == 3


def test_make_llm_picks_the_provider() -> None:
    assert (
        type(make_llm(LLMConfig(provider="ollama", base_url="http://x", model="m"))).__name__
        == "OllamaLLM"
    )
    openai = make_llm(
        LLMConfig(provider="openai", base_url="http://x/v1", model="m", api_key=SecretStr("k"))
    )
    assert isinstance(openai, OpenAICompatibleLLM)
    assert openai.api_key == "k"


async def test_status_for_an_unreachable_provider() -> None:
    status = await llm_status(
        LLMConfig(provider="openai", base_url="http://127.0.0.1:1/v1", model="m"), timeout=1
    )
    assert status.reachable is False
    assert status.error
