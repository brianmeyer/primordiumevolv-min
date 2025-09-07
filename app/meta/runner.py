import os
import time
import json
from typing import List, Optional, Dict, Any

from app.meta import store, bandit
from app.meta import operators as ops
from app.meta.rewards import compute_total_reward, get_default_baseline
from app.config import DEFAULT_OPERATORS, EVO_DEFAULTS, OP_GROUPS
from app.engines import call_engine
from app.groq_client import available as groq_available
from app.judge import judge_pair
from app.ollama_client import MODEL_ID as OLLAMA_MODEL_ID
from app.evolve.loop import score_output, stitch_context
# Legacy memory import removed - using new episodic memory system
from app.memory.store import get_memory_store, Experience
from app.memory.retriever import build_memory_primer
from app.memory.embed import get_embedding
from app.memory.metrics import get_memory_metrics_tracker
from app.tools.rag import query as rag_query  
from app.tools.web_search import search as web_search
from app.utils.logging import (
    log_meta_run_start, log_meta_run_finish, 
    log_operator_selection, log_generation_timing
)
from app import realtime
from app.config import FF_SYSTEMS_V2, FF_MEMORY, MEMORY_K, MEMORY_REWARD_FLOOR, MEMORY_INJECTION_MODE

# Expanded system voices (FF_SYSTEMS_V2)
VOICES_V2 = {
    "Engineer": "You are a concise senior engineer. Return minimal, directly usable code or config.",
    "Analyst": "You are a careful analyst. Trace reasoning in brief steps and confirm assumptions are valid.",
    "Optimizer": "You are a creative optimizer. Generate alternatives, compare tradeoffs, and justify the best option.",
    "Specialist": "You are a detail-oriented specialist. Ensure correctness, compliance, and complete coverage of edge cases.",
    "Architect": "You are an experienced architect. Design robust, extensible systems with long-term maintainability.",
    "Product Strategist": "You are a pragmatic product strategist. Frame solutions in terms of user value, business impact, and constraints.",
    "Experimenter": "You are a rapid prototyper. Propose small, low-risk tests to validate ideas quickly.",
    "Skeptic": "You are a rigorous skeptic. Stress-test assumptions and highlight potential failures."
}

def _weighted_system_for_task(task_class: str) -> str | None:
    if not FF_SYSTEMS_V2:
        return None
    t = (task_class or '').strip().lower()
    # Define weights per task type
    if t == 'code':
        choices = [
            ("Engineer", 3), ("Analyst", 2), ("Specialist", 2), ("Architect", 2),
            ("Optimizer", 1), ("Experimenter", 1), ("Skeptic", 1), ("Product Strategist", 1)
        ]
    elif t == 'analysis':
        choices = [("Analyst", 3), ("Skeptic", 2), ("Optimizer", 2), ("Engineer", 1), ("Architect", 1)]
    elif t == 'writing':
        choices = [("Experimenter", 3), ("Optimizer", 2), ("Specialist", 1), ("Analyst", 1), ("Skeptic", 1)]
    elif t == 'business':
        choices = [("Product Strategist", 3), ("Architect", 2), ("Optimizer", 2), ("Skeptic", 1), ("Analyst", 1)]
    elif t == 'research':
        choices = [("Analyst", 3), ("Specialist", 2), ("Skeptic", 2), ("Optimizer", 1)]
    else:  # general
        choices = [("Analyst", 2), ("Optimizer", 2), ("Engineer", 1), ("Experimenter", 1), ("Skeptic", 1), ("Product Strategist", 1)]
    import random
    population = [name for name, w in choices for _ in range(max(1, int(w)))]
    pick = random.choice(population)
    return VOICES_V2.get(pick)

