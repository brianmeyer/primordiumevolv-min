"""
Improved prompt for DGM that is explicit and accurate
"""

def make_prompt_improved(allowed_areas, max_loc, snapshots=None):
    """Create a MUCH better prompt that is explicit about what exists"""
    
    import os
    
    # Reality check - what files actually exist
    existing_files = {
        "bandit": {
            "files": ["app/config.py"],
            "exists": os.path.exists("app/config.py"),
            "parameters": {
                "ucb_c": {"current": 2.0, "range": "±0.02", "line": 23, "description": "UCB exploration constant"},
                "eps": {"current": 0.6, "range": "±0.02", "line": 19, "description": "Epsilon for epsilon-greedy"},
                "warm_start_min_pulls": {"current": 1, "range": "±1", "line": 24, "description": "Min pulls before UCB"},
                "stratified_explore": {"current": "true", "range": "true/false", "line": 25, "description": "First pass diversity"}
            }
        },
        "memory_policy": {
            "files": ["app/config.py", "app/memory/store.py", "app/memory/embed.py"],
            "exists": os.path.exists("app/memory/store.py"),
            "parameters": {
                "MEMORY_REWARD_WEIGHT": {"current": 0.3, "range": "±0.05", "line": 53, "description": "Memory reward weight"},
                "MEMORY_MIN_CONFIDENCE": {"current": 0.5, "range": "±0.1", "line": 56, "description": "Min confidence threshold"},
                "MEMORY_BASELINE_REWARD": {"current": 0.5, "range": "±0.1", "line": 57, "description": "Baseline reward"},
                "MEMORY_K": {"current": 5, "range": "±2", "line": 47, "description": "Number of memory results"}
            }
        }
    }
    
    # Only use areas that have existing files
    valid_areas = [area for area in allowed_areas if area in existing_files and existing_files[area]["exists"]]
    
    if not snapshots or len(snapshots) == 0:
        return "ERROR: No file snapshot provided. Cannot generate patch without file content."
    
    # Determine which area we're working with based on the file
    file_path = snapshots[0]['path']
    current_area = None
    if "config.py" in file_path:
        # Could be bandit or memory_policy - need to check what was requested
        current_area = "bandit"  # Default to bandit for config.py
    elif "memory" in file_path:
        current_area = "memory_policy"
    
    if not current_area or current_area not in valid_areas:
        return f"ERROR: File {file_path} doesn't match any valid area. Valid areas: {valid_areas}"
    
    # Get the specific parameters for this area
    params = existing_files[current_area]["parameters"]
    
    # Build very explicit prompt
    prompt = f'''You are modifying the PrimordiumEvolv system. Generate ONE small patch.

CRITICAL INSTRUCTIONS:
1. You are editing: {file_path}
2. Area: {current_area}
3. You can ONLY change these specific parameters:
'''
    
    for param_name, param_info in params.items():
        prompt += f'''   - {param_name}: Currently {param_info["current"]}, can change by {param_info["range"]} (line {param_info["line"]})
'''
    
    prompt += f'''
4. Output ONLY valid JSON with these exact fields:
   - "area": Must be "{current_area}"
   - "rationale": Brief explanation (max 10 words)
   - "diff": Valid unified diff format

EXAMPLE OF CORRECT OUTPUT:
{{
    "area": "{current_area}",
    "rationale": "Slight increase in {"exploration" if current_area == "bandit" else "memory importance"}",
    "diff": "--- a/{file_path}\\n+++ b/{file_path}\\n@@ -{params[list(params.keys())[0]]["line"]},7 +{params[list(params.keys())[0]]["line"]},7 @@\\n     # Comment line before\\n-    \\"{list(params.keys())[0]}\\": {params[list(params.keys())[0]]["current"]},\\n+    \\"{list(params.keys())[0]}\\": {params[list(params.keys())[0]]["current"] + 0.01 if isinstance(params[list(params.keys())[0]]["current"], float) else params[list(params.keys())[0]]["current"] + 1},\\n     # Comment line after"
}}

CURRENT FILE CONTENT (first 1000 chars):
{snapshots[0]['content'][:1000]}

CRITICAL RULES:
- The diff MUST use exact path: {file_path}
- The diff MUST have proper context lines (3 before and after)
- The diff MUST use @@ -line,count +line,count @@ format
- Only change ONE parameter value
- Change must be minimal ({params[list(params.keys())[0]]["range"]})

Output ONLY the JSON object:'''
    
    return prompt

# Test the improved prompt
if __name__ == "__main__":
    from app.dgm.proposer import get_snapshot, DGM_ALLOWED_AREAS, DGM_MAX_LOC_DELTA
    
    # Get a real snapshot
    snapshots = get_snapshot("bandit")
    
    # Generate improved prompt
    prompt = make_prompt_improved(DGM_ALLOWED_AREAS, DGM_MAX_LOC_DELTA, snapshots)
    
    print("===== IMPROVED PROMPT =====")
    print(prompt)