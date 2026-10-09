"""A second agent in ~20 lines, reusing the framework unchanged (FR-9)."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from minagent import Agent, tool


class ReleaseNotes(BaseModel):
    headline: str
    highlights: list[str]
    breaking: list[str]


@tool
def read_changelog(path: str) -> str:
    """Read a changelog file and return its contents."""
    return Path(path).read_text(encoding="utf-8")


def build_agent(**kwargs) -> Agent:
    return Agent(
        name="release-notes",
        instructions=(
            "Draft release notes from a changelog. Call read_changelog to read the "
            "file, then produce the structured notes: a one-line headline, the key "
            "highlights, and any breaking changes."
        ),
        tools=[read_changelog],
        output_schema=ReleaseNotes,
        **kwargs,
    )
