"""Replay provider.

Returns the recorded `llm_response` events in order instead of calling a model,
so a committed run can be re-driven with no API key and no network (spec §7.2,
C2). When the loop asks for more responses than were recorded, the run has
diverged from the recording and `ReplayDivergence` is raised.
"""

from __future__ import annotations

from ..provider import LLMRequest, LLMResponse, ReplayDivergence


class ReplayProvider:
    def __init__(self, responses: list[LLMResponse]) -> None:
        self._responses = list(responses)
        self._i = 0

    def complete(self, req: LLMRequest) -> LLMResponse:
        if self._i >= len(self._responses):
            raise ReplayDivergence(
                f"recording holds {len(self._responses)} model responses; "
                "the replayed run asked for another"
            )
        resp = self._responses[self._i]
        self._i += 1
        return resp
