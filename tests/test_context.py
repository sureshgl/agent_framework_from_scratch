import pytest

from minagent.context import FullHistory, SlidingWindow
from minagent.messages import Message, TextBlock, ToolResultBlock, ToolUseBlock


def _user(text):
    return Message(role="user", content=[TextBlock(text=text)])


def _assistant_tool(call_id):
    return Message(role="assistant", content=[ToolUseBlock(id=call_id, name="t", input={})])


def _tool_result(call_id):
    return Message(role="user", content=[ToolResultBlock(tool_use_id=call_id, content="r")])


def test_full_history_returns_everything():
    msgs = [_user("task"), _assistant_tool("c1"), _tool_result("c1")]
    assert FullHistory().view(msgs) == msgs


def test_sliding_window_keeps_task_and_recent():
    msgs = [_user("task")] + [_user(f"m{i}") for i in range(10)]
    view = SlidingWindow(max_messages=4).view(msgs)
    assert len(view) == 4
    assert view[0].content[0].text == "task"   # task always kept
    assert view[-1].content[0].text == "m9"     # most recent kept


def test_sliding_window_noop_when_short():
    msgs = [_user("task"), _user("m1")]
    assert SlidingWindow(max_messages=5).view(msgs) == msgs


def test_sliding_window_does_not_start_on_orphan_tool_result():
    # task, then alternating assistant tool_use / user tool_result turns
    msgs = [_user("task")]
    for i in range(6):
        msgs.append(_assistant_tool(f"c{i}"))
        msgs.append(_tool_result(f"c{i}"))
    view = SlidingWindow(max_messages=4).view(msgs)
    # the first message after the task must not be a bare tool_result
    assert all(isinstance(b, TextBlock) for b in view[0].content)
    first_tail = view[1]
    assert not all(isinstance(b, ToolResultBlock) for b in first_tail.content)


def test_sliding_window_rejects_bad_size():
    with pytest.raises(ValueError):
        SlidingWindow(max_messages=0)
