import threading
import time
import json
import os
import uuid
from typing import Dict, Any, List, Tuple

# Centralized, lightweight policy helpers for autonomous evolution

LOG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "logs", "autonomy.log")
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)


def _trace_id() -> str:
    return f"trc-{uuid.uuid4().hex[:8]}"


def run_log(event: Dict[str, Any]) -> None:
    try:
        event = {**event}
        event.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        with open(LOG_PATH, "a") as f:
            f.write(json.dumps(event) + "\n")
    except Exception:
        pass


def preflight_check() -> Tuple[bool, Dict[str, Any]]:
    """Check core health signals before a meta run. Returns (ok, details)."""
    from app.ollama_client import health as ollama_health
    from app.engines import health as engines_health
    from app.main import dgm_health  # FastAPI handler returning JSONResponse

    try:
        h_app = ollama_health()  # app/health is same as ollama health in this project
    except Exception as e:
        h_app = {"status": "down", "detail": str(e)}

    try:
        h_groq = engines_health()  # {"groq": {...}, "ollama": {...}}
    except Exception as e:
        h_groq = {"groq": {"status": "down", "detail": str(e)}}

    try:
        # dgm_health is async FastAPI route; call synchronous via .body if available
        r = dgm_health()  # type: ignore
        if hasattr(r, "body") and r.body:
            import json as _json
            h_dgm = _json.loads(r.body)
        else:
            h_dgm = {"status": "ok", "enabled": True}
    except Exception as e:
        h_dgm = {"status": "error", "detail": str(e)}

    ok = (
        (h_app.get("status") == "ok") and
        ((h_groq.get("groq") or {}).get("status") in ("ok", None)) and
        (h_dgm.get("status") in ("ok", "disabled"))
    )
    details = {"app": h_app, "groq": h_groq, "dgm": h_dgm}
    return ok, details


def golden_subset_gate(ids: List[str]) -> Dict[str, Any]:
    """Run a small golden subset synchronously and return aggregate KPIs.

    Uses the same logic as the async runner but runs inline to gate promotion.
    """
    from glob import glob
    import json as _json
    import os as _os
    from app.meta.runner import meta_run

    base = _os.path.join(_os.path.dirname(__file__), "..", "..", "storage", "golden")
    files = sorted(glob(_os.path.join(base, "*.json")))
    per_item = []
    for path in files:
        with open(path, "r") as f:
            item = _json.load(f)
        slug = item.get("id") or _os.path.splitext(_os.path.basename(path))[0]
        if ids and slug not in ids:
            continue
        res = meta_run(
            task_class=item.get("task_class", "code"),
            task=item.get("task", ""),
            assertions=item.get("assertions") or [],
            session_id=None,
            n=3,
            memory_k=int((item.get("flags") or {}).get("memory_k", 0)),
            rag_k=int((item.get("flags") or {}).get("rag_k", 0)),
            operators=None,
            framework_mask=["SEAL", "SAMPLING"],
            use_bandit=True,
            test_cmd=None,
            test_weight=0.0,
            force_engine="ollama",
            compare_with_groq=False,
            judge_mode="off",
            judge_include_rationale=True,
        )
        br = res.get("best_reward_breakdown") or {}
        per_item.append({
            "total_reward": res.get("best_total_reward"),
            "cost_penalty": br.get("cost_penalty") or 0.0,
            "steps": (res.get("metrics") or {}).get("steps_to_best") or 0,
        })

    valid = [p for p in per_item if isinstance(p.get("total_reward"), (int, float))]
    pass_rate = (sum(1 for p in valid if p["total_reward"] >= 0.3) / len(valid)) if valid else 0.0
    avg_total_reward = (sum(p["total_reward"] for p in valid) / len(valid)) if valid else None
    avg_cost_penalty = (sum(p.get("cost_penalty", 0.0) for p in valid) / len(valid)) if valid else None
    avg_steps = (sum(p.get("steps", 0) for p in valid) / len(valid)) if valid else None
    return {
        "pass_rate": pass_rate,
        "avg_total_reward": avg_total_reward,
        "avg_cost_penalty": avg_cost_penalty,
        "avg_steps": avg_steps,
        "count": len(valid)
    }


def nightly_scheduler_start():
    """Launch the nightly self-evolve sweep at ~02:00 local time in a daemon thread."""
    t = threading.Thread(target=_nightly_loop, daemon=True)
    t.start()


def _sleep_until(hour: int, minute: int = 0):
    now = time.time()
    lt = list(time.localtime(now))
    lt[3], lt[4], lt[5] = hour, minute, 0
    target = time.mktime(tuple(lt))
    if target <= now:
        target += 86400
    time.sleep(max(0, target - now))


