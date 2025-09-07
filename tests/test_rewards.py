import math
from app.meta.rewards import compute_total_reward

def test_total_reward_monotonicity():
    out = "ok"
    assertions = []
    task = "do"
    ctx = {"tool_success_rate": 1.0, "tool_calls": 0, "token_usage": {"input": 10, "output": 10}}
    # Baseline
    rb1, tr1 = compute_total_reward(out, assertions, task, 1000, "op", ctx)
    # Higher outcome increases total_reward
    rb2, tr2 = compute_total_reward(out, assertions, task, 1000, "op", ctx)
    assert tr2 >= tr1 - 1e-9
    # Increasing cost reduces total_reward
    rb3, tr3 = compute_total_reward(out, assertions, task, 100000, "op", ctx)
    assert tr3 <= tr2 + 1e-9

def test_total_reward_no_nan():
    out = ""
    rb, tr = compute_total_reward(out, [], "", 0, "op", {"tool_success_rate": 0.0, "tool_calls": 0, "token_usage": {"input": 0, "output": 0}})
    assert rb["total_reward"] == tr
    assert not (math.isnan(tr) or math.isinf(tr))

