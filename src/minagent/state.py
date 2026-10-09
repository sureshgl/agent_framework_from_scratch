"""`project()`: fold the event log into the current run state.

This is the load-bearing function of the whole framework. The drive loop reads
state *only* from here, so a fresh run, a resumed run, crash recovery, and
replay all share one code path. Keep it a pure function of the events.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .events import Event, EventType
from .messages import Message, TextBlock, ToolResultBlock, ToolUseBlock, Usage


@dataclass
class PendingCall:
    call_id: str
    tool: str
    args: dict[str, Any]


@dataclass
class RunState:
    messages: list[Message] = field(default_factory=list)
    pending_calls: list[PendingCall] = field(default_factory=list)
    terminal: bool = False
    paused: bool = False
    status: str | None = None
    output: Any = None
    step_count: int = 0        # number of llm_response events
    tool_call_count: int = 0   # number of tool_result events
    usage: Usage = field(default_factory=Usage)
    approvals: dict[str, bool] = field(default_factory=dict)        # call_id -> decided
    approval_requests: dict[str, dict] = field(default_factory=dict)  # call_id -> {tool, args}


def _result_block(ev: Event) -> ToolResultBlock:
    data = ev.data
    if data.get("is_error"):
        return ToolResultBlock(
            tool_use_id=data["call_id"],
            content=str(data.get("error", "")),
            is_error=True,
        )
    result = data.get("result")
    content = result if isinstance(result, str) else json.dumps(result)
    return ToolResultBlock(tool_use_id=data["call_id"], content=content, is_error=False)


def project(events: list[Event]) -> RunState:
    state = RunState()
    pending_results: list[ToolResultBlock] = []
    last_response_blocks: list[Any] = []
    resolved_ids: set[str] = set()

    def flush_results() -> None:
        if pending_results:
            state.messages.append(Message(role="user", content=list(pending_results)))
            pending_results.clear()

    for ev in events:
        if ev.type == EventType.run_started:
            flush_results()
            state.messages.append(
                Message(role="user", content=[TextBlock(text=ev.data.get("task", ""))])
            )
        elif ev.type == EventType.llm_response:
            flush_results()
            blocks = [_block_from_dict(b) for b in ev.data.get("content", [])]
            state.messages.append(Message(role="assistant", content=blocks))
            last_response_blocks = blocks
            state.step_count += 1
            state.usage = state.usage + Usage.model_validate(ev.data.get("usage", {}))
        elif ev.type == EventType.tool_result:
            pending_results.append(_result_block(ev))
            resolved_ids.add(ev.data["call_id"])
            state.tool_call_count += 1
        elif ev.type == EventType.approval_requested:
            state.approval_requests[ev.data["call_id"]] = {
                "tool": ev.data.get("tool"),
                "args": ev.data.get("args", {}),
            }
        elif ev.type == EventType.approval_decided:
            state.approvals[ev.data["call_id"]] = bool(ev.data["approved"])
        elif ev.type == EventType.output_rejected:
            flush_results()
            feedback = (
                "Your previous response did not match the required JSON schema.\n"
                f"Validation error:\n{ev.data.get('error', '')}\n"
                "Respond again with ONLY a JSON value matching the schema."
            )
            state.messages.append(Message(role="user", content=[TextBlock(text=feedback)]))
        elif ev.type == EventType.run_completed:
            state.terminal = True
            state.status = "completed"
            state.output = ev.data.get("output")
        elif ev.type == EventType.budget_exceeded:
            state.terminal = True
            state.status = "budget_exceeded"
        elif ev.type == EventType.run_failed:
            state.terminal = True
            state.status = "failed"
        elif ev.type == EventType.run_paused:
            state.status = "paused"

    flush_results()

    # A run is paused iff its very last event is run_paused (a resume appends
    # run_resumed after it, so a resumed run is no longer paused).
    state.paused = bool(events) and events[-1].type == EventType.run_paused
    if state.paused and state.status is None:
        state.status = "paused"

    # Pending tool calls = tool_use blocks from the last response not yet resolved.
    if not state.terminal:
        for block in last_response_blocks:
            if isinstance(block, ToolUseBlock) and block.id not in resolved_ids:
                state.pending_calls.append(
                    PendingCall(call_id=block.id, tool=block.name, args=block.input)
                )

    return state


def _block_from_dict(d: dict[str, Any]) -> Any:
    kind = d.get("type")
    if kind == "text":
        return TextBlock(text=d.get("text", ""))
    if kind == "tool_use":
        return ToolUseBlock(id=d["id"], name=d["name"], input=d.get("input", {}))
    if kind == "tool_result":
        return ToolResultBlock(
            tool_use_id=d["tool_use_id"],
            content=d.get("content", ""),
            is_error=d.get("is_error", False),
        )
    raise ValueError(f"unknown content block type: {kind!r}")
