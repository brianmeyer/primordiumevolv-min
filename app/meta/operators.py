import random
from typing import Dict, Any, Optional

# Base systems to choose from
SYSTEMS = [
    "You are a concise senior engineer. Return precise, directly usable output.",
    "You are a careful analyst. Explain steps briefly and verify constraints.",
    "You are a creative optimizer. Offer improved alternatives and rationale.",
    "You are a detail-oriented specialist. Focus on accuracy and completeness.",
    "You are an experienced architect. Design robust and scalable solutions."
]

# Base nudges to choose from
NUDGES = [
    "Respond in bullet points.",
    "Prioritize correctness and include one test example.",
    "Add a short checklist at the end.",
    "Use concise, technical language.",
    "Provide step-by-step reasoning.",
    "Include potential edge cases.",
    "Format as structured sections."
]

# Few-shot examples by domain
FEWSHOT_EXAMPLES = {
    "code": "Example: Write a function to reverse a string.\ndef reverse_string(s): return s[::-1]",
    "analysis": "Example: Analyze this data pattern.\nPattern shows 20% increase in usage during peak hours, suggesting need for scaling.",
    "debug": "Example: Fix this bug.\nIssue: IndexError on line 42. Solution: Add bounds checking before array access.",
    "design": "Example: Design a user login system.\nComponents: Authentication service, session management, password hashing, rate limiting."
}

def get_default_plan() -> Dict[str, Any]:
    """Get default execution plan."""
    return {
        "engine": "ollama",
        "system": SYSTEMS[0],
        "nudge": NUDGES[0],
        "params": {"temperature": 0.7, "top_k": 40},
        "use_rag": False,
        "use_memory": False,
        "use_web": False,
        "fewshot": None,
    }

def build_plan(operator_name: str, base_recipe: Optional[Dict] = None) -> Dict[str, Any]:
    """
    Build execution plan by applying operator to base recipe.
    
    Args:
        operator_name: Name of operator to apply
        base_recipe: Base recipe to mutate (if None, use default)
        
    Returns:
        Execution plan dict
    """
    if base_recipe is None:
        plan = get_default_plan()
    else:
        plan = {
            "engine": base_recipe.get("engine", "ollama"),
            "system": base_recipe.get("system", SYSTEMS[0]),
            "nudge": base_recipe.get("nudge", NUDGES[0]),
            "params": base_recipe.get("params", {"temperature": 0.7, "top_k": 40}).copy(),
            "use_rag": base_recipe.get("use_rag", False),
            "use_memory": base_recipe.get("use_memory", False),
            "use_web": base_recipe.get("use_web", False),
            "fewshot": base_recipe.get("fewshot", None)
        }
    
    # Apply operator mutation
    if operator_name == "change_system":
        plan["system"] = random.choice(SYSTEMS)
        
    elif operator_name == "change_nudge":
        plan["nudge"] = random.choice(NUDGES)
        
    elif operator_name == "raise_temp":
        current_temp = plan["params"].get("temperature", 0.7)
        plan["params"]["temperature"] = min(1.5, current_temp + random.uniform(0.1, 0.3))
        
    elif operator_name == "lower_temp":
        current_temp = plan["params"].get("temperature", 0.7)
        plan["params"]["temperature"] = max(0.1, current_temp - random.uniform(0.1, 0.3))
        
    elif operator_name == "inject_rag":
        plan["use_rag"] = True
        
    elif operator_name == "inject_memory":
        plan["use_memory"] = True
        
    elif operator_name == "add_fewshot":
        domain = random.choice(list(FEWSHOT_EXAMPLES.keys()))
        plan["fewshot"] = FEWSHOT_EXAMPLES[domain]
        
    elif operator_name == "toggle_web":
        plan["use_web"] = not plan["use_web"]
        
    # Adjust top_k sampling parameter
    elif operator_name == "raise_top_k":
        current_k = plan["params"].get("top_k", 40)
        plan["params"]["top_k"] = min(100, current_k + random.randint(5, 15))
        
    elif operator_name == "lower_top_k":
        current_k = plan["params"].get("top_k", 40)
        plan["params"]["top_k"] = max(1, current_k - random.randint(5, 15))

    elif operator_name == "use_groq":
        # Engine switch to Groq; runner will validate availability
        plan["engine"] = "groq"
        
    return plan


def apply(plan: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply execution plan to build final prompt and options.
    
    Args:
        plan: Execution plan from build_plan()
        context: Context dict with task, rag_context, memory_context, web_context
        
    Returns:
        Dict with prompt, system, and options for ollama generation
    """
    task = context.get("task", "")
    rag_context = context.get("rag_context", "")
    memory_context = context.get("memory_context", "")
    web_context = context.get("web_context", "")
    
    # Build context sections
    context_parts = []
    
    if plan.get("fewshot"):
        context_parts.append(f"Examples:\n{plan['fewshot']}")
        
    if plan.get("use_rag") and rag_context:
        context_parts.append(f"RAG Context:\n{rag_context}")
        
    if plan.get("use_memory") and memory_context:
        context_parts.append(f"Memory Context:\n{memory_context}")
        
    if plan.get("use_web") and web_context:
        context_parts.append(f"Web Context:\n{web_context}")
    
    # Combine task with context
    if context_parts:
        full_context = "\n\n".join(context_parts)
        prompt = f"{task}\n\nContext:\n{full_context}\n\nConstraints:\n{plan['nudge']}"
    else:
        prompt = f"{task}\n\nConstraints:\n{plan['nudge']}"
    
    return {
        "prompt": prompt,
        "system": plan["system"],
        "options": plan["params"]
    }
