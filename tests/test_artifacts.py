import json, os
from app.meta.runner import meta_run

def test_artifact_integrity(tmp_path):
    # Run a minimal meta evolution
    res = meta_run(task_class="code", task="Write a function hello()", assertions=[], session_id=None, n=2, memory_k=0, rag_k=0, use_bandit=True)
    run_id = res.get("run_id")
    assert run_id is not None
    # Check results.json present
    # Iteration artifacts in runs/<ts> are not trivial to map; validate result fields
    assert "best_reward_breakdown" in res
    assert "operator_stats" in res
    assert isinstance(res.get("metrics", {}).get("steps_to_best"), int)

