"""Anthropic adapter.

Maps the neutral `LLMRequest`/`Message` types to the `anthropic` SDK and back.
The SDK client is created lazily on first use so importing this module (or
building an Agent that is never run live) needs neither the package nor a key.
This module is exercised by the live demo, not by unit tests.
"""

from __future__ import annotations

from typing import Any

from ..messages import Message, TextBlock, ToolUseBlock, Usage
from ..provider import LLMRequest, LLMResponse


def _to_api_message(msg: Message) -> dict[str, Any]:
    return {"role": msg.role, "content": [b.model_dump() for b in msg.content]}


def _from_api_content(content: list[Any]) -> list[Any]:
    blocks: list[Any] = []
    for block in content:
        if block.type == "text":
            blocks.append(TextBlock(text=block.text))
        elif block.type == "tool_use":
            blocks.append(ToolUseBlock(id=block.id, name=block.name, input=dict(block.input)))
    return blocks


class AnthropicProvider:
    def __init__(self, client: Any | None = None) -> None:
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic()
        return self._client

    def complete(self, req: LLMRequest) -> LLMResponse:
        resp = self.client.messages.create(
            model=req.model,
            max_tokens=req.max_tokens,
            system=req.system,
            tools=[t.model_dump() for t in req.tools],
            messages=[_to_api_message(m) for m in req.messages],
        )
        return LLMResponse(
            content=_from_api_content(resp.content),
            stop_reason=resp.stop_reason or "end_turn",
            usage=Usage(
                input_tokens=resp.usage.input_tokens,
                output_tokens=resp.usage.output_tokens,
            ),
        )
