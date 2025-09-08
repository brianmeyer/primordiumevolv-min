"""
Enhanced Quality Evaluation System
==================================

This module implements a sophisticated multi-model AI judging system for evaluating 
response quality in the meta-evolution pipeline. It combines Groq LLM judgment with 
semantic similarity scoring to provide robust, reliable quality assessment.

Key Features:
- Two-judge system with automatic tie-breaker when judges disagree significantly
- 90/10 weighted combination of AI judgment vs semantic similarity
- Smart model rotation across 10 different Groq models for even distribution
- Comprehensive metadata tracking for transparency and debugging

Architecture:
1. Two random Groq models evaluate the response independently
2. If scores differ by >0.3, a third judge reviews both evaluations and decides
3. Final score combines AI judgment (90%) with semantic similarity (10%)

Model Pool:
- llama-3.3-70b-versatile
- openai/gpt-oss-120b
- openai/gpt-oss-20b  
- llama-3.1-8b-instant
- groq/compound
- groq/compound-mini
- meta-llama/llama-4-maverick-17b-128e-instruct
- meta-llama/llama-4-scout-17b-16e-instruct
- qwen/qwen3-32b
- moonshotai/kimi-k2-instruct

Usage:
    score, metadata = evaluate_response_quality(task, assertions, output)
    
Returns:
    Tuple of (final_score: float, metadata: dict) where:
    - final_score: 0.0-1.0 quality score
    - metadata: Detailed breakdown including individual judge scores, reasoning, etc.
"""

import json
import random
from typing import List, Dict, Optional, Tuple
from app.groq_client import chat_complete, available as groq_available
import time as _time
from app.evolve.loop import score_output  # Fallback semantic scoring

# Available judge models for evaluation
JUDGE_MODELS = [
    "llama-3.3-70b-versatile",
    "openai/gpt-oss-120b", 
    "openai/gpt-oss-20b",
    "llama-3.1-8b-instant",
    "groq/compound",
    "groq/compound-mini",
    "meta-llama/llama-4-maverick-17b-128e-instruct",
    "meta-llama/llama-4-scout-17b-16e-instruct", 
    "qwen/qwen3-32b",
    "moonshotai/kimi-k2-instruct"
]

# Track model usage for even distribution
_model_usage_counts = {model: 0 for model in JUDGE_MODELS}

# System prompt for quality evaluation
QUALITY_JUDGE_SYSTEM = """You are an expert evaluator. Rate the quality of an AI response for the given task.

Consider:
- Accuracy and correctness
- Completeness and thoroughness  
- Clarity and coherence
- Relevance to the task
- Practical usefulness

Return ONLY a JSON object with:
{
  "score": <float 0.0-1.0>,
  "reasoning": "<brief explanation>",
  "strengths": ["<strength1>", "<strength2>"],
  "weaknesses": ["<weakness1>", "<weakness2>"]
}"""

# System prompt for third judge (tie-breaker)
TIE_BREAKER_SYSTEM = """You are an expert evaluator resolving a disagreement between two other judges.

Two AI evaluators have scored the same response but gave significantly different scores. Your job is to:
1. Review the original task and response
2. Consider both previous evaluations
3. Make a final, definitive judgment

Be decisive and explain why you agree more with one judge or why you chose a middle ground.

Return ONLY a JSON object with:
{
  "score": <float 0.0-1.0>,
  "reasoning": "<explanation of your decision>",
  "agrees_with": "<judge1|judge2|neither>",
  "final_verdict": "<brief summary>"
}"""

