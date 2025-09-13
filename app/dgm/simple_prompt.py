"""
Simple prompt that dynamically handles all operator types
"""
import random

def make_simple_prompt(allowed_areas, max_loc, snapshots=None):
    """Create a SIMPLE prompt that models can actually follow"""
    
    if not snapshots or len(snapshots) == 0:
        return "ERROR: No file snapshot provided."
    
    file_path = snapshots[0]['path']
    file_content = snapshots[0].get('content', '')
    
    if not file_content:
        return "ERROR: No file content provided."
    
    # Choose a random area from allowed areas
    area = random.choice(allowed_areas) if allowed_areas else "operators"
    
    # Map areas to specific changes with realistic values
    area_changes = {
        "operators": [
            {"param": "temperature", "current": "0.7", "new": str(round(random.uniform(0.3, 1.2), 1)), "line": 78},
            {"param": "top_k", "current": "40", "new": str(random.randint(20, 80)), "line": 99},
        ],
        "prompts": [
            {"param": "system prompt", "current": "You are a concise senior engineer", "new": "You are a thorough technical architect", "line": 6},
            {"param": "system prompt", "current": "You are a careful analyst", "new": "You are a methodical problem solver", "line": 7},
        ],
        "bandit": [
            {"param": "ucb_c", "current": "2.0", "new": str(round(random.uniform(1.5, 3.0), 1)), "line": 23},
            {"param": "epsilon", "current": "0.6", "new": str(round(random.uniform(0.3, 0.8), 1)), "line": 31},
        ],
        "rag": [
            {"param": "rag_k", "current": "5", "new": str(random.randint(3, 10)), "line": 42},
            {"param": "rag_threshold", "current": "0.7", "new": str(round(random.uniform(0.5, 0.9), 1)), "line": 43},
        ],
        "memory_policy": [
            {"param": "memory_window", "current": "100", "new": str(random.randint(50, 200)), "line": 45},
            {"param": "memory_decay", "current": "0.95", "new": str(round(random.uniform(0.9, 0.99), 2)), "line": 46},
        ],
        "temperature": [
            {"param": "temperature", "current": "0.7", "new": str(round(random.uniform(0.3, 1.2), 1)), "line": 78},
            {"param": "temperature range", "current": "0.1, 0.3", "new": f"{round(random.uniform(0.05, 0.2), 2)}, {round(random.uniform(0.2, 0.4), 2)}", "line": 79},
        ],
        "sampling": [
            {"param": "top_k", "current": "40", "new": str(random.randint(20, 80)), "line": 99},
            {"param": "top_p", "current": "0.9", "new": str(round(random.uniform(0.7, 0.95), 2)), "line": 100},
        ],
        "web_search": [
            {"param": "web_enabled", "current": "False", "new": "True", "line": 48},
            {"param": "web_timeout", "current": "30", "new": str(random.randint(20, 60)), "line": 49},
        ],
        "fewshot": [
            {"param": "fewshot example", "current": "def reverse_string(s): return s[::-1]", "new": "def reverse_string(s): return ''.join(reversed(s))", "line": 26},
            {"param": "fewshot domain", "current": "code", "new": random.choice(["analysis", "debug", "design"]), "line": 92},
        ]
    }
    
    # Determine file-specific mappings
    if "config.py" in file_path:
        # Config file handles bandit, rag, memory, web_search parameters
        possible_areas = ["bandit", "rag", "memory_policy", "web_search"]
        area = random.choice([a for a in possible_areas if a in allowed_areas] or ["bandit"])
    elif "operators.py" in file_path:
        # Operators file handles operators, prompts, temperature, sampling, fewshot
        possible_areas = ["operators", "prompts", "temperature", "sampling", "fewshot"]
        area = random.choice([a for a in possible_areas if a in allowed_areas] or ["operators"])
    
    # Get change details for the selected area
    changes = area_changes.get(area, area_changes["operators"])
    change = random.choice(changes)
    
    # Extract context around the target line
    lines = file_content.split('\n')
    line_num = change["line"]
    
    # Adjust line number if it's beyond file length
    if line_num >= len(lines):
        line_num = min(len(lines) - 1, max(10, len(lines) // 2))
    
    start = max(0, line_num - 4)
    end = min(len(lines), line_num + 3)
    context_lines = lines[start:end]
    context = '\n'.join(f"{i+start+1}: {line}" for i, line in enumerate(context_lines))
    
    # Build a simple, clear prompt
    # Use raw string to avoid confusion with escaping
    prompt = f"""Generate a simple patch for {file_path}.

Current context around line {line_num}:
{context}

Task: Change {change['param']} from {change['current']} to {change['new']}

Generate ONLY a valid JSON object with exactly these 3 fields:
- "area": the modification area ("{area}")
- "rationale": brief reason (max 10 words)
- "diff": a valid unified diff patch

The diff MUST be a proper unified diff with:
- Header lines: --- a/filepath and +++ b/filepath
- Hunk header: @@ -start,count +start,count @@
- Context lines (unchanged): start with space
- Removed lines: start with -
- Added lines: start with +

Example of valid JSON response:
{{"area":"bandit","rationale":"Increase exploration parameter","diff":"--- a/app/config.py\\n+++ b/app/config.py\\n@@ -20,7 +20,7 @@\\n     # Bandit configuration\\n-    \\"ucb_c\\": float(os.getenv(\\"UCB_C\\", \\"2.0\\")),\\n+    \\"ucb_c\\": float(os.getenv(\\"UCB_C\\", \\"2.1\\")),\\n     \\"epsilon\\": float(os.getenv(\\"EPSILON\\", \\"0.6\\")),"}}

Generate the JSON response:"""
    
    return prompt