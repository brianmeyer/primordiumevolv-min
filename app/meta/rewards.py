"""
Meta-Evolution Reward System
===========================

This module implements the comprehensive reward system for the meta-evolution pipeline.
It evaluates AI responses across three key dimensions to guide the evolution of better
prompt engineering strategies.

Reward Components:
1. **Outcome Reward**: Quality and correctness of the final response
   - Uses hybrid AI judgment (90%) + semantic similarity (10%)
   - Two-judge system with tie-breaker for disagreement resolution
   - Evaluates accuracy, completeness, clarity, relevance, usefulness

2. **Process Reward**: Quality of the reasoning and methodology  
   - Structured reasoning patterns
   - Code quality (if applicable)
   - Tool usage effectiveness
   - Operator-specific bonuses

3. **Cost Penalty**: Resource efficiency considerations
   - Execution time vs baseline
   - Token usage vs baseline  
   - Tool call overhead

Total Reward Formula:
    total_reward = outcome_reward + process_reward - cost_penalty

Integration:
- Called by meta-evolution runner to score response variants
- Feeds into UCB bandit algorithm for operator selection
- Used for human-in-the-loop rating correlation analysis

Key Features:
- Fallback mechanisms for robustness
- Detailed metadata for analysis and debugging
- Configurable baselines and weights
- Test command integration for external validation
"""
import re
import time
from typing import List, Optional, Dict, Any, Tuple
from app.evolve.loop import score_output  # Import existing scoring
import json as _json
import os as _os
from app.quality_judge import evaluate_response_quality  # New hybrid scoring


def compute_outcome_reward(
    output: str, 
    assertions: Optional[List[str]] = None, 
    task: str = "",
    test_cmd: Optional[str] = None,
    test_weight: float = 0.0,
    use_groq_judge: bool = True,
    variant_id: Optional[str] = None
) -> Tuple[float, Dict[str, Any]]:
    """
    Compute outcome reward - the primary quality assessment of the AI response.
    
    This function evaluates how well the AI response meets the task requirements
    and quality standards. It's the most important component of the total reward.
    
    Scoring Methods:
    1. **Hybrid AI+Semantic (default)**: Uses sophisticated two-judge system
       - 90% weight on multi-model AI judgment
       - 10% weight on semantic similarity
       - Automatic tie-breaker for disagreement resolution
    
    2. **External Test Command (optional)**: Validates output against automated tests
       - Runs provided shell command with output saved to artifacts/out.txt
       - Blends test result with primary score based on test_weight
       
    3. **Human Rating Modifier (when available)**: Direct human feedback integration
       - Scale: 1-10 (1=terrible, 5=neutral, 10=excellent)  
       - 1→0.2x modifier (80% penalty), 5→1.0x (no change), 10→1.8x (80% boost)
       - Applied only when variant_id is provided and human rating exists
       - Modifies the final outcome score before returning
       
    4. **Fallback Semantic**: If AI judges fail, uses pure semantic similarity
    
    Args:
        output (str): The AI-generated response to evaluate
        assertions (Optional[List[str]]): Specific requirements/constraints to check
        task (str): Original task description for context
        test_cmd (Optional[str]): Shell command to run for external validation
        test_weight (float): Weight for test command result (0.0-1.0)
        use_groq_judge (bool): Whether to use AI judges (default True)
        
    Returns:
        Tuple[float, Dict[str, Any]]:
            - score: 0.0-1.0 outcome quality score
            - metadata: Detailed evaluation breakdown including:
                * method: Scoring method used ("hybrid", "semantic_only", etc.)
                * test_applied: Whether external test was run
                * test_score: External test result (if applicable)
                * groq_metadata: Full AI judgment details (if used)
                
    Example:
        score, meta = compute_outcome_reward(
            output="def factorial(n): return 1 if n <= 1 else n * factorial(n-1)",
            assertions=["Must handle edge cases", "Should be recursive"],
            task="Write a recursive factorial function",
            test_cmd="python -c 'exec(open(\"artifacts/out.txt\").read()); print(factorial(5))'",
            test_weight=0.3
        )
        # Returns high score if both AI judges and test pass
    """
    if use_groq_judge:
        try:
            # Use hybrid Groq + semantic scoring
            score, metadata = evaluate_response_quality(task, assertions or [], output)
            
            # Apply test_cmd if provided (same as original logic)
            if test_cmd and test_weight > 0.0:
                try:
                    import os, subprocess
                    os.makedirs("artifacts", exist_ok=True)
                    with open("artifacts/out.txt", "w") as f:
                        f.write(output)
                    
                    result = subprocess.run(test_cmd, shell=True, capture_output=True, timeout=30)
                    test_score = 1.0 if result.returncode == 0 else 0.0
                    score = (1 - test_weight) * score + test_weight * test_score
                    metadata["test_applied"] = True
                    metadata["test_score"] = test_score
                except Exception as e:
                    metadata["test_error"] = str(e)
            
            # Apply human rating modifier if variant_id provided
            if variant_id:
                try:
                    from app.meta.store import _conn
                    conn = _conn()
                    cursor = conn.execute("SELECT human_score FROM human_ratings WHERE variant_id = ? ORDER BY created_at DESC LIMIT 1", (variant_id,))
                    result = cursor.fetchone()
                    conn.close()
                    
                    if result:
                        human_score = float(result[0])
                        # Convert 1-10 scale to modifier: 1-4=penalty, 5=neutral(1.0), 6-10=boost
                        if human_score < 5:
                            # 1→0.2, 4→0.8, linear
                            human_modifier = 0.2 + (human_score - 1) * 0.2
                        elif human_score == 5:
                            # Neutral
                            human_modifier = 1.0
                        else:
                            # 6→1.2, 10→2.0, linear
                            human_modifier = 1.0 + (human_score - 5) * 0.2
                        original_score = score
                        score = min(1.0, max(0.0, score * human_modifier))  # Clamp to [0, 1]
                        
                        metadata["human_rating"] = {
                            "score": human_score,
                            "modifier": human_modifier,
                            "original_score": original_score,
                            "adjusted_score": score
                        }
                except Exception as e:
                    metadata["human_rating_error"] = str(e)
                    
            return score, metadata
            
        except Exception as e:
            # Fallback to original scoring if Groq fails
            fallback_score = score_output(output, assertions, task, test_cmd, test_weight)
            return fallback_score, {"method": "fallback_semantic", "groq_error": str(e)}
    else:
        # Original semantic-only scoring
        score = score_output(output, assertions, task, test_cmd, test_weight)
        return score, {"method": "semantic_only"}


