from conftest import FakeProvider, text_response

from pydantic import BaseModel

from minagent.agent import Agent
from minagent.events import EventLog, EventType
from minagent.output import extract_json, validate_output


class Answer(BaseModel):
    value: int
    label: str


VALID = '{"value": 42, "label": "answer"}'


def _types(result):
    return [e.type for e in EventLog.load(result.log_path).events()]


def test_valid_output_completes_with_typed_object(tmp_path):
    agent = Agent("t", "x", provider=FakeProvider([text_response(VALID)]),
                  output_schema=Answer, store_dir=tmp_path)
    result = agent.run("answer please")

    assert result.status == "completed"
    assert isinstance(result.output, Answer)
    assert result.output.value == 42 and result.output.label == "answer"
    # the log stores the validated value as JSON-able data, not the prose
    completed = EventLog.load(result.log_path).events()[-1]
    assert completed.data["output"] == {"value": 42, "label": "answer"}


def test_schema_is_offered_to_the_model(tmp_path):
    provider = FakeProvider([text_response(VALID)])
    agent = Agent("t", "base instructions", provider=provider,
                  output_schema=Answer, store_dir=tmp_path)
    agent.run("go")
    system = provider.requests[0].system
    assert "base instructions" in system
    assert "JSON Schema" in system and "value" in system


def test_invalid_then_valid_retries_with_feedback(tmp_path):
    provider = FakeProvider([text_response("I think it's 42"), text_response(VALID)])
    agent = Agent("t", "x", provider=provider, output_schema=Answer, store_dir=tmp_path)
    result = agent.run("go")

    assert result.status == "completed"
    assert isinstance(result.output, Answer)
    types = _types(result)
    assert types.count(EventType.output_rejected) == 1
    assert types.count(EventType.llm_response) == 2


def test_retries_exhausted_fails_with_validation_error(tmp_path):
    # default max_output_retries=2 => 3 attempts total, then fail
    provider = FakeProvider([text_response("nope"), text_response("still nope"),
                             text_response("nope again")])
    agent = Agent("t", "x", provider=provider, output_schema=Answer, store_dir=tmp_path)
    result = agent.run("go")

    assert result.status == "failed"
    failed = EventLog.load(result.log_path).events()[-1]
    assert failed.type == EventType.run_failed
    assert failed.data["where"] == "output_validation"
    assert _types(result).count(EventType.output_rejected) == 2


def test_max_output_retries_zero_fails_on_first_bad_answer(tmp_path):
    provider = FakeProvider([text_response("not json")])
    agent = Agent("t", "x", provider=provider, output_schema=Answer,
                  max_output_retries=0, store_dir=tmp_path)
    result = agent.run("go")
    assert result.status == "failed"
    assert _types(result).count(EventType.output_rejected) == 0


def test_no_schema_leaves_output_as_text(tmp_path):
    agent = Agent("t", "x", provider=FakeProvider([text_response("just text")]),
                  store_dir=tmp_path)
    result = agent.run("go")
    assert result.status == "completed"
    assert result.output == "just text"


def test_extract_and_validate_helpers():
    assert extract_json('here is ```json\n{"value":1,"label":"a"}\n``` done').strip().startswith("{")
    assert extract_json('prose {"value": 1, "label": "a"} trailing') == '{"value": 1, "label": "a"}'
    obj, err = validate_output(Answer, VALID)
    assert err is None and obj.value == 42
    bad, err2 = validate_output(Answer, "no json")
    assert bad is None and err2
