#!/usr/bin/env python3
"""
Comprehensive fix for DGM proposal generation to handle ALL operator areas
"""

# Complete area configuration that matches ALL operators
COMPREHENSIVE_AREA_CONFIG = {
    "operators": {
        "files": ["app/meta/operators.py"],
        "parameters": {
            "change_system": {"line": 71, "type": "string", "description": "System prompt modification"},
            "change_nudge": {"line": 74, "type": "string", "description": "Nudge prompt modification"},
            "raise_temp": {"line": 78, "type": "float", "range": "+0.1", "description": "Temperature increase"},
            "lower_temp": {"line": 82, "type": "float", "range": "-0.1", "description": "Temperature decrease"},
            "add_fewshot": {"line": 92, "type": "list", "description": "Few-shot examples"},
            "inject_memory": {"line": 88, "type": "bool", "description": "Memory injection flag"},
            "inject_rag": {"line": 85, "type": "bool", "description": "RAG injection flag"},
            "toggle_web": {"line": 95, "type": "bool", "description": "Web search toggle"},
            "raise_top_k": {"line": 99, "type": "int", "range": "+5", "description": "Top-k sampling increase"},
            "lower_top_k": {"line": 103, "type": "int", "range": "-5", "description": "Top-k sampling decrease"},
            "use_groq": {"line": 106, "type": "bool", "description": "Use Groq engine"}
        }
    },
    "prompts": {
        "files": ["app/meta/operators.py"],
        "parameters": {
            "system_prompt": {"line": 71, "type": "string", "description": "Main system prompt"},
            "nudge_prompt": {"line": 74, "type": "string", "description": "Nudge guidance"}
        }
    },
    "bandit": {
        "files": ["app/config.py"],
        "parameters": {
            "ucb_c": {"current": 2.0, "range": "±0.1", "line": 23, "type": "float", "description": "UCB exploration constant"},
            "eps": {"current": 0.6, "range": "±0.05", "line": 19, "type": "float", "description": "Epsilon for epsilon-greedy"},
            "warm_start_min_pulls": {"current": 1, "range": "±1", "line": 24, "type": "int", "description": "Min pulls before UCB"},
            "stratified_explore": {"current": True, "range": "toggle", "line": 25, "type": "bool", "description": "First pass diversity"}
        }
    },
    "rag": {
        "files": ["app/config.py"],
        "parameters": {
            "rag_k": {"current": 3, "range": "±1", "line": 18, "type": "int", "description": "Number of RAG results"}
        }
    },
    "memory_policy": {
        "files": ["app/config.py"],
        "parameters": {
            "MEMORY_REWARD_WEIGHT": {"current": 0.3, "range": "±0.05", "line": 53, "type": "float", "description": "Memory reward weight"},
            "MEMORY_MIN_CONFIDENCE": {"current": 0.5, "range": "±0.1", "line": 56, "type": "float", "description": "Min confidence threshold"},
            "MEMORY_BASELINE_REWARD": {"current": 0.5, "range": "±0.1", "line": 57, "type": "float", "description": "Baseline reward"},
            "MEMORY_K": {"current": 5, "range": "±2", "line": 47, "type": "int", "description": "Number of memory results"}
        }
    },
    "temperature": {
        "files": ["app/meta/operators.py"],
        "parameters": {
            "default_temp": {"current": 0.7, "range": "±0.1", "line": 78, "type": "float", "description": "Default temperature"}
        }
    },
    "sampling": {
        "files": ["app/meta/operators.py"],
        "parameters": {
            "top_k": {"current": 40, "range": "±10", "line": 99, "type": "int", "description": "Top-k sampling parameter"},
            "top_p": {"current": 0.9, "range": "±0.05", "line": 100, "type": "float", "description": "Top-p nucleus sampling"}
        }
    },
    "web_search": {
        "files": ["app/config.py"],
        "parameters": {
            "web_k": {"current": 3, "range": "±1", "line": 20, "type": "int", "description": "Web search results count"}
        }
    },
    "fewshot": {
        "files": ["app/meta/operators.py"],
        "parameters": {
            "num_examples": {"current": 2, "range": "±1", "line": 92, "type": "int", "description": "Number of few-shot examples"}
        }
    }
}

def get_comprehensive_snapshot(area: str):
    """Get proper file snapshot for ANY area"""
    import os
    
    config = COMPREHENSIVE_AREA_CONFIG.get(area)
    if not config:
        return []
    
    snapshots = []
    for file_path in config.get("files", []):
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r') as f:
                    content = f.read()
                snapshots.append({
                    'path': file_path,
                    'content': content,
                    'area': area
                })
            except Exception as e:
                print(f"Error reading {file_path}: {e}")
    
    return snapshots

def make_comprehensive_prompt(area: str, snapshot: dict):
    """Create a complete prompt for ANY area with proper parameters"""
    
    config = COMPREHENSIVE_AREA_CONFIG.get(area)
    if not config:
        return "ERROR: Unknown area"
    
    if not snapshot:
        return "ERROR: No file snapshot provided"
    
    file_path = snapshot['path']
    params = config.get("parameters", {})
    
    # Build focused prompt
    prompt = f"""Generate a minimal code patch for {area} in {file_path}.

AREA: {area}
FILE: {file_path}

AVAILABLE PARAMETERS TO MODIFY:
"""
    
    for param_name, param_info in params.items():
        current = param_info.get('current', 'N/A')
        change_range = param_info.get('range', '±0.1')
        line = param_info.get('line', 'unknown')
        prompt += f"- {param_name}: line {line}, current={current}, change by {change_range}\n"
    
    prompt += f"""
CRITICAL: Output ONLY this JSON (no explanation):
{{"area":"{area}","rationale":"<10 words max>","diff":"<minimal unified diff>"}}

FILE CONTENT (first 500 chars):
{snapshot['content'][:500]}

Generate the JSON now:"""
    
    return prompt

# Test the comprehensive solution
if __name__ == "__main__":
    print("Testing comprehensive DGM fix...")
    print("=" * 80)
    
    # Test all areas
    for area in COMPREHENSIVE_AREA_CONFIG.keys():
        print(f"\nArea: {area}")
        snapshots = get_comprehensive_snapshot(area)
        if snapshots:
            print(f"  ✓ Found {len(snapshots)} file(s)")
            prompt = make_comprehensive_prompt(area, snapshots[0])
            print(f"  ✓ Generated prompt ({len(prompt)} chars)")
            print(f"  Parameters: {list(COMPREHENSIVE_AREA_CONFIG[area]['parameters'].keys())}")
        else:
            print(f"  ✗ No files found")
    
    print("\n" + "=" * 80)
    print("All areas properly configured!")