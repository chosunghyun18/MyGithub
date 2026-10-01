from autocommit.batcher import ChangeBatcher


def test_empty_never_due():
    b = ChangeBatcher(quiet_seconds=5)
    assert b.flush_if_due(100.0) is None


def test_flush_after_quiet_period_and_dedupe():
    b = ChangeBatcher(quiet_seconds=5, max_wait_seconds=60)
    b.add("b.md", 0.0)
    b.add("a.md", 1.0)
    b.add("b.md", 2.0)  # 같은 파일 재저장 → 한 번만
    assert b.flush_if_due(6.9) is None  # 마지막 변경(2.0)으로부터 4.9초
    assert b.flush_if_due(7.0) == ["a.md", "b.md"]
    assert b.flush_if_due(100.0) is None  # 비워졌음


def test_continuous_edits_reset_quiet_timer():
    b = ChangeBatcher(quiet_seconds=5, max_wait_seconds=60)
    for t in range(0, 20, 2):  # 2초마다 저장 → quiet 조건 미충족
        b.add("x.md", float(t))
        assert b.flush_if_due(float(t) + 1) is None


def test_max_wait_forces_flush():
    b = ChangeBatcher(quiet_seconds=5, max_wait_seconds=10)
    t = 0.0
    flushed = None
    while flushed is None:
        b.add("x.md", t)
        flushed = b.flush_if_due(t)
        t += 1.0
    assert flushed == ["x.md"]
    assert t - 1.0 == 10.0  # 첫 변경 후 정확히 max_wait 시점


def test_new_batch_after_flush_restarts_timers():
    b = ChangeBatcher(quiet_seconds=5, max_wait_seconds=10)
    b.add("a.md", 0.0)
    assert b.flush_if_due(5.0) == ["a.md"]
    b.add("c.md", 50.0)
    assert b.flush_if_due(54.0) is None
    assert b.flush_if_due(55.0) == ["c.md"]