def compute_process_reward(
    output: str,
    execution_context: Dict[str, Any],
    operator_name: str
) -> float:
    """
    Compute process reward based on the quality of reasoning and methodology.
    
    This function evaluates HOW the AI approached the task, not just the final result.
    It rewards structured thinking, good practices, and effective use of tools.
    Process reward is capped at 0.5 to keep it secondary to outcome quality.
    
    Evaluation Criteria:
    
    **General Quality Signals (all tasks):**
    - Structured reasoning: Use of logical flow, steps, cause-effect relationships
    - Tool usage success: Effectiveness of any tool calls made during generation
    
    **Code-Specific Signals (programming tasks):**
    - Proper function definitions and structure
    - Error handling and edge case consideration  
    - Documentation and comments
    
    **Operator-Specific Bonuses:**
    - add_fewshot: Bonus for including examples or demonstrations
    - inject_rag: Bonus for referencing external information appropriately
    - toggle_web: Bonus for effectively using web search context
    - temperature operators: Bonus for balancing creativity with structure
    
    Args:
        output (str): The AI-generated response to evaluate
        execution_context (Dict[str, Any]): Runtime information including:
            - tool_success_rate: Fraction of successful tool calls (0.0-1.0)
            - Any other execution metadata
        operator_name (str): Name of the meta-evolution operator used
        
    Returns:
        float: Process reward score (0.0-0.5), where:
            - 0.0: Poor process, no structure or methodology
            - 0.1-0.2: Basic structure present
            - 0.3-0.4: Good methodology and reasoning
            - 0.5: Excellent process (maximum possible)
            
    Example:
        reward = compute_process_reward(
            output="First, I'll analyze the requirements...\ndef solve():\n    # Handle edge case\n    if not data: return None",
            execution_context={"tool_success_rate": 0.9},
            operator_name="add_fewshot"
        )
        # Returns ~0.3 for structured approach + code quality + high tool success
    """
    process_reward = 0.0
    
    # Reasoning format checks
    if has_structured_reasoning(output):
        process_reward += 0.1
    
    # Code quality signals (if code task)
    if is_code_related(output):
        if has_proper_functions(output):
            process_reward += 0.1
        if has_error_handling(output):
            process_reward += 0.05
        if has_documentation(output):
            process_reward += 0.05
    
    # Tool success rate (from execution context)
    tool_success_rate = execution_context.get("tool_success_rate", 1.0)
    process_reward += tool_success_rate * 0.1
    
    # Operator-specific bonuses
    if operator_name == "add_fewshot" and has_examples(output):
        process_reward += 0.05
    elif operator_name == "inject_rag" and has_references(output):
        process_reward += 0.05
    elif operator_name == "toggle_web" and has_web_context(output):
        process_reward += 0.05
    elif operator_name in ["raise_temp", "lower_temp"] and has_creativity_balance(output):
        process_reward += 0.03
    
    return min(process_reward, 0.5)  # Cap at 0.5