def select_judge_models(num_models: int = 3) -> List[str]:
    """
    Select models for judging with weighted distribution to ensure even usage.
    
    Uses inverse frequency weighting - models that have been used less frequently
    get higher selection probability. This ensures fair distribution across all
    available models over time and prevents bias toward any particular model.
    
    Algorithm:
    1. Calculate inverse weights: weight = 1 / (1 + usage_count)
    2. Use weighted random sampling without replacement
    3. Update usage counters for selected models
    
    Args:
        num_models (int): Number of models to select (default 3, capped to available models)
        
    Returns:
        List[str]: Selected model identifiers
        
    Example:
        models = select_judge_models(2)  # ['llama-3.3-70b-versatile', 'groq/compound']
    """
    if num_models > len(JUDGE_MODELS):
        num_models = len(JUDGE_MODELS)
    
    # Calculate inverse weights (models used less get higher weight)
    total_usage = sum(_model_usage_counts.values()) + len(JUDGE_MODELS)  # Add smoothing
    weights = []
    for model in JUDGE_MODELS:
        # Inverse weight: higher for less used models
        weight = 1.0 / (1 + _model_usage_counts[model])
        weights.append(weight)
    
    # Weighted random selection without replacement
    selected_models = []
    available_models = JUDGE_MODELS.copy()
    available_weights = weights.copy()
    
    for _ in range(num_models):
        if not available_models:
            break
            
        # Weighted random choice
        selected_idx = random.choices(range(len(available_models)), weights=available_weights)[0]
        selected_model = available_models.pop(selected_idx)
        available_weights.pop(selected_idx)
        
        selected_models.append(selected_model)
        _model_usage_counts[selected_model] += 1
    
    return selected_models

def build_quality_prompt(task: str, assertions: List[str], output: str) -> str:
    """
    Build the evaluation prompt for Groq judge models.
    
    Creates a structured prompt that provides the judge with:
    - The original task description
    - Any specific requirements/assertions to check
    - The AI response to be evaluated
    
    Args:
        task (str): The original task description
        assertions (List[str]): List of specific requirements/constraints
        output (str): The AI response to evaluate
        
    Returns:
        str: Formatted prompt for the judge model
        
    Example:
        prompt = build_quality_prompt(
            task="Write a Python function to sort a list",
            assertions=["Must handle empty lists", "Should be efficient"],
            output="def sort_list(lst): return sorted(lst)"
        )
    """
    prompt = f"""Task: {task}

"""
    
    if assertions:
        prompt += f"""Requirements:
{chr(10).join(f"• {assertion}" for assertion in assertions)}

"""
    
    prompt += f"""AI Response to Evaluate:
{output}

Please evaluate this response's quality."""
    
    return prompt

def build_tie_breaker_prompt(task: str, assertions: List[str], output: str, judge1_result: Dict, judge2_result: Dict) -> str:
    """
    Build prompt for third judge to resolve significant disagreement between initial judges.
    
    When two judges disagree significantly (score difference ≥ 0.3), this creates a prompt
    for a third judge that includes:
    - The original task and response
    - Both previous judges' scores and detailed reasoning
    - Request for final decisive judgment
    
    Args:
        task (str): Original task description
        assertions (List[str]): Task requirements/constraints  
        output (str): AI response being evaluated
        judge1_result (Dict): First judge's evaluation with score, reasoning, etc.
        judge2_result (Dict): Second judge's evaluation with score, reasoning, etc.
        
    Returns:
        str: Formatted prompt for tie-breaker judge
        
    Example:
        When Judge 1 scores 0.8 and Judge 2 scores 0.4, the tie-breaker gets both
        evaluations and must decide which is more accurate or find middle ground.
    """
    prompt = f"""Original Task: {task}

"""
    
    if assertions:
        prompt += f"""Requirements:
{chr(10).join(f"• {assertion}" for assertion in assertions)}

"""
    
    prompt += f"""AI Response Being Evaluated:
{output}

JUDGE 1 ({judge1_result['model']}) - Score: {judge1_result['score']}
Reasoning: {judge1_result.get('reasoning', 'N/A')}
Strengths: {judge1_result.get('strengths', [])}
Weaknesses: {judge1_result.get('weaknesses', [])}

JUDGE 2 ({judge2_result['model']}) - Score: {judge2_result['score']}
Reasoning: {judge2_result.get('reasoning', 'N/A')}
Strengths: {judge2_result.get('strengths', [])}
Weaknesses: {judge2_result.get('weaknesses', [])}

The judges disagree significantly. Please make the final decision."""
    
    return prompt

