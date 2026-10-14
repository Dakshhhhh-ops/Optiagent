"""A scripted LLM for tests: replays fixed replies and records what it was sent."""

from __future__ import annotations

import json
from typing import Any

from optiagent_agent.llm import LLMReply, Message


class FakeLLM:
    model = "fake"

    def __init__(self, *replies: str | dict[str, Any]) -> None:
        self.replies = [r if isinstance(r, str) else json.dumps(r) for r in replies]
        self.seen: list[list[Message]] = []

    async def chat(self, messages: list[Message], schema: dict[str, Any]) -> LLMReply:
        self.seen.append(list(messages))
        return LLMReply(content=self.replies.pop(0), model=self.model, latency_ms=1.0)
