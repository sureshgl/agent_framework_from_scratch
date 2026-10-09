"""The drive loop.

One function, `drive(agent, log, approver)`, advances a run until it reaches a
terminal event or pauses for approval. It recomputes state from the log at the
top of every iteration and holds nothing else, so run / resume / replay all share
this code path.

Each pending tool call is settled one at a time: decide (policy combined with
`before_tool` hooks) -> on `deny` emit an error result; on `ask` either consult
an inline approver or pause the run; on `allow`/approved, validate the arguments
and execute. Tool and validation errors become error results so the model can
self-correct; they never crash the loop.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Optional, TYPE_CHECKING

from pydantic import BaseModel, ValidationError

from .budgets import elapsed_seconds
from .events import EventLog
from .hooks import HookContext, HookPoint
from .messages import TextBlock, ToolUseBlock
from .output import schema_instructions, validate_output
from .policy import ApprovalRequest, Decision, most_restrictive
from .provider import LLMRequest, ToolSpec
from .state import PendingCall, RunState, project

if TYPE_CHECKING:
    from .agent import Agent
    from .tools import Tool

Approver = Callable[[ApprovalRequest], bool]


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump()
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return str(value)
    return value


def _error_result(log: EventLog, call: PendingCall, error: str) -> None:
    log.append(
        "tool_result",
        {"call_id": call.call_id, "tool": call.tool, "is_error": True, "error": error},
    )


def _effective_decision(agent: "Agent", tool: "Tool", call: PendingCall, state: RunState) -> Decision:
    decisions = [agent.policy.decide(tool.name, tool.side_effecting)]
    ctx = HookContext(
        point=HookPoint.before_tool,
        state=state,
        tool_name=tool.name,
        args=call.args,
        call_id=call.call_id,
    )
    for hook in agent.hooks:
        d = hook(ctx)
        if d is not None:
            decisions.append(d)
    return most_restrictive(decisions)


def _execute(agent: "Agent", log: EventLog, tool: "Tool", call: PendingCall, state: RunState) -> None:
    log.append("tool_started", {"call_id": call.call_id, "tool": call.tool, "args": call.args})
    try:
        kwargs = tool.validate(call.args)
    except ValidationError as e:
        _error_result(log, call, f"invalid arguments: {e}")
        return
    try:
        result = tool.call(**kwargs)
    except Exception as e:  # tools never crash the loop; the model self-corrects
        _error_result(log, call, f"{type(e).__name__}: {e}")
        return
    log.append(
        "tool_result",
        {"call_id": call.call_id, "tool": call.tool, "result": _jsonable(result), "is_error": False},
    )
    for hook in agent.hooks:
        hook(HookContext(point=HookPoint.after_tool, state=state, tool_name=tool.name,
                         args=call.args, call_id=call.call_id, result=result))


def _settle_call(
    agent: "Agent", log: EventLog, call: PendingCall, state: RunState, approver: Optional[Approver]
) -> bool:
    """Settle one pending call. Returns True if the run must pause."""
    tool = agent.tools_by_name.get(call.tool)
    if tool is None:
        _error_result(log, call, f"unknown tool: {call.tool!r}")
        return False

    decision = _effective_decision(agent, tool, call, state)

    if decision.action == "deny":
        _error_result(log, call, f"denied by policy: {decision.reason}")
        return False

    if decision.action == "ask":
        if call.call_id in state.approvals:
            if not state.approvals[call.call_id]:
                _error_result(log, call, "denied by approver")
                return False
            # approved -> fall through to execution
        else:
            if call.call_id not in state.approval_requests:
                log.append(
                    "approval_requested",
                    {"call_id": call.call_id, "tool": call.tool, "args": call.args},
                )
            if approver is not None:
                approved = bool(approver(ApprovalRequest(call_id=call.call_id, tool=call.tool, args=call.args)))
                log.append(
                    "approval_decided",
                    {"call_id": call.call_id, "approved": approved, "by": "approver"},
                )
                return False  # re-project; an approved call executes on the next pass
            log.append("run_paused", {"pending": [call.call_id]})
            return True

    _execute(agent, log, tool, call, state)
    return False


def drive(agent: "Agent", log: EventLog, approver: Optional[Approver] = None) -> None:
    while True:
        state = project(log.events())

        if state.terminal or state.paused:
            break

        if state.pending_calls:
            # Settle one call per iteration, then re-project.
            if _settle_call(agent, log, state.pending_calls[0], state, approver):
                break
            continue

        hit = agent.budgets.check(state, elapsed_seconds(log.events()))
        if hit is not None:
            which, limit, actual = hit
            log.append("budget_exceeded", {"which": which, "limit": limit, "actual": actual})
            break

        system = agent.instructions
        if agent.output_schema is not None:
            system = f"{system}\n\n{schema_instructions(agent.output_schema)}"
        req = LLMRequest(
            system=system,
            messages=state.messages,
            tools=[ToolSpec(**t.spec_dict()) for t in agent.tools],
            model=agent.model,
            max_tokens=agent.max_tokens,
        )
        for hook in agent.hooks:
            d = hook(HookContext(point=HookPoint.before_model, state=state, request=req))
            if d is not None and d.action == "deny":
                log.append("run_failed", {"error": f"denied by hook: {d.reason}", "where": "before_model"})
                return

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
        for hook in agent.hooks:
            hook(HookContext(point=HookPoint.after_model, state=state, response=resp))

        if not any(isinstance(b, ToolUseBlock) for b in resp.content):
            text = "".join(b.text for b in resp.content if isinstance(b, TextBlock))
            if agent.output_schema is None:
                log.append("run_completed", {"output": text, "usage_total": resp.usage.model_dump()})
                break

            obj, error = validate_output(agent.output_schema, text)
            if error is None:
                log.append("run_completed", {"output": obj.model_dump(),
                                             "usage_total": resp.usage.model_dump()})
                break
            # Retry with feedback, bounded by max_output_retries.
            attempts = sum(1 for ev in log.events()
                           if ev.type.value == "output_rejected")
            if attempts >= agent.max_output_retries:
                log.append("run_failed", {
                    "error": f"output did not match schema after {attempts} retries: {error}",
                    "where": "output_validation"})
                break
            log.append("output_rejected", {"error": error, "attempt": attempts + 1})
