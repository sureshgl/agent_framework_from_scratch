"""The secondary agent completes with no changes to the framework (FR-9)."""

from pathlib import Path

from conftest import FakeProvider, text_response, tool_response

from examples.release_notes.agent import ReleaseNotes, build_agent

NOTES_JSON = (
    '{"headline": "minagent 0.1: replay, MCP, and bounded context", '
    '"highlights": ["SlidingWindow context", "Agent.replay()", "MCPToolset"], '
    '"breaking": ["max_steps now seeds budgets"]}'
)


def test_secondary_agent_runs_with_fake_model(tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("- added replay\n- BREAKING: budgets\n")

    provider = FakeProvider([
        tool_response("c1", "read_changelog", {"path": str(changelog)}),
        text_response(NOTES_JSON),
    ])
    agent = build_agent(provider=provider, store_dir=str(tmp_path))
    result = agent.run("draft the notes")

    assert result.status == "completed"
    assert isinstance(result.output, ReleaseNotes)
    assert result.output.highlights and result.output.breaking


def test_sample_changelog_exists():
    assert (Path(__file__).resolve().parents[1]
            / "examples" / "release_notes" / "CHANGELOG.sample.md").exists()
