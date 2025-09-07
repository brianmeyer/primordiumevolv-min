import os
import json
import time
import threading
import subprocess
import hashlib
from collections import deque
from glob import glob
from typing import Dict

from app.meta.runner import meta_run
from app.config import (
    CODE_LOOP_MODE, CODE_LOOP_TIMEOUT_SECONDS, CODE_LOOP_MAX_PER_HOUR,
    PHASE4_DELTA_REWARD_MIN, PHASE4_COST_RATIO_MAX, GOLDEN_PASS_RATE_TARGET
)

_lock = threading.Lock()
_running = False
_queue: deque[dict] = deque()
_processed_ids: set[int] = set()
_run_timestamps: deque[float] = deque()  # for rate limiting


def _select_golden_subset() -> list[dict]:
    base = os.path.join(os.path.dirname(__file__), "..", "storage", "golden")
    files = sorted(glob(os.path.join(base, "*.json")))
    subset = []
    seen_types = set()
    for path in files:
        try:
            with open(path, "r") as f:
                item = json.load(f)
        except Exception:
            continue
        ttype = item.get("task_type") or item.get("task_class")
        if ttype not in seen_types or len(subset) < 3:
            subset.append(item)
            seen_types.add(ttype)
        if len(subset) >= 5 and len(seen_types) >= 3:
            break
    return subset


def _run_subset_avg(subset: list[dict]) -> dict:
    import random
    rewards = []
    costs = []
    total = 0
    passes = 0
    for it in subset:
        try:
            random.seed(int(it.get("seed", 123)))
            res = meta_run(
                task_class=it.get("task_class", "code"),
                task=it.get("task", ""),
                assertions=it.get("assertions") or [],
                session_id=None,
                n=6,
                memory_k=0,
                rag_k=int((it.get("flags") or {}).get("rag_k", 0)),
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
            r = res.get("best_total_reward") or 0.0
            c = br.get("cost_penalty") or 0.0
            rewards.append(r)
            costs.append(c)
            total += 1
            if r >= GOLDEN_PASS_RATE_TARGET:  # reward threshold proxy for pass
                passes += 1
        except Exception:
            continue
    return {
        "avg_reward": (sum(rewards) / len(rewards)) if rewards else 0.0,
        "avg_cost": (sum(costs) / len(costs)) if costs else 0.0,
        "pass_rate": (passes / total) if total else 0.0
    }


def _hash_file(path: str) -> str | None:
    try:
        h = hashlib.sha256()
        with open(path, 'rb') as f:
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def _run_pytests(timeout_sec: int = 120) -> Dict:
    try:
        proc = subprocess.run(["pytest", "-q"], capture_output=True, text=True, timeout=timeout_sec)
        passed = proc.returncode == 0
        out = (proc.stdout or '') + (proc.stderr or '')
        # crude parse
        failed = 0 if passed else 1
        return {"passed": passed, "output": out[-2000:], "failed": failed}
    except Exception as e:
        return {"passed": False, "output": str(e), "failed": 1}


def run_phase4(source_run_id: int | None = None, mode: str | None = None) -> Dict:
    ts = int(time.time())
    artifacts_dir = os.path.join("runs", str(ts))
    os.makedirs(artifacts_dir, exist_ok=True)

    # Load baseline tuning
    tuning_path = os.path.join("storage", "tuning.json")
    try:
        with open(tuning_path, "r") as tf:
            before_tuning = tf.read()
        current = json.loads(before_tuning)
    except Exception:
        current = {"process_multiplier": 1.0, "cost_multiplier": 1.0}
        before_tuning = json.dumps(current)

    subset = _select_golden_subset()
    before = _run_subset_avg(subset)

    # Critic: adjust process or cost multiplier
    pm = float(current.get("process_multiplier", 1.0))
    cm = float(current.get("cost_multiplier", 1.0))
    patch = {}
    if before["avg_reward"] < 0.35:
        patch["process_multiplier"] = min(1.5, pm + 0.05)
    else:
        patch["cost_multiplier"] = max(0.5, cm - 0.05)

    # Apply patch (live only)
    new_tuning = {"process_multiplier": patch.get("process_multiplier", pm), "cost_multiplier": patch.get("cost_multiplier", cm)}
    unified_diff_snippet = ""
    git_commit = None
    applied = False
    mode = (mode or CODE_LOOP_MODE)
    if mode == "live":
        with open(tuning_path, "w") as tf:
            tf.write(json.dumps(new_tuning, indent=2))
        applied = True
        # Best-effort git hash capture
        try:
            gc = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5)
            if gc.returncode == 0:
                git_commit = (gc.stdout or '').strip()
        except Exception:
            git_commit = None
        # Unified diff snippet (simple JSON line comparison)
        unified_diff_snippet = f"- {before_tuning.strip()}\n+ {json.dumps(new_tuning, indent=2).strip()}"

    # Test after
    after = _run_subset_avg(subset)
    delta = after["avg_reward"] - before["avg_reward"]
    # Run unit tests
    test_results = _run_pytests(timeout_sec=180)
    # Acceptance gates (cost gate and schema integrity approximated via presence of artifacts)
    # Cost ratio and pass rate gates
    cost_ratio_ok = (after["avg_cost"] <= PHASE4_COST_RATIO_MAX * max(1e-6, before["avg_cost"])) if before["avg_cost"] > 0 else True
    pass_rate_ok = (after["pass_rate"] >= GOLDEN_PASS_RATE_TARGET)
    decision = (test_results.get("passed") and (delta >= PHASE4_DELTA_REWARD_MIN) and cost_ratio_ok and pass_rate_ok)
    if mode == "live" and applied and not decision:
        # revert tuning
        with open(tuning_path, "w") as tf:
            tf.write(before_tuning)

    loop_id = f"{ts}-{source_run_id or 'manual'}"
    # Context
    model_id = "ollama:"  # enforced local
    rag_hash = _hash_file(os.path.join("storage", ".chat.faiss"))
    code_loop = {
        "loop_id": loop_id,
        "source_run_id": source_run_id,
        "mode": mode,
        "critic_note": "Adjust process/cost multipliers to improve total_reward while controlling cost.",
        "patch_summary": {"before": json.loads(before_tuning), "after": new_tuning, "loc_changed": 2, "unified_diff_snippet": unified_diff_snippet, "git_commit": git_commit},
        "tests": {"unit": {"passed": test_results.get("passed"), "failed": test_results.get("failed", 0)}},
        "golden_kpis_before_after": {
            "before": before,
            "after": after,
            "delta_total_reward": delta
        },
        "thresholds": {
            "delta_reward_min": PHASE4_DELTA_REWARD_MIN,
            "cost_ratio_max": PHASE4_COST_RATIO_MAX,
            "golden_pass_rate_target": GOLDEN_PASS_RATE_TARGET
        },
        "context": {"model_id": model_id, "rag_index_hash": rag_hash, "seeds": {"subset": [it.get("seed") for it in subset]}},
        "decision": {
            "accepted": bool(decision),
            "reasons": ([] if decision else [r for r in [
                (None if test_results.get('passed') else 'tests_failed'),
                (None if delta >= PHASE4_DELTA_REWARD_MIN else 'delta_too_small'),
                (None if cost_ratio_ok else 'cost_too_high'),
                (None if pass_rate_ok else 'pass_rate_low')
            ] if r])
        }
    }

    with open(os.path.join(artifacts_dir, "code_loop.json"), "w") as f:
        json.dump(code_loop, f, indent=2)
    return code_loop


