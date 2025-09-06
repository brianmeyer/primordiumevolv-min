import os
import time
import json
from typing import List, Optional, Dict, Any

from app.meta import store, bandit
from app.meta import operators as ops
from app.config import DEFAULT_OPERATORS, EVO_DEFAULTS, OP_GROUPS
from app.engines import call_engine
from app.groq_client import available as groq_available
from app.judge import judge_pair
from app.ollama_client import MODEL_ID as OLLAMA_MODEL_ID
from app.evolve.loop import score_output, stitch_context
from app.memory import query_memory
from app.tools.rag import query as rag_query  
from app.tools.web_search import search as web_search
from app.utils.logging import (
    log_meta_run_start, log_meta_run_finish, 
    log_operator_selection, log_generation_timing
)
from app import realtime

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
    bandit_algorithm: str = "epsilon_greedy",  # "epsilon_greedy" or "ucb"
    framework_mask: Optional[List[str]] = None,
    test_cmd: Optional[str] = None,
    test_weight: float = 0.0,
    force_engine: Optional[str] = None,
    compare_with_groq: Optional[bool] = False,
    judge_mode: Optional[str] = "off",
    judge_include_rationale: bool = True,
    pre_run_id: Optional[int] = None,
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
    
    # Initialize bandit
    if use_bandit:
        if bandit_algorithm == "ucb":
            bandit_agent = bandit.UCB()
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
    
    # Track best variant
    best_variant_id = None
    best_score = float('-inf')
    best_recipe = None
    best_execution = None
    best_output = None
    
    # Track operator sequence for analytics
    operator_sequence = []
    
    # Create run artifacts directory
    timestamp = int(time.time())
    artifacts_dir = f"runs/{timestamp}"
    os.makedirs(artifacts_dir, exist_ok=True)
    
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

            # Ensure engine field and allow override
            if not plan.get("engine"):
                plan["engine"] = "ollama"
            if force_engine in ("ollama", "groq"):
                plan["engine"] = force_engine
            
            # Gather contexts based on plan
            context = {"task": task}
            
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
            
            # If engine switch requested but unavailable, fallback and tag
            if plan.get("engine") == "groq" and not groq_available():
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
            
            # Score output
            score = score_output(output, assertions, task, test_cmd, test_weight)
            
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
                model_id=model_id_value
            )

            # Stream iteration event
            try:
                realtime.publish(run_id, {
                    "type": "iter",
                    "run_id": run_id,
                    "i": i,
                    "operator": selected_op,
                    "engine": plan.get("engine", "ollama"),
                    "model_id": model_id_value,
                    "score": score,
                    "duration_ms": generation_time_ms,
                    "timestamp": time.time(),
                })
            except Exception:
                pass
            
            # Update best if this is better
            if score > best_score:
                best_score = score
                best_variant_id = variant_id
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
            
            # Calculate reward and update operator stats
            reward_base = score - baseline
            # Optional process+cost reward blending
            try:
                from app.config import FF_PROCESS_COST_REWARD, REWARD_ALPHA, REWARD_BETA_PROCESS, REWARD_GAMMA_COST
            except Exception:
                FF_PROCESS_COST_REWARD = False
            if FF_PROCESS_COST_REWARD:
                process_reward = 0.0 if best_score in (None, float('-inf')) else (score - (best_score if best_score != float('-inf') else score))
                cost_reward = -float(generation_time_ms)
                reward = (
                    REWARD_ALPHA * reward_base +
                    REWARD_BETA_PROCESS * process_reward +
                    REWARD_GAMMA_COST * cost_reward
                )
            else:
                reward = reward_base
            if use_bandit and bandit_agent:
                operator_stats = bandit_agent.update(selected_op, reward, operator_stats)
            store.upsert_operator_stat(selected_op, reward, generation_time_ms)
            
            # Track engine-specific operator performance
            engine_used = plan.get("engine", "ollama")
            store.upsert_operator_engine_stat(selected_op, engine_used, reward, generation_time_ms)
            
            # Save iteration artifact
            iteration_data = {
                "iteration": i,
                "operator": selected_op,
                "plan": plan,
                "score": score,
                "reward": reward,
                "output_preview": output[:200] + "..." if len(output) > 200 else output
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
                        "reward": reward,
                    })
                    with open(traj_path, "w") as tf:
                        json.dump({"run_id": run_id, "trajectory": traj}, tf, indent=2)
            except Exception:
                pass
                
        except Exception as e:
            print(f"Error in iteration {i}: {e}")
            continue
    
    # Finish run tracking and logging - ALWAYS mark run as finished
    store.save_run_finish(run_id, best_variant_id or -1, best_score, operator_sequence)
    
    # Log run completion
    log_meta_run_finish(run_id, best_score, n, logs_dir)
    
    # Save best as new recipe if it's significantly better (only if we had success)
    if best_variant_id and best_score > baseline + 0.1:
        # Calculate engine confidence based on performance
        engine_confidence = min(1.0, 0.5 + (best_score - baseline) * 2)
        best_engine = best_recipe.get("engine", "ollama")
        
        recipe_id = store.save_recipe(task_class, 
                                    best_recipe["system"],
                                    best_recipe["nudge"], 
                                    best_recipe["params"],
                                    best_score,
                                    engine=best_engine,
                                    engine_confidence=engine_confidence)
        # Auto-approve if significantly better
        if best_score > baseline + 0.2:
            store.approve_recipe(recipe_id, 1)
    
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

    # Save final artifacts
    final_results = {
        "run_id": run_id,
        "task_class": task_class,
        "task": task,
        "assertions": assertions,
        "best_score": best_score,
        "best_recipe": best_recipe,
        "operator_stats": operator_stats,
        "baseline": baseline,
        "improvement": best_score - baseline if best_score != float('-inf') else 0,
        "timestamp": timestamp,
        **({"compare": compare} if compare else {}),
        **({"judge": judge_report} if judge_report else {}),
        **({"eval": eval_report} if eval_report else {}),
    }
    
    with open(f"{artifacts_dir}/results.json", "w") as f:
        json.dump(final_results, f, indent=2)
    
    # Stream completion
    try:
        realtime.publish(run_id, {"type": "done", "run_id": run_id, "result": final_results})
    except Exception:
        pass

    return final_results
