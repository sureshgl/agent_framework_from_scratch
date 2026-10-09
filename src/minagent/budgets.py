"""Budgets: named limits that end a run deterministically.

A budget is checked in the drive loop against the state projected from the log,
never against anything the loop holds in memory. When one trips, the loop
appends `budget_exceeded` and stops — a named terminal reason, not an exception.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from .events import Event
from .state import RunState

# (which, limit, actual) — what tripped, the configured ceiling, the observed value.
BudgetHit = tuple[str, float, float]


class Budgets(BaseModel):
    max_steps: int | None = None       # number of model calls (llm_response events)
    max_tokens: int | None = None      # cumulative input + output tokens
    max_cost_usd: float | None = None  # cumulative estimated cost
    max_tool_calls: int | None = None  # number of tool results
    max_wallclock_s: float | None = None  # seconds since the run started

    def check(self, state: RunState, elapsed_s: float) -> BudgetHit | None:
        """Return the first limit that is met or exceeded, or None."""
        if self.max_steps is not None and state.step_count >= self.max_steps:
            return ("max_steps", self.max_steps, state.step_count)
        if self.max_tokens is not None:
            total = state.usage.input_tokens + state.usage.output_tokens
            if total >= self.max_tokens:
                return ("max_tokens", self.max_tokens, total)
        if self.max_cost_usd is not None and state.usage.cost_usd >= self.max_cost_usd:
            return ("max_cost_usd", self.max_cost_usd, state.usage.cost_usd)
        if self.max_tool_calls is not None and state.tool_call_count >= self.max_tool_calls:
            return ("max_tool_calls", self.max_tool_calls, state.tool_call_count)
        if self.max_wallclock_s is not None and elapsed_s >= self.max_wallclock_s:
            return ("max_wallclock_s", self.max_wallclock_s, elapsed_s)
        return None


def elapsed_seconds(events: list[Event]) -> float:
    """Wall-clock seconds since the run's first event. Derived from the log so a
    resumed run measures from the original start."""
    if not events:
        return 0.0
    start = datetime.fromisoformat(events[0].ts)
    return (datetime.now(start.tzinfo) - start).total_seconds()