def _within_rate_limit(now_ts: float) -> bool:
    # Allow at most CODE_LOOP_MAX_PER_HOUR completed starts per rolling hour
    cutoff = now_ts - 3600
    while _run_timestamps and _run_timestamps[0] < cutoff:
        _run_timestamps.popleft()
    return len(_run_timestamps) < CODE_LOOP_MAX_PER_HOUR


def maybe_enqueue(source_run_id: int, mode: str | None = None) -> bool:
    now = time.time()
    with _lock:
        if source_run_id in _processed_ids:
            return False
        if not _within_rate_limit(now):
            return False
        _queue.append({"source_run_id": source_run_id, "mode": mode or CODE_LOOP_MODE, "enqueued_at": now})
        _processed_ids.add(source_run_id)
        # Start worker if not running
        if not _running:
            _start_worker()
        return True


def _start_worker():
    global _running
    _running = True

    def _worker():
        global _running
        try:
            while True:
                with _lock:
                    if not _queue:
                        _running = False
                        break
                    job = _queue.popleft()
                start = time.time()
                try:
                    # Hard timeout per loop
                    t = threading.Thread(target=run_phase4, args=(job.get("source_run_id"), job.get("mode")))
                    t.daemon = True
                    t.start()
                    t.join(timeout=CODE_LOOP_TIMEOUT_SECONDS)
                except Exception:
                    pass
                finally:
                    with _lock:
                        _run_timestamps.append(time.time())
        finally:
            _running = False

    threading.Thread(target=_worker, daemon=True).start()
