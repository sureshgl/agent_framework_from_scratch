"""Console tracer.

A subscriber that renders events to stdout as they are appended. It is just a
`Callable[[Event], None]`; the JSONL file remains the canonical trace.
"""

from __future__ import annotations

from .events import Event, EventType


def _summary(ev: Event) -> str:
    d = ev.data
    if ev.type == EventType.run_started:
        return f"task={d.get('task', '')!r} model={d.get('model', '')}"
    if ev.type == EventType.llm_request:
        return f"-> model ({d.get('n_messages', 0)} msgs)"
    if ev.type == EventType.llm_response:
        return f"stop={d.get('stop_reason', '')}"
    if ev.type == EventType.tool_started:
        return f"{d.get('tool', '')}({d.get('args', {})})"
    if ev.type == EventType.tool_result:
        return f"{d.get('tool', '')} -> {'ERROR ' + str(d.get('error')) if d.get('is_error') else 'ok'}"
    if ev.type == EventType.budget_exceeded:
        return f"{d.get('which')}={d.get('actual')}/{d.get('limit')}"
    if ev.type == EventType.run_completed:
        return f"output={str(d.get('output', ''))[:80]!r}"
    if ev.type == EventType.run_failed:
        return f"error={d.get('error', '')}"
    return ""


class ConsoleTracer:
    def __init__(self, prefix: str = "") -> None:
        self.prefix = prefix

    def __call__(self, ev: Event) -> None:
        print(f"{self.prefix}[{ev.seq:02d}] {ev.type.value:<18} {_summary(ev)}")
