"""Shared test fixtures. Unit tests never hit the network: every run uses a
scripted `FakeProvider` in place of a real model."""

from __future__ import annotations

from minagent.messages import TextBlock, ToolUseBlock, Usage
from minagent.provider import LLMRequest, LLMResponse


class FakeProvider:
    """Returns pre-scripted `LLMResponse`s in order and records the requests."""

    def __init__(self, responses: list[LLMResponse]) -> None:
        self._responses = list(responses)
        self.requests: list[LLMRequest] = []

    def complete(self, req: LLMRequest) -> LLMResponse:
        self.requests.append(req)
        if not self._responses:
            raise AssertionError("FakeProvider ran out of scripted responses")
        return self._responses.pop(0)


def text_response(text: str, stop_reason: str = "end_turn") -> LLMResponse:
    return LLMResponse(
        content=[TextBlock(text=text)],
        stop_reason=stop_reason,
        usage=Usage(input_tokens=3, output_tokens=5),
    )


def tool_response(call_id: str, name: str, inp: dict) -> LLMResponse:
    return LLMResponse(
        content=[ToolUseBlock(id=call_id, name=name, input=inp)],
        stop_reason="tool_use",
        usage=Usage(input_tokens=3, output_tokens=5),
    )
