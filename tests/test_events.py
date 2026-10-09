from minagent.events import EventLog, EventType


def test_append_assigns_gapfree_seq_and_persists(tmp_path):
    log = EventLog.create(tmp_path, "run1")
    a = log.append(EventType.run_started, {"task": "hi"})
    b = log.append("llm_request", {"model": "m"})

    assert [e.seq for e in log.events()] == [0, 1]
    assert a.seq == 0 and b.seq == 1
    assert a.ts and a.run_id == "run1"
    # one JSON object per line, written through to disk
    lines = log.path.read_text().splitlines()
    assert len(lines) == 2


def test_load_round_trips(tmp_path):
    log = EventLog.create(tmp_path, "run2")
    log.append("run_started", {"task": "t"})
    log.append("run_completed", {"output": "done"})

    reloaded = EventLog.load(log.path)
    assert reloaded.run_id == "run2"
    assert [e.type for e in reloaded.events()] == [
        EventType.run_started,
        EventType.run_completed,
    ]
    assert reloaded.events()[1].data["output"] == "done"


def test_subscribers_notified_in_order(tmp_path):
    seen = []
    log = EventLog.create(tmp_path, "run3")
    log.subscribe(lambda e: seen.append((e.seq, e.type)))
    log.append("run_started", {})
    log.append("run_completed", {})

    assert seen == [(0, EventType.run_started), (1, EventType.run_completed)]
