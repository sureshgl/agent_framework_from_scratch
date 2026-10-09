import pytest

from minagent.builtins import read_file_tool, shell_tool, web_search_tool, write_file_tool


def test_read_file_within_root(tmp_path):
    (tmp_path / "a.txt").write_text("hello")
    assert read_file_tool(tmp_path).call(path="a.txt") == "hello"


def test_read_file_rejects_traversal(tmp_path):
    with pytest.raises(ValueError):
        read_file_tool(tmp_path).call(path="../secret")


def test_write_file_is_side_effecting_and_writes(tmp_path):
    wf = write_file_tool(tmp_path)
    assert wf.side_effecting is True
    wf.call(path="out/report.txt", content="hi")
    assert (tmp_path / "out" / "report.txt").read_text() == "hi"


def test_write_file_rejects_traversal(tmp_path):
    with pytest.raises(ValueError):
        write_file_tool(tmp_path).call(path="../evil.txt", content="x")


def test_shell_allowlist(tmp_path):
    sh = shell_tool(allow=["echo"], cwd=tmp_path)
    assert sh.side_effecting is True
    assert "hi" in sh.call(command="echo hi")
    with pytest.raises(ValueError):
        sh.call(command="rm -rf /")


def test_web_search_fixture_is_deterministic():
    ws = web_search_tool({"acme": "Acme Corp is a registered supplier."})
    assert "registered" in ws.call(query="background on Acme Corp")
    assert ws.call(query="unknown vendor") == "No results."
