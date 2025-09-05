import os
import time
import json
from typing import List, Optional, Dict, Any

from app.meta import store, bandit
from app.meta import operators as ops
from app.config import DEFAULT_OPERATORS, EVO_DEFAULTS
from app.ollama_client import generate
from app.evolve.loop import score_output, stitch_context
from app.memory import query_memory
from app.tools.rag import query as rag_query  
from app.tools.web_search import search as web_search

def meta_run(
    task_class: str,
    task: str, 
    assertions: Optional[List[str]] = None,
    session_id: Optional[int] = None,
    n: int = EVO_DEFAULTS["n"],
    memory_k: int = EVO_DEFAULTS["memory_k"],
    rag_k: int = EVO_DEFAULTS["rag_k"],
    operators: Optional[List[str]] = None,
    eps: float = EVO_DEFAULTS["eps"]
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
    
    # Load current operator stats
    operator_stats = store.list_operator_stats()
    
    # Initialize bandit
    bandit_agent = bandit.EpsilonGreedy(eps=eps)
    
    # Get baseline from top recipe for this task class
    top_recipes = store.top_recipes(task_class, limit=1)
    baseline = top_recipes[0]["avg_score"] if top_recipes else 0.0
    
    # Start run tracking
    run_id = store.save_run_start(task_class, task, assertions)
    
    # Track best variant
    best_variant_id = None
    best_score = float('-inf')
    best_recipe = None
    
    # Create run artifacts directory
    timestamp = int(time.time())
    artifacts_dir = f"runs/{timestamp}"
    os.makedirs(artifacts_dir, exist_ok=True)
    
    # Evolution loop
    for i in range(n):
        try:
            # Select operator using bandit
            selected_op = bandit_agent.select(operators, operator_stats)
            
            # Get base recipe (use best known recipe for task class)
            base_recipe = top_recipes[0] if top_recipes else None
            
            # Build execution plan
            plan = ops.build_plan(selected_op, base_recipe)
            
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
            
            # Apply plan to build final prompt
            execution = ops.apply(plan, context)
            
            # Generate output
            output = generate(
                execution["prompt"], 
                system=execution["system"],
                options=execution.get("options", {})
            )
            
            # Score output
            score = score_output(output, assertions, task)
            
            # Save variant
            variant_id = store.save_variant(
                run_id, 
                execution["system"],
                plan["nudge"],
                plan["params"],
                execution["prompt"],
                output,
                score
            )
            
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
                    "fewshot": plan.get("fewshot")
                }
            
            # Calculate reward and update operator stats
            reward = score - baseline
            operator_stats = bandit_agent.update(selected_op, reward, operator_stats)
            store.upsert_operator_stat(selected_op, reward)
            
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
                
        except Exception as e:
            print(f"Error in iteration {i}: {e}")
            continue
    
    # Finish run tracking
    if best_variant_id:
        store.save_run_finish(run_id, best_variant_id, best_score)
        
        # Save best as new recipe if it's significantly better
        if best_score > baseline + 0.1:  # Threshold for improvement
            recipe_id = store.save_recipe(task_class, 
                                        best_recipe["system"],
                                        best_recipe["nudge"], 
                                        best_recipe["params"],
                                        best_score)
            # Auto-approve if significantly better
            if best_score > baseline + 0.2:
                store.approve_recipe(recipe_id, 1)
    
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
        "timestamp": timestamp
    }
    
    with open(f"{artifacts_dir}/results.json", "w") as f:
        json.dump(final_results, f, indent=2)
    
    return final_results