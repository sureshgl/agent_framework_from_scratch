"""The model boundary.

`Provider` is the only seam through which the loop reaches a model. Everything
the loop needs is expressed in neutral types (`messages.py`); concrete adapters
live in `providers/`.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from .messages import ContentBlock, Message, Usage


class ToolSpec(BaseModel):
    """A tool as advertised to the model."""

    name: str
    description: str
    input_schema: dict


class LLMRequest(BaseModel):
    system: str
    messages: list[Message]
    tools: list[ToolSpec] = Field(default_factory=list)
    model: str
    max_tokens: int = 1024


class LLMResponse(BaseModel):
    content: list[ContentBlock]
    stop_reason: str
    usage: Usage = Field(default_factory=Usage)


@runtime_checkable
class Provider(Protocol):
    def complete(self, req: LLMRequest) -> LLMResponse: ...


class ReplayDivergence(Exception):
    """Raised during replay when the live loop asks for a model response the
    recording does not contain — i.e. the run diverged from what was recorded."""