def groq_quality_score(task: str, assertions: List[str], output: str, disagreement_threshold: float = 0.3) -> Tuple[float, Dict]:
    """
    Core two-judge evaluation system with automatic tie-breaker for disagreements.
    
    This is the heart of the quality evaluation system. It implements a robust
    judging process designed to minimize noise and maximize reliability:
    
    Process Flow:
    1. Select two judges using weighted model rotation
    2. Each judge independently evaluates the response
    3. If judges agree (score difference < threshold): use average
    4. If judges disagree significantly (≥ threshold): invoke tie-breaker
    5. Tie-breaker judge sees both evaluations and makes final decision
    
    Scoring Criteria (judges evaluate on):
    - Accuracy and correctness
    - Completeness and thoroughness
    - Clarity and coherence
    - Relevance to the task
    - Practical usefulness
    
    Args:
        task (str): The original task description
        assertions (List[str]): List of specific requirements/constraints to check
        output (str): The AI response to be evaluated
        disagreement_threshold (float): Score difference that triggers tie-breaker (default 0.3)
        
    Returns:
        Tuple[float, Dict]: 
            - final_score: 0.0-1.0 quality score
            - metadata: Comprehensive evaluation details including:
                * individual_judge_scores: Scores from each judge
                * needed_tie_breaker: Whether disagreement resolution was used  
                * score_difference: Absolute difference between initial judges
                * judge_results: Full evaluation details from each model
                * tie_breaker_result: Tie-breaker evaluation (if used)
                
    Example:
        score, meta = groq_quality_score(
            task="Write a function to calculate fibonacci numbers",
            assertions=["Must handle n=0 and n=1", "Should be efficient"],
            output="def fib(n): return n if n <= 1 else fib(n-1) + fib(n-2)"
        )
        # score: 0.75, meta shows both judges agreed within threshold
    """
    if not groq_available():
        return 0.0, {"error": "groq_unavailable"}
    
    # Select two judges first
    initial_judges = select_judge_models(2)
    judge_results = []
    successful_scores = []
    
    # Get evaluations from both judges
    for model in initial_judges:
        try:
            messages = [
                {"role": "system", "content": QUALITY_JUDGE_SYSTEM},
                {"role": "user", "content": build_quality_prompt(task, assertions or [], output)}
            ]
            start = _time.time()
            response = chat_complete(messages, model_id=model, temperature=0.1)
            elapsed_ms = int((_time.time() - start) * 1000)
            
            # Parse JSON response
            if response.strip().startswith('{'):
                data = json.loads(response.strip())
                score = float(data.get("score", 0.0))
                # Ensure score is in valid range
                score = max(0.0, min(1.0, score))
                
                judge_result = {
                    "model": model,
                    "score": score,
                    "reasoning": data.get("reasoning", ""),
                    "strengths": data.get("strengths", []),
                    "weaknesses": data.get("weaknesses", []),
                    "raw_response": response,
                    "duration_ms": elapsed_ms,
                    "role": f"judge_{len(successful_scores) + 1}"
                }
                
                judge_results.append(judge_result)
                successful_scores.append(score)
            else:
                # Record failure
                judge_results.append({
                    "model": model,
                    "error": "invalid_json",
                    "raw_response": response,
                    "role": f"judge_{len(judge_results) + 1}"
                })
                
        except Exception as e:
            # Record failure
            judge_results.append({
                "model": model,
                "error": str(e),
                "role": f"judge_{len(judge_results) + 1}"
            })
    
    # Check if we need a tie-breaker
    need_tie_breaker = False
    if len(successful_scores) == 2:
        score_difference = abs(successful_scores[0] - successful_scores[1])
        need_tie_breaker = score_difference >= disagreement_threshold
    elif len(successful_scores) < 2:
        # If we don't have 2 successful evaluations, we need more judges
        need_tie_breaker = True
    
    tie_breaker_result = None
    final_score = 0.0
    
    if need_tie_breaker and len(successful_scores) == 2:
        # Use tie-breaker judge
        tie_breaker_model = select_judge_models(1)[0]
        
        try:
            # Get the two successful judge results for the tie-breaker prompt
            judge1_result = next((r for r in judge_results if r.get("role") == "judge_1" and "score" in r), None)
            judge2_result = next((r for r in judge_results if r.get("role") == "judge_2" and "score" in r), None)
            
            if judge1_result is None or judge2_result is None:
                # Can't find successful judge results for tie-breaker
                final_score = sum(successful_scores) / len(successful_scores) if successful_scores else 0.0
                tie_breaker_result = {
                    "model": tie_breaker_model,
                    "error": "missing_judge_results",
                    "role": "tie_breaker"
                }
                return final_score, {
                    "method": "two_judge_plus_tiebreaker",
                    "disagreement_threshold": disagreement_threshold,
                    "needed_tie_breaker": need_tie_breaker,
                    "successful_initial_judges": len(successful_scores),
                    "score_difference": abs(successful_scores[0] - successful_scores[1]) if len(successful_scores) == 2 else None,
                    "final_score": final_score,
                    "initial_scores": successful_scores,
                    "judge_results": judge_results,
                    "tie_breaker_result": tie_breaker_result,
                    "error": "tie_breaker_failed_missing_results"
                }
            
            messages = [
                {"role": "system", "content": TIE_BREAKER_SYSTEM},
                {"role": "user", "content": build_tie_breaker_prompt(task, assertions or [], output, judge1_result, judge2_result)}
            ]
            
            start_tb = _time.time()
            response = chat_complete(messages, model_id=tie_breaker_model, temperature=0.1)
            elapsed_tb_ms = int((_time.time() - start_tb) * 1000)
            
            # Parse tie-breaker response
            if response.strip().startswith('{'):
                data = json.loads(response.strip())
                tie_breaker_score = float(data.get("score", 0.0))
                tie_breaker_score = max(0.0, min(1.0, tie_breaker_score))
                
                tie_breaker_result = {
                    "model": tie_breaker_model,
                    "score": tie_breaker_score,
                    "reasoning": data.get("reasoning", ""),
                    "agrees_with": data.get("agrees_with", "neither"),
                    "final_verdict": data.get("final_verdict", ""),
                    "raw_response": response,
                    "duration_ms": elapsed_tb_ms,
                    "role": "tie_breaker"
                }
                
                final_score = tie_breaker_score
            else:
                # Tie-breaker failed, use average
                final_score = sum(successful_scores) / len(successful_scores)
                tie_breaker_result = {
                    "model": tie_breaker_model,
                    "error": "invalid_json", 
                    "raw_response": response,
                    "role": "tie_breaker"
                }
                
        except Exception as e:
            # Tie-breaker failed, use average
            final_score = sum(successful_scores) / len(successful_scores)
            tie_breaker_result = {
                "model": tie_breaker_model if 'tie_breaker_model' in locals() else "unknown",
                "error": str(e),
                "role": "tie_breaker"
            }
    else:
        # No tie-breaker needed or not enough successful judges
        if successful_scores:
            final_score = sum(successful_scores) / len(successful_scores)
        else:
            final_score = 0.0
    
    # Build metadata
    metadata = {
        "method": "two_judge_plus_tiebreaker",
        "disagreement_threshold": disagreement_threshold,
        "needed_tie_breaker": need_tie_breaker,
        "successful_initial_judges": len(successful_scores),
        "score_difference": abs(successful_scores[0] - successful_scores[1]) if len(successful_scores) == 2 else None,
        "final_score": final_score,
        "initial_scores": successful_scores,
        "judge_results": judge_results
    }
    
    if tie_breaker_result:
        metadata["tie_breaker_result"] = tie_breaker_result
    
    if len(successful_scores) == 0:
        metadata["error"] = "no_successful_evaluations"
        return 0.0, metadata
    
    return final_score, metadata

