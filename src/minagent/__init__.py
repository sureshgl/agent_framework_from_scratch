"""minagent — a minimal agent framework where a run is an append-only event log.

Public API (increment 1). More is exported as later increments land.
"""

from .agent import DEFAULT_MODEL, Agent, RunResult
from .budgets import Budgets
from .builtins import read_file_tool, shell_tool, web_search_tool, write_file_tool
from .events import Event, EventLog, EventType
from .mcp_tools import MCPToolset
from .hooks import Hook, HookContext, HookPoint
from .loop import Approver
from .messages import (
    ContentBlock,
    Message,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    Usage,
)
from .output import schema_instructions, validate_output
from .policy import ApprovalRequest, Decision, Policy, Rule, most_restrictive
from .provider import LLMRequest, LLMResponse, Provider, ToolSpec
from .state import PendingCall, RunState, project
from .tools import Tool, tool
from .tracing import ConsoleTracer

__all__ = [
    "Agent",
    "RunResult",
    "DEFAULT_MODEL",
    "Budgets",
    "Policy",
    "Rule",
    "Decision",
    "most_restrictive",
    "ApprovalRequest",
    "Approver",
    "Hook",
    "HookContext",
    "HookPoint",
    "schema_instructions",
    "validate_output",
    "read_file_tool",
    "write_file_tool",
    "shell_tool",
    "web_search_tool",
    "MCPToolset",
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
