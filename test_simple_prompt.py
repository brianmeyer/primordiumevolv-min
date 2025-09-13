#!/usr/bin/env python3
"""
Test with a super simple prompt to establish baseline success
"""
import os
import sys
import json
import subprocess
import time
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.dgm.proposer import _route_model_call
from app.config import DGM_JUDGE_MODEL_POOL

SIMPLE_PROMPT = """Generate a simple patch to improve the UCB exploration parameter.

The current value is ucb_c=2.0 on line 23 of app/config.py.

Generate a JSON response with:
- area: "bandit"
- rationale: Brief explanation 
- diff: A unified diff patch

Example response:
{
  "area": "bandit", 
  "rationale": "Increase exploration by raising UCB constant",
  "diff": "--- a/app/config.py\\n+++ b/app/config.py\\n@@ -20,7 +20,7 @@\\n     \\"eps\\": float(os.getenv(\\"META_DEFAULT_EPS\\", \\"0.6\\")),\\n     \\"web_k\\": 3,\\n     # UCB Bandit Configuration\\n-    \\"ucb_c\\": float(os.getenv(\\"UCB_C\\", \\"2.0\\")),\\n+    \\"ucb_c\\": float(os.getenv(\\"UCB_C\\", \\"2.1\\")),\\n     \\"warm_start_min_pulls\\": int(os.getenv(\\"WARM_START_MIN_PULLS\\", \\"1\\")),\\n     \\"stratified_explore\\": os.getenv(\\"STRATIFIED_EXPLORE\\", \\"true\\").lower() == \\"true\\",\\n }"
}

Generate a valid JSON response:"""

def test_simple(model_id):
    """Test with simple prompt"""
    try:
        response, actual_model = _route_model_call(model_id, SIMPLE_PROMPT)
        
        # Try to parse as JSON
        try:
            parsed = json.loads(response)
            
            # Check fields
            if all(k in parsed for k in ['area', 'rationale', 'diff']):
                # Test if diff applies
                diff = parsed['diff'].replace('\\n', '\n')
                with open('/tmp/test.patch', 'w') as f:
                    f.write(diff)
                
                result = subprocess.run(
                    f"cd {os.getcwd()} && git apply --check /tmp/test.patch 2>&1",
                    shell=True,
                    capture_output=True,
                    text=True
                )
                
                if result.returncode == 0:
                    return True, "Success"
                else:
                    return False, f"Patch failed: {result.stdout[:50]}"
            else:
                missing = [k for k in ['area', 'rationale', 'diff'] if k not in parsed]
                return False, f"Missing fields: {missing}"
                
        except json.JSONDecodeError as e:
            return False, f"JSON parse error: {str(e)[:30]}"
            
    except Exception as e:
        return False, f"Exception: {str(e)[:50]}"

def main():
    os.environ['FF_DGM'] = '1'
    os.environ['DGM_USE_JUDGE_POOL'] = '0'
    
    # Test subset of models
    models = DGM_JUDGE_MODEL_POOL[:5]
    
    print("## Simple Prompt Test Results\n")
    print("| Model | Run 1 | Run 2 | Run 3 | Success Rate |")
    print("|-------|-------|-------|-------|--------------|")
    
    for model in models:
        results = []
        for run in range(3):
            success, reason = test_simple(model)
            results.append("✅" if success else "❌")
            time.sleep(1)
        
        success_count = results.count("✅")
        success_rate = f"{success_count}/3 ({success_count*100/3:.0f}%)"
        
        print(f"| {model} | {results[0]} | {results[1]} | {results[2]} | {success_rate} |")

if __name__ == "__main__":
    main()