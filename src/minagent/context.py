"""Context strategies: choose the model's *view* of the conversation.

The event log always keeps everything; a `ContextStrategy` decides which messages
are sent to the model on a given turn. `FullHistory` sends all of them;
`SlidingWindow` keeps the task plus the most recent N, which is enough for long
runs without unbounded prompts.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .messages import Message, ToolResultBlock


@runtime_checkable
class ContextStrategy(Protocol):
    def view(self, messages: list[Message]) -> list[Message]: ...


class FullHistory:
    def view(self, messages: list[Message]) -> list[Message]:
        return list(messages)


def _is_tool_result_only(msg: Message) -> bool:
    return bool(msg.content) and all(isinstance(b, ToolResultBlock) for b in msg.content)


class SlidingWindow:
    """Keep the first message (the task) and the most recent `max_messages`.

    The window never *starts* on a user message made only of tool_result blocks,
    which would reference a tool_use that fell outside the window and be rejected
    by the model. Such leading messages are dropped from the tail.
    """

    def __init__(self, max_messages: int) -> None:
        if max_messages < 1:
            raise ValueError("max_messages must be >= 1")
        self.max_messages = max_messages

    def view(self, messages: list[Message]) -> list[Message]:
        if len(messages) <= self.max_messages:
            return list(messages)
        head = messages[:1]
        tail = messages[-(self.max_messages - 1):] if self.max_messages > 1 else []
        while tail and _is_tool_result_only(tail[0]):
            tail = tail[1:]
        return head + tail