def compute_cost_penalty(
    execution_time_ms: int,
    token_usage: Dict[str, int],
    tool_calls: int,
    task_baseline: Dict[str, float]
) -> float:
    """
    Compute cost penalty based on resource usage vs baselines.
    
    Args:
        execution_time_ms: Generation time in milliseconds
        token_usage: {"input": int, "output": int} token counts  
        tool_calls: Number of tool calls made
        task_baseline: Baseline costs for this task type
    """
    penalty = 0.0
    
    # Time penalty (normalized against baseline)
    baseline_time = task_baseline.get("time_ms", 30000)  # 30s default
    if execution_time_ms > baseline_time:
        time_ratio = execution_time_ms / baseline_time
        penalty += min(time_ratio - 1.0, 2.0) * 0.1  # Cap time penalty
    
    # Token usage penalty
    total_tokens = token_usage.get("input", 0) + token_usage.get("output", 0)
    baseline_tokens = task_baseline.get("tokens", 2000)  # 2k tokens default
    if total_tokens > baseline_tokens:
        token_ratio = total_tokens / baseline_tokens  
        penalty += min(token_ratio - 1.0, 3.0) * 0.05  # Cap token penalty
    
    # Tool call penalty (each call adds slight cost)
    penalty += tool_calls * 0.01
    
    return min(penalty, 1.0)  # Cap total cost penalty


def compute_total_reward(
    output: str,
    assertions: Optional[List[str]],
    task: str,
    execution_time_ms: int,
    operator_name: str,
    execution_context: Dict[str, Any],
    test_cmd: Optional[str] = None,
    test_weight: float = 0.0,
    task_baseline: Optional[Dict[str, float]] = None,
    variant_id: Optional[str] = None
) -> Tuple[Dict[str, float], float]:
    """
    Compute total reward and breakdown components.
    
    Returns:
        Tuple of (reward_breakdown, total_reward)
        reward_breakdown: {"outcome_reward": float, "process_reward": float, 
                          "cost_penalty": float, "total_reward": float}
    """
    # Compute components (now returns tuple with metadata)
    outcome_reward, outcome_metadata = compute_outcome_reward(output, assertions, task, test_cmd, test_weight, variant_id=variant_id)
    process_reward = compute_process_reward(output, execution_context, operator_name)
    
    # Estimate token usage if not provided
    token_usage = execution_context.get("token_usage", {
        "input": len(task.split()) * 1.3,  # Rough estimate
        "output": len(output.split()) * 1.3
    })
    
    tool_calls = execution_context.get("tool_calls", 0)
    baseline = task_baseline or get_default_baseline(task)
    
    cost_penalty = compute_cost_penalty(execution_time_ms, token_usage, tool_calls, baseline)
    # Account for evaluation overhead if present
    eval_ms = float(outcome_metadata.get("evaluation_overhead_ms", 0)) if isinstance(outcome_metadata, dict) else 0.0
    if eval_ms > 0:
        base_time = baseline.get("time_ms", 30000)
        # Penalize long evaluation overhead modestly
        cost_penalty += min(eval_ms / max(1.0, base_time), 1.0) * 0.1
    
    # Optional tuning multipliers
    try:
        tpath = _os.path.join(_os.path.dirname(__file__), "..", "..", "storage", "tuning.json")
        _t = _json.load(open(tpath, "r")) if _os.path.exists(tpath) else {}
        m_proc = float(_t.get("process_multiplier", 1.0))
        m_cost = float(_t.get("cost_multiplier", 1.0))
    except Exception:
        m_proc, m_cost = 1.0, 1.0

    # Total reward formula (with optional tuning)
    total_reward = outcome_reward + (process_reward * m_proc) - (cost_penalty * m_cost)
    
    reward_breakdown = {
        "outcome_reward": outcome_reward,
        "process_reward": process_reward * m_proc, 
        "cost_penalty": cost_penalty * m_cost,
        "total_reward": total_reward,
        "outcome_metadata": outcome_metadata  # Include metadata from hybrid scoring
    }
    
    return reward_breakdown, total_reward