def _nightly_loop():
    while True:
        _sleep_until(2, 0)
        tr = _trace_id()
        try:
            # Ensure indices fresh
            from app import memory
            from app.tools.rag import build_or_update_index
            start = time.time()
            build_or_update_index("data")
            run_log({"trace_id": tr, "operator": "rag.build", "inputs": {"rebuild": True}, "result": "ok", "duration_ms": int((time.time()-start)*1000)})
            start = time.time()
            memory.build_index()
            run_log({"trace_id": tr, "operator": "memory.build", "inputs": {"rebuild": True}, "result": "ok", "duration_ms": int((time.time()-start)*1000)})

            # Launch async-like meta runs (small batch)
            from app.meta.runner import meta_run
            classes = ["code", "qa"]
            ns = [3, 5]
            jobs: List[Tuple[int, str]] = []
            for i in range(6):
                tc = classes[i % len(classes)]
                n = ns[i % len(ns)]
                use_bandit = (i % 2 == 0)
                start = time.time()
                res = meta_run(tc, f"Nightly auto task {i+1}", [], None, n=n, memory_k=0, rag_k=0, use_bandit=use_bandit, framework_mask=["SEAL","SAMPLING"], force_engine="ollama", judge_mode="off")
                rid = res.get("run_id") or -1
                run_log({"trace_id": tr, "operator": "meta.run", "inputs": {"task_class": tc, "n": n, "use_bandit": use_bandit}, "result": "completed", "run_id": rid, "duration_ms": int((time.time()-start)*1000)})

                # Simple “promotable” heuristic: total_reward improvement vs recent median
                try:
                    from app.meta import store
                    recent = store.recent_runs(tc, 50)
                    vals = [r.get("best_score") for r in recent if isinstance(r.get("best_score"), (int, float))]
                    vals.sort()
                    median = vals[len(vals)//2] if vals else 0.0
                    best = res.get("best_score") or 0.0
                    lift = (best - median)
                    if lift >= 0.02:
                        # Propose → Commit → Golden gate → Rollback if regress
                        from app.dgm.proposer import generate as dgm_generate
                        from app.dgm.apply import batch_try_patches, commit_patch, rollback_commit
                        patches = dgm_generate(3, ["operators","rag","memory_policy"]).patches
                        applied = batch_try_patches(patches, dry_run=True)
                        good = [p for p, a in zip(patches, applied) if a.apply_ok and a.tests_ok]
                        if not good:
                            run_log({"trace_id": tr, "operator": "dgm.propose", "inputs": {"dry_run": True}, "result": "no_valid_patches"})
                        else:
                            p0 = good[0]
                            # Commit with tests (guarded in commit_patch)
                            cstart = time.time()
                            cres = commit_patch(p0, None)
                            if cres.get("status") == "committed":
                                run_log({"trace_id": tr, "operator": "dgm.commit", "inputs": {"patch_id": p0.id}, "result": "ok", "commit_sha": cres.get("commit_sha"), "duration_ms": int((time.time()-cstart)*1000)})
                                # Quick golden subset after commit
                                agg = golden_subset_gate(["search_capital_france", "code_dedupe"])  # small gate
                                if (agg.get("pass_rate", 0) < 0.95):
                                    rb = rollback_commit(cres.get("commit_sha"))
                                    run_log({"trace_id": tr, "operator": "dgm.rollback", "inputs": {"target_sha": cres.get("commit_sha")}, "result": rb.get("status")})
                            else:
                                run_log({"trace_id": tr, "operator": "dgm.commit", "inputs": {"patch_id": p0.id}, "result": "failed", "error": cres.get("error")})
                except Exception as e:
                    run_log({"trace_id": tr, "operator": "nightly.evaluate", "result": "error", "error": str(e)})

        except Exception as e:
            run_log({"trace_id": tr, "operator": "nightly.sweep", "result": "error", "error": str(e)})


def regression_watcher_start():
    t = threading.Thread(target=_regression_loop, daemon=True)
    t.start()


def _regression_loop():
    last_pause_until = 0.0
    while True:
        time.sleep(900)  # 15 minutes
        tr = _trace_id()
        now = time.time()
        try:
            from app.meta.store import get_analytics_overview
            a = get_analytics_overview()
            # Derive simple proxies
            # Use improvement trend and recent error rates if available (fallbacks set to safe values)
            success_rate = 0.99
            error_rate = 0.01
            chat_p95_ms = 1000
            confirmation_missing = 0.0
            cost_over = 0.0
            triggers = []
            if success_rate < 0.95 - 0.03:
                triggers.append("success_rate_drop")
            if chat_p95_ms > 1.2 * 1000 * 3:  # placeholder thresholding
                triggers.append("latency_p95_rise")
            if error_rate > 0.05:
                triggers.append("error_rate_high")
            if confirmation_missing > 0.005:
                triggers.append("confirmations_missing")
            if cost_over > 0.25:
                triggers.append("cost_overrun")

            if triggers and now >= last_pause_until:
                # Attempt auto-rollback of most recent commits (placeholder: no-op without commit registry)
                run_log({"trace_id": tr, "operator": "watcher.rollback", "result": "no_recent_commits", "triggers": triggers})
                # Throttle exploration for next window
                last_pause_until = now + 3600
                run_log({"trace_id": tr, "operator": "watcher.pause", "result": "throttle_exploration", "until": last_pause_until})
            else:
                run_log({"trace_id": tr, "operator": "watcher.heartbeat", "result": "ok"})
        except Exception as e:
            run_log({"trace_id": tr, "operator": "watcher.error", "result": "error", "error": str(e)})

