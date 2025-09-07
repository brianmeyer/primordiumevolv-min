from app.meta.bandit import UCB

def test_ucb_warm_start_and_bonus_shrink():
    ops = ["a","b","c"]
    agent = UCB(c=2.0, warm_start_min_pulls=1, stratified_explore=True)
    stats = {}
    # First passes cover each operator
    sel1 = agent.select(ops, stats)
    stats = agent.update(sel1, 0.1, stats)
    sel2 = agent.select(ops, stats)
    stats = agent.update(sel2, 0.2, stats)
    sel3 = agent.select(ops, stats)
    stats = agent.update(sel3, 0.3, stats)
    assert set([sel1, sel2, sel3]) == set(ops)
    # After plays, UCB bonus decreases as n grows
    scores1 = agent.get_ucb_scores(ops, stats)
    # Add observations to one operator and verify recomputed scores
    for _ in range(5):
        stats = agent.update(sel1, 0.1, stats)
    scores2 = agent.get_ucb_scores(ops, stats)
    assert scores2[sel1] <= scores1[sel1] + 1e-9

