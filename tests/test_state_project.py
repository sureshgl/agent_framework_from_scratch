from minagent.events import Event, EventType
from minagent.messages import TextBlock, ToolResultBlock, ToolUseBlock
from minagent.state import project


def _ev(seq, type, data):
    return Event(seq=seq, type=EventType(type), ts="t", run_id="r", data=data)


def test_messages_interleave_task_response_and_results():
    events = [
        _ev(0, "run_started", {"task": "do it"}),
        _ev(1, "llm_response", {
            "content": [{"type": "tool_use", "id": "c1", "name": "add", "input": {"a": 1, "b": 2}}],
            "stop_reason": "tool_use", "usage": {"input_tokens": 1, "output_tokens": 1},
        }),
        _ev(2, "tool_started", {"call_id": "c1", "tool": "add", "args": {"a": 1, "b": 2}}),
        _ev(3, "tool_result", {"call_id": "c1", "tool": "add", "result": 3, "is_error": False}),
    ]
    state = project(events)

    roles = [m.role for m in state.messages]
    assert roles == ["user", "assistant", "user"]
    assert isinstance(state.messages[1].content[0], ToolUseBlock)
    result_block = state.messages[2].content[0]
    assert isinstance(result_block, ToolResultBlock)
    assert result_block.content == "3" and result_block.is_error is False


def test_pending_calls_are_unresolved_tool_uses_from_last_response():
    events = [
        _ev(0, "run_started", {"task": "x"}),
        _ev(1, "llm_response", {
            "content": [{"type": "tool_use", "id": "c9", "name": "add", "input": {"a": 1, "b": 1}}],
            "stop_reason": "tool_use", "usage": {},
        }),
    ]
    state = project(events)
    assert len(state.pending_calls) == 1
    assert state.pending_calls[0].call_id == "c9"
    assert state.pending_calls[0].tool == "add"
    assert state.step_count == 1

    # once the result is logged, nothing is pending
    events.append(_ev(2, "tool_result", {"call_id": "c9", "result": 2, "is_error": False}))
    assert project(events).pending_calls == []


def test_error_result_renders_as_error_block():
    events = [
        _ev(0, "run_started", {"task": "x"}),
        _ev(1, "llm_response", {
            "content": [{"type": "tool_use", "id": "c1", "name": "nope", "input": {}}],
            "stop_reason": "tool_use", "usage": {},
        }),
        _ev(2, "tool_result", {"call_id": "c1", "is_error": True, "error": "unknown tool"}),
    ]
    block = project(events).messages[-1].content[0]
    assert isinstance(block, ToolResultBlock)
    assert block.is_error is True and block.content == "unknown tool"


def test_terminal_status_and_output():
    events = [
        _ev(0, "run_started", {"task": "x"}),
        _ev(1, "llm_response", {"content": [{"type": "text", "text": "answer"}], "usage": {}}),
        _ev(2, "run_completed", {"output": "answer"}),
    ]
    state = project(events)
    assert state.terminal is True
    assert state.status == "completed"
    assert state.output == "answer"
    assert state.pending_calls == []
    assert isinstance(state.messages[1].content[0], TextBlock)
