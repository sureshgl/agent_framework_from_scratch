"""Policy: per-tool allow / ask / deny, enforced in the runtime.

Rules are globs over tool names; the first match wins and an unmatched tool is
denied (fail-closed). Side-effecting tools are floored at `ask` even when a
broader rule would allow them, so a mistaken `*: allow` can never silently let a
posting tool run unapproved. Policy lives here; it is applied in the drive loop,
never in a prompt.
"""

from __future__ import annotations

from fnmatch import fnmatchcase
from typing import Literal

from pydantic import BaseModel, Field

Action = Literal["allow", "ask", "deny"]
_RANK: dict[str, int] = {"allow": 0, "ask": 1, "deny": 2}


class Decision(BaseModel):
    action: Action
    reason: str = ""


class Rule(BaseModel):
    pattern: str  # glob over the tool name, e.g. "post_*", "erp.read_*", "*"
    action: Action


def most_restrictive(decisions: list[Decision]) -> Decision:
    """Combine decisions so deny > ask > allow. Used to merge policy with hooks."""
    return max(decisions, key=lambda d: _RANK[d.action])


class Policy(BaseModel):
    rules: list[Rule] = Field(
        default_factory=lambda: [Rule(pattern="*", action="allow")]
    )

    def decide(self, tool_name: str, side_effecting: bool = False) -> Decision:
        matched: Rule | None = None
        for rule in self.rules:
            if fnmatchcase(tool_name, rule.pattern):
                matched = rule
                break
        if matched is None:
            return Decision(action="deny", reason="no matching rule (fail-closed)")
        action: Action = matched.action
        reason = f"rule {matched.pattern!r} -> {matched.action}"
        if side_effecting and action == "allow":
            action = "ask"
            reason = f"{reason}; side-effecting floored to ask"
        return Decision(action=action, reason=reason)


class ApprovalRequest(BaseModel):
    call_id: str
    tool: str
    args: dict
