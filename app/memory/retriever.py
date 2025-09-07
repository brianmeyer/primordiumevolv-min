"""
Memory retrieval and evolution primer generation.
Transforms historical experiences into actionable evolutionary hints.
"""
import json
from typing import List, Tuple
import logging

from app.config import MEMORY_PRIMER_TOKENS_MAX
from app.memory.store import Experience
from app.memory.embed import estimate_tokens

logger = logging.getLogger(__name__)

def build_memory_primer(experiences: List[Experience]) -> Tuple[str, int]:
    """
    Build evolution primer from retrieved experiences.
    
    Returns:
        Tuple of (primer_text, estimated_token_count)
    """
    if not experiences:
        return "", 0
    
    try:
        # Sort experiences by reward (best first)
        sorted_experiences = sorted(experiences, key=lambda x: x.reward, reverse=True)
        
        primer_parts = [
            "Evolutionary seeds from similar past cases (higher reward is better):"
        ]
        
        for i, exp in enumerate(sorted_experiences, 1):
            # Extract key information
            plan_excerpt = _extract_plan_excerpt(exp.plan_json)
            output_excerpt = _extract_output_excerpt(exp.output_text)
            weaknesses = _infer_weaknesses(exp)
            
            # Format experience entry
            entry = f"""
{i}. Reward:{exp.reward:.2f} Δ:{exp.improvement_delta:.2f} Conf:{exp.confidence_score:.2f} Op:{exp.operator_used}
   Plan excerpt: {plan_excerpt}
   Output excerpt: {output_excerpt}
   Known weaknesses: {weaknesses}"""
            
            primer_parts.append(entry)
            
            # Check token limit after adding each experience
            current_primer = "\n".join(primer_parts + [_get_evolution_instruction()])
            if estimate_tokens(current_primer) > MEMORY_PRIMER_TOKENS_MAX:
                # Remove the last addition and break
                primer_parts.pop()
                break
        
        # Add evolution instruction
        primer_parts.append(_get_evolution_instruction())
        
        final_primer = "\n".join(primer_parts)
        token_count = estimate_tokens(final_primer)
        
        logger.debug(f"Built memory primer: {len(sorted_experiences)} experiences, {token_count} tokens")
        return final_primer, token_count
        
    except Exception as e:
        logger.error(f"Failed to build memory primer: {e}")
        return "", 0

def _extract_plan_excerpt(plan_json: dict, max_chars: int = 150) -> str:
    """Extract meaningful excerpt from plan JSON."""
    try:
        if not plan_json:
            return "N/A"
            
        # Try to extract key fields from plan
        key_fields = ['system', 'nudge', 'strategy', 'approach', 'method', 'plan']
        
        for field in key_fields:
            if field in plan_json and plan_json[field]:
                text = str(plan_json[field])
                if len(text) <= max_chars:
                    return text
                else:
                    return text[:max_chars-3] + "..."
        
        # Fallback: use JSON string truncated
        plan_str = json.dumps(plan_json, sort_keys=True)
        if len(plan_str) <= max_chars:
            return plan_str
        else:
            return plan_str[:max_chars-3] + "..."
            
    except Exception as e:
        logger.error(f"Failed to extract plan excerpt: {e}")
        return "N/A"

def _extract_output_excerpt(output_text: str, max_chars: int = 200) -> str:
    """Extract meaningful excerpt from output text."""
    try:
        if not output_text:
            return "N/A"
            
        # Clean up the output text
        cleaned = output_text.strip()
        
        # Handle multi-line outputs - prefer first substantial line
        lines = [line.strip() for line in cleaned.split('\n') if line.strip()]
        if lines:
            first_line = lines[0]
            if len(first_line) <= max_chars:
                return first_line
            else:
                return first_line[:max_chars-3] + "..."
        
        # Fallback: truncate full text
        if len(cleaned) <= max_chars:
            return cleaned
        else:
            return cleaned[:max_chars-3] + "..."
            
    except Exception as e:
        logger.error(f"Failed to extract output excerpt: {e}")
        return "N/A"

def _infer_weaknesses(exp: Experience) -> str:
    """Infer potential weaknesses from experience metadata."""
    try:
        weaknesses = []
        
        # Confidence-based inferences
        if exp.confidence_score < 0.7:
            weaknesses.append("low judge confidence")
            
        # Reward-based inferences  
        if exp.reward < 0.8:
            if exp.judge_ai > 0 and exp.judge_semantic > 0:
                if exp.judge_ai < exp.judge_semantic:
                    weaknesses.append("AI judge scored lower than semantic")
                elif exp.judge_semantic < 0.5:
                    weaknesses.append("poor semantic match")
                    
        # Performance-based inferences
        if exp.latency_ms > 10000:  # > 10 seconds
            weaknesses.append("slow execution")
            
        if exp.tokens_out > exp.tokens_in * 3:  # Very verbose
            weaknesses.append("overly verbose output")
            
        # Operator-specific inferences
        if exp.operator_used in ["raise_temp", "lower_temp"]:
            if exp.reward < 0.6:
                weaknesses.append("temperature adjustment ineffective")
                
        elif exp.operator_used == "add_fewshot":
            if exp.reward < 0.7:
                weaknesses.append("examples may not be relevant")
                
        # Return formatted weaknesses or N/A
        if weaknesses:
            return "; ".join(weaknesses)
        else:
            return "N/A"
            
    except Exception as e:
        logger.error(f"Failed to infer weaknesses: {e}")
        return "N/A"

def _get_evolution_instruction() -> str:
    """Get the evolution instruction for the primer."""
    return """
Objective: Evolve a new approach that improves on these strengths and avoids the weaknesses listed above. 
Do not copy verbatim - use these as evolutionary seeds to inspire novel improvements."""

def format_memory_context(experiences: List[Experience], query_text: str) -> str:
    """
    Format experiences as general context (alternative to primer approach).
    Useful for different injection strategies.
    """
    if not experiences:
        return ""
        
    try:
        context_parts = [
            f"Context: Similar tasks have been handled as follows:"
        ]
        
        for i, exp in enumerate(experiences[:3], 1):  # Limit to top 3
            plan_summary = _extract_plan_excerpt(exp.plan_json, 100)
            outcome = "succeeded" if exp.reward > 0.7 else "partially succeeded" if exp.reward > 0.4 else "struggled"
            
            context_entry = f"{i}. Previous approach: {plan_summary} (outcome: {outcome}, reward: {exp.reward:.2f})"
            context_parts.append(context_entry)
        
        context_parts.append(f"Current task: {query_text}")
        context_parts.append("Based on this context, provide an improved approach.")
        
        return "\n".join(context_parts)
        
    except Exception as e:
        logger.error(f"Failed to format memory context: {e}")
        return ""

def truncate_to_token_limit(text: str, max_tokens: int) -> str:
    """Truncate text to approximate token limit."""
    if not text:
        return text
        
    current_tokens = estimate_tokens(text)
    if current_tokens <= max_tokens:
        return text
    
    # Rough truncation: remove characters proportionally
    target_chars = len(text) * max_tokens // current_tokens
    
    if target_chars < len(text):
        truncated = text[:target_chars-20]  # Leave some buffer
        # Try to end at a sentence or line boundary
        for boundary in ['. ', '\n', '; ', ', ']:
            last_boundary = truncated.rfind(boundary)
            if last_boundary > target_chars * 0.8:  # Don't truncate too much
                return truncated[:last_boundary + len(boundary)] + "[truncated]"
                
        return truncated + "[truncated]"
    
    return text