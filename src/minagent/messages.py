"""Neutral message types shared by every provider.

One `Message`/`ContentBlock` vocabulary sits between the drive loop and any
vendor SDK. Adapters translate these to and from their wire format; the loop,
the event log, and the tools never import a provider SDK.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field


class TextBlock(BaseModel):
    type: Literal["text"] = "text"
    text: str


class ToolUseBlock(BaseModel):
    """A model's request to call a tool. `id` is the call id tool results key off."""

    type: Literal["tool_use"] = "tool_use"
    id: str
    name: str
    input: dict[str, Any] = Field(default_factory=dict)


class ToolResultBlock(BaseModel):
    """The result of a tool call, carried back to the model in a user message."""

    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str
    content: str
    is_error: bool = False


ContentBlock = Annotated[
    Union[TextBlock, ToolUseBlock, ToolResultBlock],
    Field(discriminator="type"),
]


class Message(BaseModel):
    """A turn in the conversation. Tool results ride in `user` messages, as
    Anthropic expects; the system prompt is carried on `LLMRequest`, not here."""

    role: Literal["user", "assistant"]
    content: list[ContentBlock]


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cost_usd=self.cost_usd + other.cost_usd,
        )
