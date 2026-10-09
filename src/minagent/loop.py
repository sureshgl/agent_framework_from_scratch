"""The drive loop.

One function, `drive(agent, log)`, advances a run until it reaches a terminal
event. It recomputes state from the log at the top of every iteration and holds
nothing else, so run / resume / replay all share this code path.

Increment 1 scope: settle pending tool calls, enforce a `max_steps` budget, call
the model, and complete when the model stops requesting tools. Policy, approval,
and richer budgets arrive in later increments.
"""

from __future__ import annotations

import json
from typing import Any, TYPE_CHECKING

from pydantic import BaseModel, ValidationError

from .budgets import elapsed_seconds
from .events import EventLog
from .messages import TextBlock, ToolUseBlock
from .provider import LLMRequest, ToolSpec
from .state import PendingCall, project

if TYPE_CHECKING:
    from .agent import Agent


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump()
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return str(value)
    return value


def _settle_call(agent: "Agent", log: EventLog, call: PendingCall) -> None:
    tool = agent.tools_by_name.get(call.tool)
    if tool is None:
        log.append(
            "tool_result",
            {"call_id": call.call_id, "tool": call.tool, "is_error": True,
             "error": f"unknown tool: {call.tool!r}"},
        )
        return

    log.append("tool_started", {"call_id": call.call_id, "tool": call.tool, "args": call.args})
    try:
        kwargs = tool.validate(call.args)
    except ValidationError as e:
        log.append(
            "tool_result",
            {"call_id": call.call_id, "tool": call.tool, "is_error": True,
             "error": f"invalid arguments: {e}"},
        )
        return
    try:
        result = tool.call(**kwargs)
    except Exception as e:  # tools never crash the loop; the model self-corrects
        log.append(
            "tool_result",
            {"call_id": call.call_id, "tool": call.tool, "is_error": True,
             "error": f"{type(e).__name__}: {e}"},
        )
        return
    log.append(
        "tool_result",
        {"call_id": call.call_id, "tool": call.tool, "result": _jsonable(result),
         "is_error": False},
    )


def drive(agent: "Agent", log: EventLog) -> None:
    while True:
        state = project(log.events())

        if state.terminal or state.status == "paused":
            break

        if state.pending_calls:
            for call in state.pending_calls:
                _settle_call(agent, log, call)
            continue

        hit = agent.budgets.check(state, elapsed_seconds(log.events()))
        if hit is not None:
            which, limit, actual = hit
            log.append("budget_exceeded", {"which": which, "limit": limit, "actual": actual})
            break

        req = LLMRequest(
            system=agent.instructions,
            messages=state.messages,
            tools=[ToolSpec(**t.spec_dict()) for t in agent.tools],
            model=agent.model,
            max_tokens=agent.max_tokens,
        )
        log.append("llm_request", {"model": agent.model, "n_messages": len(state.messages)})
        try:
            resp = agent.provider.complete(req)
        except Exception as e:
            log.append("run_failed", {"error": f"{type(e).__name__}: {e}", "where": "provider"})
            break
        log.append(
            "llm_response",
            {"content": [b.model_dump() for b in resp.content],
             "stop_reason": resp.stop_reason,
             "usage": resp.usage.model_dump()},
        )

        if not any(isinstance(b, ToolUseBlock) for b in resp.content):
            text = "".join(b.text for b in resp.content if isinstance(b, TextBlock))
            log.append("run_completed", {"output": text, "usage_total": resp.usage.model_dump()})
            break
