#!/usr/bin/env python3
"""
Test patch enforcer directly with problematic model outputs
"""
import os
import sys
import json
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.dgm.patch_enforcer import enforce_and_sanitize, PatchFormatError

# Test cases: actual failing outputs from models
test_cases = [
    {
        "name": "truncated_json",
        "model": "meta-llama/llama-4-scout-17b-16e-instruct",
        "raw": '{"area":"bandit","goal_tag":"exploration","rationale":"toggle stratified explore","diff_lines":["--- a/app/config.py","+++ b/app/config.py","@@ -19,6 +19,7 @@","OP_GROUPS = {","\\"SEAL\\": [\\"change_system\\", \\"change_nudge\\", \\"raise_temp\\", \\"lower_temp\\", \\"add_fewshot\\", \\"inject_memory\\", \\"inject_rag\\"]","\\"DEFAULT_OPERATORS\\": OP_GROUPS[\\"SEAL\\"] + OP_GROUPS[\\"WEB\\"] + OP_GROUPS[\\"SAMPLING\\"].","EVO_DEFAULTS = {","  \\"n\\": int(os.getenv(\\"META_DEFAULT_N\\", \\"16\\")), # Number of evolution iterati',
        "file_path": "app/config.py"
    },
    {
        "name": "old_diff_string_format",
        "model": "groq/compound-mini",
        "raw": '{"area":"bandit","goal_tag":"exploration","rationale":"increase exploration","diff":"--- a/app/config.py\\n+++ b/app/config.py\\n@@ -23,7 +23,7 @@\\n     \\"ucb_c\\": float(os.getenv(\\"UCB_C\\", \\"2.0\\")),\\n-    \\"warm_start_min_pulls\\": int(os.getenv(\\"WARM_START_MIN_PULLS\\", \\"1\\")),\\n+    \\"warm_start_min_pulls\\": int(os.getenv(\\"WARM_START_MIN_PULLS\\", \\"2\\")),\\n     \\"stratified_explore\\": os.getenv(\\"STRATIFIED_EXPLORE\\", \\"true\\").lower() == \\"true\\",\\n"}',
        "file_path": "app/config.py"
    },
    {
        "name": "diff_with_unescaped_newlines",
        "model": "test_model",
        "raw": '''{"area":"operators","goal_tag":"temperature","rationale":"adjust temperature range","diff":"--- a/app/meta/operators.py
+++ b/app/meta/operators.py
@@ -76,7 +76,7 @@
         
     elif operator_name == \\"raise_temp\\":
         current_temp = plan[\\"params\\"].get(\\"temperature\\", 0.7)
-        plan[\\"params\\"][\\"temperature\\"] = min(1.5, current_temp + random.uniform(0.1, 0.3))
+        plan[\\"params\\"][\\"temperature\\"] = min(1.5, current_temp + random.uniform(0.1, 0.2))
         
     elif operator_name == \\"lower_temp\\":"}''',
        "file_path": "app/meta/operators.py"
    }
]

def test_enforcer():
    """Test the patch enforcer with various problematic outputs"""
    print("Testing Patch Enforcer")
    print("=" * 80)
    
    # Read actual file content for context
    file_texts = {}
    for path in ["app/config.py", "app/meta/operators.py"]:
        try:
            with open(path, 'r') as f:
                file_texts[path] = f.read()
        except:
            file_texts[path] = ""
    
    results = []
    for test in test_cases:
        print(f"\nTest: {test['name']}")
        print(f"Model: {test['model']}")
        print("-" * 40)
        
        try:
            # Try to enforce and sanitize
            diff_lines = enforce_and_sanitize(
                test['raw'], 
                test['file_path'],
                file_texts.get(test['file_path'], "")
            )
            
            print("✅ Successfully enforced!")
            print(f"   Output lines: {len(diff_lines)}")
            
            # Show first few lines
            for i, line in enumerate(diff_lines[:5]):
                print(f"   Line {i}: {repr(line)}")
            
            # Try to reconstruct diff
            diff_str = '\n'.join(diff_lines)
            print(f"   Diff length: {len(diff_str)} chars")
            
            # Validate it's a proper diff
            if diff_str.startswith("--- a/") and "+++ b/" in diff_str and "@@ " in diff_str:
                print("   ✓ Valid diff structure")
                results.append((test['name'], True, None))
            else:
                print("   ✗ Invalid diff structure")
                results.append((test['name'], False, "Invalid structure"))
                
        except PatchFormatError as e:
            print(f"❌ Patch format error: {e}")
            results.append((test['name'], False, str(e)))
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            results.append((test['name'], False, str(e)))
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY:")
    success = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"  Success: {success}/{total} ({100*success/total:.1f}%)")
    
    if success < total:
        print("\n  Failed tests:")
        for name, ok, err in results:
            if not ok:
                print(f"    - {name}: {err}")

if __name__ == "__main__":
    test_enforcer()