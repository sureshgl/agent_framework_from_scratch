"""minagent — a minimal agent framework where a run is an append-only event log.

Public API (increment 1). More is exported as later increments land.
"""

from .agent import DEFAULT_MODEL, Agent, RunResult
from .budgets import Budgets
from .events import Event, EventLog, EventType
from .messages import (
    ContentBlock,
    Message,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    Usage,
)
from .provider import LLMRequest, LLMResponse, Provider, ToolSpec
from .state import PendingCall, RunState, project
from .tools import Tool, tool
from .tracing import ConsoleTracer

__all__ = [
    "Agent",
    "RunResult",
    "DEFAULT_MODEL",
    "Budgets",
    "tool",
    "Tool",
    "Event",
    "EventType",
    "EventLog",
    "project",
    "RunState",
    "PendingCall",
    "Message",
    "ContentBlock",
    "TextBlock",
    "ToolUseBlock",
    "ToolResultBlock",
    "Usage",
    "Provider",
    "LLMRequest",
    "LLMResponse",
    "ToolSpec",
    "ConsoleTracer",
]
