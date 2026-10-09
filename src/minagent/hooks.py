"""Lifecycle hooks.

A hook is a callable invoked at one of four points in the loop. `before_model`
and `before_tool` hooks are gates: returning a `Decision` of `deny`/`ask`
constrains the action (combined with policy by `most_restrictive`). `after_model`
and `after_tool` hooks observe; their return value is ignored for now (structured
output in increment 4 is the first to use `after_model`).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional

from .policy import Decision
from .state import RunState


class HookPoint(str, Enum):
    before_model = "before_model"
    after_model = "after_model"
    before_tool = "before_tool"
    after_tool = "after_tool"


@dataclass
class HookContext:
    point: HookPoint
    state: RunState
    tool_name: Optional[str] = None
    args: Optional[dict] = None
    call_id: Optional[str] = None
    request: Any = None
    response: Any = None
    result: Any = None


Hook = Callable[[HookContext], Optional[Decision]]