def get_default_baseline(task: str) -> Dict[str, float]:
    """Get default baseline costs based on task characteristics."""
    task_lower = task.lower()
    
    # Code tasks tend to be longer
    if any(keyword in task_lower for keyword in ["code", "function", "class", "implement", "python", "javascript"]):
        return {"time_ms": 45000, "tokens": 3000}
    
    # Analysis tasks are medium complexity
    elif any(keyword in task_lower for keyword in ["analyze", "review", "explain", "compare"]):
        return {"time_ms": 35000, "tokens": 2500}
    
    # Simple tasks are faster  
    else:
        return {"time_ms": 25000, "tokens": 1500}


# Helper functions for process reward computation

def has_structured_reasoning(output: str) -> bool:
    """Check if output has structured reasoning patterns."""
    reasoning_patterns = [
        r"(?:first|second|third|next|then|finally)",
        r"(?:because|since|therefore|thus|hence)",
        r"(?:step \d+|phase \d+|\d+\))",
        r"(?:consider|note that|important)"
    ]
    return sum(1 for pattern in reasoning_patterns 
               if re.search(pattern, output, re.IGNORECASE)) >= 2


def is_code_related(output: str) -> bool:
    """Check if output contains code."""
    code_indicators = ["def ", "function", "class ", "import ", "from ", "{", "}", "()", "[]"]
    return sum(1 for indicator in code_indicators if indicator in output) >= 2


def has_proper_functions(output: str) -> bool:
    """Check for well-formed functions."""
    return bool(re.search(r"def\s+\w+\s*\([^)]*\)\s*:", output)) or \
           bool(re.search(r"function\s+\w+\s*\([^)]*\)\s*{", output))


def has_error_handling(output: str) -> bool:
    """Check for error handling patterns."""
    error_patterns = ["try:", "except", "catch", "throw", "raise", "if.*error", "error.*handling"]
    return any(pattern in output.lower() for pattern in error_patterns)


def has_documentation(output: str) -> bool:
    """Check for documentation/comments."""
    doc_patterns = ['"""', "'''", "//", "#", "/**", "*/", "Args:", "Returns:"]
    return sum(1 for pattern in doc_patterns if pattern in output) >= 2


def has_examples(output: str) -> bool:
    """Check if output contains examples."""
    example_patterns = ["example", "for instance", "e.g.", "such as", "like this"]
    return any(pattern in output.lower() for pattern in example_patterns)


def has_references(output: str) -> bool:
    """Check if output references external information."""
    ref_patterns = ["according to", "based on", "reference", "source", "documented"]
    return any(pattern in output.lower() for pattern in ref_patterns)


def has_creativity_balance(output: str) -> bool:
    """Check for balanced creative and structured elements."""
    creative = sum(1 for word in ["innovative", "creative", "unique", "novel", "original"] 
                   if word in output.lower())
    structured = sum(1 for word in ["systematic", "structured", "organized", "methodical"] 
                     if word in output.lower())
    return creative > 0 and structured > 0


def has_web_context(output: str) -> bool:
    """Check if output effectively uses web search context or external information."""
    web_signals = [
        "according to", "based on", "research shows", "studies indicate",
        "current", "recent", "latest", "up-to-date", "as of", 
        "source:", "reference:", "cited", "documentation",
        "web search", "online", "internet", "website", "url",
        "found that", "reported", "published", "article", "paper"
    ]
    
    # Look for multiple web context signals for higher confidence
    signal_count = sum(1 for signal in web_signals if signal in output.lower())
    
    return signal_count >= 2
