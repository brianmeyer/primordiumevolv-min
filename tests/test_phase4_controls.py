from app import code_loop

def test_idempotent_enqueue():
    # Enqueue same run id twice; second should be ignored
    code_loop._processed_ids.clear()
    code_loop._queue.clear()
    ok1 = code_loop.maybe_enqueue(123)
    ok2 = code_loop.maybe_enqueue(123)
    assert ok1 is True
    assert ok2 is False

def test_rate_limit_block():
    # Simulate that max per hour has been reached
    import time
    now = time.time()
    code_loop._run_timestamps.clear()
    for _ in range(code_loop.CODE_LOOP_MAX_PER_HOUR):
        code_loop._run_timestamps.append(now)
    blocked = code_loop.maybe_enqueue(9999)
    assert blocked is False

def test_dry_run_no_patch(tmp_path, monkeypatch):
    # Run in dry mode; ensure returns structure and does not crash
    out = code_loop.run_phase4(source_run_id=0, mode="dry_run")
    assert out.get("mode") == "dry_run"
    assert "golden_kpis_before_after" in out
    assert "decision" in out