def meta_run(
    task_class: str,
    task: str, 
    assertions: Optional[List[str]] = None,
    session_id: Optional[int] = None,
    n: int = EVO_DEFAULTS["n"],
    memory_k: int = EVO_DEFAULTS["memory_k"],
    rag_k: int = EVO_DEFAULTS["rag_k"],
    operators: Optional[List[str]] = None,
    eps: float = EVO_DEFAULTS["eps"],
    use_bandit: bool = True,
    bandit_algorithm: Optional[str] = None,  # "epsilon_greedy" or "ucb", defaults to config
    framework_mask: Optional[List[str]] = None,
    test_cmd: Optional[str] = None,
    test_weight: float = 0.0,
    force_engine: Optional[str] = None,
    compare_with_groq: Optional[bool] = False,
    judge_mode: Optional[str] = "off",
    judge_include_rationale: bool = True,
    pre_run_id: Optional[int] = None,
    # UCB-specific parameters  
    ucb_c: Optional[float] = None,
    warm_start_min_pulls: Optional[int] = None,
    stratified_explore: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Run meta-evolution cycle using epsilon-greedy bandit to select operators.
    
    Args:
        task_class: Classification for the task (e.g., "code", "analysis")
        task: The actual task prompt
        assertions: Optional list of assertions to check in output
        session_id: Session ID for memory context
        n: Number of evolution iterations
        memory_k: Number of memory results to retrieve
        rag_k: Number of RAG results to retrieve  
        operators: List of operators to use (defaults to DEFAULT_OPERATORS)
        eps: Epsilon for epsilon-greedy selection
        
    Returns:
        Dict with run results including best variant and operator stats
    """
    # Initialize database
    store.init_db()
    
    # Use default operators if none provided
    if operators is None:
        operators = DEFAULT_OPERATORS.copy()
    
    # Apply framework mask if provided
    if framework_mask:
        # Filter operators to only those in specified frameworks
        filtered_ops = []
        for op in operators:
            op_frameworks = [g for g, names in OP_GROUPS.items() if op in names] or ["UNSET"]
            if any(fw in framework_mask for fw in op_frameworks):
                filtered_ops.append(op)
        operators = filtered_ops if filtered_ops else operators
    
    # Load current operator stats
    operator_stats = store.list_operator_stats()
    
    # Initialize bandit with configuration defaults
    strategy = bandit_algorithm or EVO_DEFAULTS["strategy"]
    ucb_c = ucb_c or EVO_DEFAULTS["ucb_c"]
    warm_start_min_pulls = warm_start_min_pulls or EVO_DEFAULTS["warm_start_min_pulls"]
    stratified_explore = stratified_explore if stratified_explore is not None else EVO_DEFAULTS["stratified_explore"]
    
    if use_bandit:
        if strategy == "ucb":
            bandit_agent = bandit.UCB(
                c=ucb_c,
                warm_start_min_pulls=warm_start_min_pulls, 
                stratified_explore=stratified_explore
            )
        else:  # default to epsilon_greedy  
            bandit_agent = bandit.EpsilonGreedy(eps=eps)
    else:
        bandit_agent = None
    
    # Get baseline from top recipe for this task class
    top_recipes = store.top_recipes(task_class, limit=1)
    baseline = top_recipes[0]["avg_score"] if top_recipes else 0.0
    
    # Start run tracking (reuse pre-created run if provided)
    run_id = pre_run_id or store.save_run_start(task_class, task, assertions)
    
    # Create logs directory
    logs_dir = "logs"
    os.makedirs(logs_dir, exist_ok=True)
    
    # Log run start
    run_config = {
        "n": n, "memory_k": memory_k, "rag_k": rag_k,
        "operators": operators, "eps": eps,
        "use_bandit": use_bandit, "bandit_algorithm": bandit_algorithm,
        "framework_mask": framework_mask,
        "test_cmd": test_cmd, "test_weight": test_weight,
        "force_engine": force_engine, "compare_with_groq": compare_with_groq,
        "judge_mode": judge_mode,
    }
    log_meta_run_start(run_id, task_class, task, run_config, logs_dir)
    
    # Track best variant (now by total_reward)
    best_variant_id = None
    best_reward_breakdown = None
    best_step_index = None
    best_score = float('-inf')  # Preserved for UI compatibility
    best_total_reward = float('-inf')  # Primary optimization target
    best_recipe = None
    best_execution = None
    best_output = None
    
    # Track operator sequence for analytics
    operator_sequence = []
    
    # Create run artifacts directory
    timestamp = int(time.time())
    artifacts_dir = f"runs/{timestamp}"
    os.makedirs(artifacts_dir, exist_ok=True)
    
    # Get task baseline once before the loop (used for cost penalty calculation)
    task_baseline = get_default_baseline(task)
    
    # Memory system integration
    memory_used = False
    memory_hits = 0
    memory_primer_tokens = 0
    memory_primer = ""
    
    if FF_MEMORY:
        try:
            memory_store = get_memory_store()
            memory_metrics_tracker = get_memory_metrics_tracker()
            
            # Pre-run memory retrieval
            query_embedding = get_embedding(task)
            experiences = memory_store.search(
                query_embedding=query_embedding,
                task_class=task_class, 
                k=MEMORY_K,
                reward_floor=MEMORY_REWARD_FLOOR
            )
            
            memory_hits = len(experiences)
            memory_used = memory_hits > 0
            
            if experiences:
                memory_primer, memory_primer_tokens = build_memory_primer(experiences)
                
            # Stream memory update
            if hasattr(realtime, 'stream_event'):
                realtime.stream_event(run_id, "memory.update", {
                    "hits": memory_hits,
                    "primer_tokens": memory_primer_tokens,
                    "store_size": memory_store.count()
                })
                
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Memory system error during pre-run: {e}")
            memory_used = False
            memory_hits = 0
    
    # Evolution loop
    for i in range(n):
        try:
            # Select operator using bandit or random choice
            if use_bandit and bandit_agent:
                selected_op = bandit_agent.select(operators, operator_stats)
                selection_method = bandit_algorithm
            else:
                import random
                selected_op = random.choice(operators)
                selection_method = "random"
            
            # Log operator selection
            log_operator_selection(run_id, i, selected_op, selection_method, logs_dir)
            
            # Track operator sequence
            operator_sequence.append(selected_op)
            
            # Compute operator groups for analytics
            groups = [g for g, names in OP_GROUPS.items() if selected_op in names] or ["UNSET"]
            
            # Get base recipe (use best known recipe for task class)
            base_recipe = top_recipes[0] if top_recipes else None
            
            # Build execution plan
            plan = ops.build_plan(selected_op, base_recipe)

            # Optionally override system voice (V2) with task-aware weighting
            if FF_SYSTEMS_V2 and selected_op == "change_system":
                v2_sys = _weighted_system_for_task(task_class)
                if v2_sys:
                    plan["system"] = v2_sys

            # Ensure engine field and enforce local-only generation
            if not plan.get("engine"):
                plan["engine"] = "ollama"
            # Enforce local generation regardless of external overrides
            plan["engine"] = "ollama"
            
            # Gather contexts based on plan
            context = {"task": task}
            
            # Add memory primer if available
            if FF_MEMORY and memory_primer and MEMORY_INJECTION_MODE == "system_prepend":
                context["memory_primer"] = memory_primer
            
            if plan.get("use_memory") and session_id:
                try:
                    memory_results = query_memory(task, k=memory_k)
                    memory_snippets = [f"{r['role']}: {r['content'][:200]}" for r in memory_results[:memory_k]]
                    context["memory_context"] = stitch_context([], memory_snippets, [])
                except Exception:
                    context["memory_context"] = ""
            
            if plan.get("use_rag"):
                try:
                    rag_results = rag_query(task, k=rag_k)
                    rag_snippets = [r["chunk"][:200] for r in rag_results[:rag_k]]
                    context["rag_context"] = stitch_context(rag_snippets, [], [])
                except Exception:
                    context["rag_context"] = ""
                    
            if plan.get("use_web"):
                try:
                    web_results = web_search(task, top_k=EVO_DEFAULTS["web_k"])
                    web_snippets = [f"{r['title']}: {r['snippet'][:100]}" for r in web_results]
                    context["web_context"] = stitch_context([], [], web_snippets)
                except Exception:
                    context["web_context"] = ""
            
            # Groq is evaluation-only; generation always uses Ollama
            if plan.get("engine") != "ollama":
                plan["engine"] = "ollama"
                groups = list(set(groups + ["ENGINE_DISABLED"]))

            # Apply plan to build final prompt
            execution = ops.apply(plan, context)
            
            # Generate output via selected engine with timing (no local token cap)
            start_time = time.time()
            engine = plan.get("engine", "ollama")
            output, model_used = call_engine(
                engine,
                execution["prompt"],
                system=execution["system"],
                options=execution.get("options", {}),
            )
            generation_time_ms = int((time.time() - start_time) * 1000)
            
            # Log generation timing
            log_generation_timing(run_id, i, selected_op, generation_time_ms, logs_dir)
            
            # Score output (legacy) and compute total reward
            score = score_output(output, assertions, task, test_cmd, test_weight)
            
            # Compute comprehensive reward breakdown
            execution_context = {
                "tool_success_rate": 1.0,  # Assume success unless we have failures
                "tool_calls": 0,  # Could be enhanced to track actual tool usage
                "token_usage": {"input": len(task.split()) * 1.3, "output": len(output.split()) * 1.3}
            }
            
            reward_breakdown, total_reward = compute_total_reward(
                output=output,
                assertions=assertions,
                task=task,
                execution_time_ms=generation_time_ms,
                operator_name=selected_op,
                execution_context=execution_context,
                test_cmd=test_cmd,
                test_weight=test_weight,
                task_baseline=task_baseline
            )
            
            # Save variant with analytics
            model_id_value = model_used if plan.get("engine") == "groq" else OLLAMA_MODEL_ID

            variant_id = store.save_variant(
                run_id, 
                execution["system"],
                plan["nudge"],
                plan["params"],
                execution["prompt"],
                output,
                score,
                operator_name=selected_op,
                groups_json=json.dumps(groups),
                execution_time_ms=generation_time_ms,
                model_id=model_id_value,
                total_reward=total_reward,
                outcome_reward=reward_breakdown["outcome_reward"],
                process_reward=reward_breakdown["process_reward"],
                cost_penalty=reward_breakdown["cost_penalty"],
                reward_metadata=reward_breakdown.get("outcome_metadata")
            )

            # Stream iteration event with output and variant_id for human rating
            try:
                # Include full output for human rating (no truncation)
                output_preview = output
                # Extract judge information for UI display
                judge_info = {}
                if reward_breakdown.get("outcome_metadata"):
                    outcome_meta = reward_breakdown["outcome_metadata"]
                    if outcome_meta.get("groq_metadata") and outcome_meta["groq_metadata"].get("judge_results"):
                        judges = outcome_meta["groq_metadata"]["judge_results"]
                        judge_info = {
                            "judges": [{"model": j.get("model", "unknown"), "score": j.get("score", 0)} for j in judges if j.get("score") is not None],
                            "tie_breaker_used": outcome_meta["groq_metadata"].get("needed_tie_breaker", False),
                            "final_score": outcome_meta["groq_metadata"].get("final_score", score)
                        }
                
                realtime.publish(run_id, {
                    "type": "iter",
                    "run_id": run_id,
                    "i": i,
                    "operator": selected_op,
                    "engine": plan.get("engine", "ollama"),
                    "model_id": model_id_value,
                    "score": score,
                    "total_reward": total_reward,  # Primary metric
                    "reward_breakdown": {
                        "outcome": reward_breakdown["outcome_reward"],
                        "process": reward_breakdown["process_reward"], 
                        "cost": reward_breakdown["cost_penalty"]
                    },
                    "judge_info": judge_info,  # Judge details for UI
                    "duration_ms": generation_time_ms,
                    "timestamp": time.time(),
                    "variant_id": variant_id,  # Enable rating submission
                    "output": output_preview,   # Show actual AI response to user
                })
            except Exception:
                pass
            
            # Update best if this is better (use total_reward as primary criterion)
            if total_reward > best_total_reward:
                best_total_reward = total_reward
                best_score = score  # Keep for UI compatibility
                best_variant_id = variant_id
                best_reward_breakdown = reward_breakdown
                best_step_index = i
                best_recipe = {
                    "system": execution["system"],
                    "nudge": plan["nudge"],
                    "params": plan["params"],
                    "use_rag": plan.get("use_rag", False),
                    "use_memory": plan.get("use_memory", False),
                    "use_web": plan.get("use_web", False),
                    "fewshot": plan.get("fewshot"),
                    "engine": plan.get("engine", "ollama"),
                }
                best_execution = {
                    "prompt": execution["prompt"],
                    "system": execution["system"],
                    "params": plan.get("params", {}),
                }
                best_output = output
            
            # Update bandit with total_reward (new comprehensive reward system)
            if use_bandit and bandit_agent:
                operator_stats = bandit_agent.update(selected_op, total_reward, operator_stats)
            
            # Store stats using total_reward as primary metric
            store.upsert_operator_stat(selected_op, total_reward, generation_time_ms)
            
            # Track engine-specific operator performance
            engine_used = plan.get("engine", "ollama")
            store.upsert_operator_engine_stat(selected_op, engine_used, total_reward, generation_time_ms)
            
            # Get UCB scores for diagnostics (if UCB is being used)
            ucb_scores = {}
            if use_bandit and hasattr(bandit_agent, 'get_ucb_scores'):
                try:
                    ucb_scores = bandit_agent.get_ucb_scores(operators, operator_stats)
                except:
                    ucb_scores = {}
            
            # Prepare bandit state for artifacts
            bandit_state = {
                "chosen_op": {
                    "mean_payoff": operator_stats.get(selected_op, {}).get("mean_payoff", 0.0),
                    "plays": operator_stats.get(selected_op, {}).get("n", 0),
                    "ucb_score": ucb_scores.get(selected_op, 0.0)
                },
                "snapshot": [
                    {
                        "operator": op,
                        "mean_payoff": operator_stats.get(op, {}).get("mean_payoff", 0.0),
                        "plays": operator_stats.get(op, {}).get("n", 0),
                        "ucb_score": ucb_scores.get(op, 0.0)
                    }
                    for op in operators
                ]
            }
            
            # Save iteration artifact with enhanced data
            iteration_data = {
                "iteration": i,
                "operator": selected_op,
                "plan": plan,
                "score": score,  # Legacy score for UI compatibility
                "reward": total_reward,  # Now using total_reward as primary
                "reward_breakdown": reward_breakdown,
                "bandit_state": bandit_state,
                "output_preview": output
            }
            
            with open(f"{artifacts_dir}/iteration_{i:02d}.json", "w") as f:
                json.dump(iteration_data, f, indent=2)
            # Append trajectory entry (optional)
            try:
                from app.config import FF_TRAJECTORY_LOG
                if FF_TRAJECTORY_LOG:
                    from pathlib import Path
                    traj_path = Path(artifacts_dir) / "trajectory.json"
                    if traj_path.exists():
                        with open(traj_path, "r") as tf:
                            traj = json.load(tf).get("trajectory", [])
                    else:
                        traj = []
                    traj.append({
                        "i": i,
                        "op": selected_op,
                        "groups": groups,
                        "engine": plan.get("engine", "ollama"),
                        "time_ms": generation_time_ms,
                        "score": score,
                        "reward": total_reward,
                        "reward_breakdown": reward_breakdown,
                        "bandit_state": bandit_state,
                    })
                    with open(traj_path, "w") as tf:
                        json.dump({"run_id": run_id, "trajectory": traj}, tf, indent=2)
            except Exception:
                pass
                
        except Exception as e:
            print(f"Error in iteration {i}: {e}")
            continue
    
    # Updated promotion policy using total_reward criteria
    baseline_total_reward = 0.0  # Could be enhanced to track historical total_reward baseline
    
    # Finish run tracking and logging - ALWAYS mark run as finished
    total_reward_improvement = best_total_reward - baseline_total_reward if best_total_reward != float('-inf') else 0.0
    store.save_run_finish(run_id, best_variant_id or -1, best_score, operator_sequence, 
                         best_total_reward if best_total_reward != float('-inf') else None, 
                         total_reward_improvement)
    
    # Log run completion
    log_meta_run_finish(run_id, best_score, n, logs_dir)
    baseline_cost_penalty = task_baseline.get("cost_penalty", 0.1)  # Estimated baseline cost
    
    promotion_eligible = False
    promotion_reasons = []
    
    if best_variant_id and best_total_reward > baseline_total_reward + 0.05:
        # Check cost efficiency requirement
        current_cost_penalty = reward_breakdown.get("cost_penalty", 0.0) if 'reward_breakdown' in locals() else 0.0
        
        if current_cost_penalty <= 0.9 * baseline_cost_penalty:
            promotion_eligible = True
            promotion_reasons.append(f"total_reward improvement: {best_total_reward - baseline_total_reward:.3f}")
            promotion_reasons.append(f"cost efficiency: {current_cost_penalty:.3f} <= {0.9 * baseline_cost_penalty:.3f}")
            
            # Calculate engine confidence based on total_reward performance
            engine_confidence = min(1.0, 0.5 + (best_total_reward - baseline_total_reward) * 2)
            best_engine = best_recipe.get("engine", "ollama")
            
            recipe_id = store.save_recipe(task_class, 
                                        best_recipe["system"],
                                        best_recipe["nudge"], 
                                        best_recipe["params"],
                                        best_score,  # Still use score for legacy compatibility
                                        engine=best_engine,
                                        engine_confidence=engine_confidence)
            
            # Auto-approve if exceptionally better
            if best_total_reward > baseline_total_reward + 0.15:
                store.approve_recipe(recipe_id, 1)
                promotion_reasons.append("auto-approved for exceptional performance")
        else:
            promotion_reasons.append(f"cost too high: {current_cost_penalty:.3f} > {0.9 * baseline_cost_penalty:.3f}")
    else:
        promotion_reasons.append(f"insufficient total_reward improvement: {best_total_reward - baseline_total_reward:.3f} < 0.05")
    
    # Optional single-shot Groq cross-check
    compare = None
    try:
        if compare_with_groq and groq_available() and best_score != float('-inf'):
            be = locals().get("best_execution")
            if be:
                groq_out, groq_model = call_engine("groq", be["prompt"], system=be["system"], options=be.get("params", {}))
                groq_score = score_output(groq_out, assertions, task, test_cmd, test_weight)
                compare = {
                    "engine": "groq",
                    "model": groq_model,  # Use actual model from call_engine
                    "score": groq_score,
                    "delta_vs_best": groq_score - best_score,
                }
    except Exception:
        compare = None

    # Optional Judge Mode: compare local best against Groq challenger
    judge_report = None
    try:
        if judge_mode and str(judge_mode).lower() == "pairwise_groq" and groq_available() and best_execution and best_output is not None:
            challenger_output, challenger_model = call_engine("groq", best_execution["prompt"], system=best_execution["system"], options=best_execution.get("params", {}))
            jr = judge_pair(task, assertions or [], best_output, challenger_output)
            judge_report = {"mode": "pairwise_groq", "verdict": jr, "challenger_model": challenger_model}
    except Exception as _e:
        judge_report = {"mode": "pairwise_groq", "error": str(_e)}

    # Optional Judge Mode: compare local best against Groq challenger
    judge_report = None
    try:
        if judge_mode and str(judge_mode).lower() == "pairwise_groq" and groq_available() and best_execution and best_output is not None:
            challenger_output, challenger_model = call_engine("groq", best_execution["prompt"], system=best_execution["system"], options=best_execution.get("params", {}))
            jr = judge_pair(task, assertions or [], best_output, challenger_output)
            judge_report = {"mode": "pairwise_groq", "verdict": jr, "challenger_model": challenger_model}
            try:
                realtime.publish(run_id, {
                    "type": "judge",
                    "run_id": run_id,
                    "judge": judge_report,
                })
            except Exception:
                pass
    except Exception as _e:
        judge_report = {"mode": "pairwise_groq", "error": str(_e)}
        try:
            realtime.publish(run_id, {"type": "judge", "run_id": run_id, "judge": judge_report})
        except Exception:
            pass

    # Eval suite & promotion gating (safety probes)
    eval_report = None
    try:
        from app.config import FF_EVAL_GATE
        if FF_EVAL_GATE and best_output:
            from app.eval.suite import promotion_gate, write_eval_artifact
            gate = promotion_gate(best_output)
            eval_report = gate
            write_eval_artifact(artifacts_dir, gate)
    except Exception:
        eval_report = {"eligible": False, "error": "eval_failed"}

    # Calculate additional metrics
    avg_total_reward = None  # Optional; compute from artifacts if needed
    steps_to_best = (best_step_index + 1) if isinstance(best_step_index, int) else n
    
    # Create evaluation report with promotion metrics
    eval_metrics = {
        "best_total_reward": best_total_reward,
        "best_score": best_score,  # Legacy compatibility
        "avg_total_reward": avg_total_reward,
        "steps_to_best": steps_to_best,
        "cost_penalty_avg": reward_breakdown.get("cost_penalty", 0.0) if 'reward_breakdown' in locals() else 0.0,
        "promotion": {
            "eligible": promotion_eligible,
            "reasons": promotion_reasons
        }
    }
    
    # Save eval_report.json
    with open(f"{artifacts_dir}/eval_report.json", "w") as f:
        json.dump({"metrics": eval_metrics}, f, indent=2)
    
    # Save final artifacts (enhanced)
    final_results = {
        "run_id": run_id,
        "task_class": task_class,
        "task": task,
        "assertions": assertions,
        "best_score": best_score,  # Legacy for UI compatibility
        "best_total_reward": best_total_reward,  # Primary metric
        "best_recipe": best_recipe,
        "operator_stats": operator_stats,
        "baseline": baseline,
        "improvement": best_score - baseline if best_score != float('-inf') else 0,  # Legacy
        "total_reward_improvement": best_total_reward - baseline_total_reward,  # New primary
        "timestamp": timestamp,
        "metrics": eval_metrics,
        **({"best_reward_breakdown": best_reward_breakdown} if best_reward_breakdown else {}),
        **({"compare": compare} if compare else {}),
        **({"judge": judge_report} if judge_report else {}),
        **({"eval": eval_report} if eval_report else {}),
    }
    
    with open(f"{artifacts_dir}/results.json", "w") as f:
        json.dump(final_results, f, indent=2)
    
    # Optional bandit diagnostics (debug flag)
    debug_bandit = os.getenv("DEBUG_BANDIT", "false").lower() == "true"
    if debug_bandit and use_bandit and operator_stats:
        print(f"\n=== Bandit Summary (Run {run_id}) ===")
        print(f"Strategy: {strategy}")
        
        # Get final UCB scores
        final_ucb_scores = {}
        if hasattr(bandit_agent, 'get_ucb_scores'):
            try:
                final_ucb_scores = bandit_agent.get_ucb_scores(operators, operator_stats)
            except:
                pass
        
        for op in operators:
            stats = operator_stats.get(op, {})
            mean_payoff = stats.get("mean_payoff", 0.0)
            plays = stats.get("n", 0)
            ucb_score = final_ucb_scores.get(op, 0.0)
            
            print(f"  {op:15s}: payoff={mean_payoff:6.3f}, plays={plays:2d}, ucb={ucb_score:6.3f}")
        print("=" * 40)
    
    # Stream completion
    try:
        realtime.publish(run_id, {"type": "done", "run_id": run_id, "result": final_results})
    except Exception:
        pass

    # Memory system post-run integration
    if FF_MEMORY and best_output and best_total_reward != float('-inf'):
        try:
            # Store successful run as experience
            experience = Experience.create(
                task_class=task_class,
                input_text=task,
                plan_json=best_recipe or {},
                operator_used=operator_sequence[-1] if operator_sequence else "unknown",
                output_text=best_output,
                reward=best_total_reward,
                confidence_score=best_reward_breakdown.get("confidence", 0.8) if best_reward_breakdown else 0.8,
                judge_ai=best_reward_breakdown.get("outcome_reward", 0.0) if best_reward_breakdown else 0.0,
                judge_semantic=0.0,  # Could be enhanced with semantic scoring
                tokens_in=len(task.split()) * 1.3,  # Rough estimation
                tokens_out=len(best_output.split()) * 1.3,
                latency_ms=sum(getattr(op, 'latency_ms', 0) for op in operator_sequence) if operator_sequence else 0
            )
            
            memory_store.add(experience)
            
            # Determine lift source attribution
            reward_delta = best_total_reward - baseline_total_reward
            lift_source = "memory" if memory_used and reward_delta > 0.05 else "none"
            
            # Stream memory result
            if hasattr(realtime, 'stream_event'):
                realtime.stream_event(run_id, "memory.result", {
                    "reward": best_total_reward,
                    "reward_delta": reward_delta,
                    "lift_source": lift_source
                })
            
            # Record memory metrics
            memory_metrics_tracker.record_run_metrics(
                run_id=run_id,
                task_class=task_class,
                memory_hits=memory_hits,
                memory_primer_tokens=memory_primer_tokens,
                memory_store_size=memory_store.count(),
                used_memory=memory_used,
                lift_source=lift_source,
                reward_delta=reward_delta
            )
            
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Memory system error during post-run: {e}")

    # Optional post-run Phase 4 loop (auto) with overlap safeguards
    try:
        from app.config import FF_CODE_LOOP
        if FF_CODE_LOOP:
            from app import code_loop as _code_loop
            _code_loop.maybe_enqueue(run_id)
    except Exception:
        pass

    return final_results