def hybrid_quality_score(
    task: str, 
    assertions: List[str], 
    output: str,
    semantic_weight: float = 0.1,
    groq_weight: float = 0.9,
    disagreement_threshold: float = 0.3
) -> Tuple[float, Dict]:
    """
    Hybrid scoring system combining AI judgment with semantic similarity.
    
    This function provides the complete evaluation pipeline by combining:
    - Groq AI judgment (90%): Multi-model evaluation of quality, correctness, usefulness
    - Semantic similarity (10%): Topical alignment between task and response
    
    The 90/10 weighting heavily favors AI judgment because:
    - AI judges can assess correctness, not just topical similarity
    - Multiple models provide robust consensus on quality
    - Semantic similarity alone cannot detect factual errors or poor reasoning
    
    Evaluation Process:
    1. Calculate semantic similarity score using sentence transformers
    2. Get AI judgment score using two-judge + tie-breaker system
    3. Combine scores: final = (0.9 * ai_score) + (0.1 * semantic_score)
    4. If AI judgment fails, fall back to pure semantic scoring
    
    Args:
        task (str): The original task description
        assertions (List[str]): List of specific requirements/constraints
        output (str): The AI response to evaluate
        semantic_weight (float): Weight for semantic similarity component (default 0.1)
        groq_weight (float): Weight for AI judgment component (default 0.9)
        disagreement_threshold (float): Score difference triggering tie-breaker (default 0.3)
        
    Returns:
        Tuple[float, Dict]: 
            - final_score: 0.0-1.0 combined quality score
            - metadata: Detailed breakdown including:
                * method: "hybrid_two_judge" or "semantic_fallback"
                * semantic_score: Raw semantic similarity score
                * groq_score: Raw AI judgment score
                * groq_metadata: Full AI evaluation details
                * final_score: Combined weighted score
                
    Example:
        score, meta = hybrid_quality_score(
            task="Explain quantum computing",
            assertions=["Must be accessible to beginners"],
            output="Quantum computing uses quantum mechanics principles..."
        )
        # Returns combined score with detailed breakdown
    """
    # Get semantic score (existing system)
    semantic_score = score_output(output, assertions, task)
    
    # Get two-judge + tie-breaker Groq quality score
    groq_score, groq_metadata = groq_quality_score(task, assertions, output, disagreement_threshold)
    
    # Combine scores
    if groq_metadata.get("error"):
        # If Groq fails, fall back to pure semantic
        final_score = semantic_score
        method = "semantic_fallback"
    else:
        # Weighted combination (90% Groq, 10% semantic)
        final_score = (semantic_weight * semantic_score) + (groq_weight * groq_score)
        method = "hybrid_two_judge"
    
    # Compute evaluation overhead from returned Groq metadata
    total_eval_overhead_ms = 0
    try:
        jr = (groq_metadata or {}).get("judge_results") or []
        if isinstance(jr, list):
            total_eval_overhead_ms = sum((r or {}).get("duration_ms", 0) for r in jr if isinstance(r, dict))
        tbr = (groq_metadata or {}).get("tie_breaker_result")
        if isinstance(tbr, dict):
            total_eval_overhead_ms += tbr.get("duration_ms", 0)
    except Exception:
        # Best-effort; lack of overhead should not break scoring
        total_eval_overhead_ms = 0
    metadata = {
        "method": method,
        "semantic_score": semantic_score,
        "semantic_weight": semantic_weight,
        "groq_score": groq_score,
        "groq_weight": groq_weight,
        "disagreement_threshold": disagreement_threshold,
        "groq_metadata": groq_metadata,
        "final_score": final_score,
        "evaluation_overhead_ms": total_eval_overhead_ms
    }
    
    return final_score, metadata

# Main API Entry Point
def evaluate_response_quality(task: str, assertions: List[str], output: str) -> Tuple[float, Dict]:
    """
    Main entry point for response quality evaluation in the meta-evolution system.
    
    This is the primary function used throughout the codebase for evaluating AI response
    quality. It implements the complete evaluation pipeline with optimized defaults:
    
    - Two-judge AI evaluation system with automatic tie-breaker
    - 90% weight on AI judgment, 10% on semantic similarity  
    - 0.3 disagreement threshold for triggering tie-breaker
    - Weighted model rotation for fair distribution across 10 Groq models
    
    Key Benefits:
    - Robust scoring that reduces noise from outlier evaluations
    - Transparent metadata for debugging and analysis
    - Graceful fallbacks if AI models are unavailable
    - Consistent scoring across different types of tasks
    
    Integration Points:
    - Used by app/meta/rewards.py in compute_outcome_reward()
    - Called during meta-evolution to score response variants
    - Provides scores for UCB bandit algorithm in operator selection
    
    Args:
        task (str): The original task or question that was asked
        assertions (List[str]): List of specific requirements, constraints, or criteria
        output (str): The AI-generated response to be evaluated
        
    Returns:
        Tuple[float, Dict]: 
            - score: Final quality score from 0.0 (worst) to 1.0 (best)
            - metadata: Comprehensive evaluation breakdown for analysis/debugging
            
    Example Usage:
        # Basic evaluation
        score, meta = evaluate_response_quality(
            task="Write a Python function to reverse a string",
            assertions=["Must handle empty strings", "Should be efficient"],
            output="def reverse_str(s): return s[::-1]"
        )
        
        # score: ~0.85 (high quality - correct, efficient, handles edge case)
        # meta contains judge scores, reasoning, tie-breaker info, etc.
    """
    return hybrid_quality_score(
        task=task,
        assertions=assertions,
        output=output,
        semantic_weight=0.1,        # 10% weight for semantic similarity
        groq_weight=0.9,            # 90% weight for Groq judgment
        disagreement_threshold=0.3  # Trigger tie-breaker if judges differ by 0.3+
    )
