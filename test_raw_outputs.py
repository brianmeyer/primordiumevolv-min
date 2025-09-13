#!/usr/bin/env python3
"""
Show raw outputs from each model for debugging
"""
import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.dgm.proposer import generate_single
from app.groq_client import generate as groq_generate
from app.quality_judge import JUDGE_MODELS

def test_all_models_raw():
    """Test each model and show raw output"""
    
    # Set environment
    os.environ['FF_DGM'] = '1'
    os.environ['DGM_USE_JUDGE_POOL'] = '0'  # Don't use pool, test individually
    
    print("=" * 80)
    print("RAW MODEL OUTPUTS FOR DGM PROPOSAL GENERATION")
    print("=" * 80)
    
    # Test each model in JUDGE_MODELS
    for model_id in JUDGE_MODELS:
        print(f"\n\n{'=' * 80}")
        print(f"MODEL: {model_id}")
        print("=" * 80)
        
        # Create a simple test prompt
        test_prompt = """You are modifying the PrimordiumEvolv system. Generate ONE minimal patch.

TASK CONTEXT
- File path: app/config.py
- Area: bandit
- Intent:
  - goal_tag: exploration
  - goal_note: slightly increase ucb_c
- Allowed parameter edits (exactly one may be changed):
  ucb_c: current=2.0, allowed_delta=±0.1, type=float, line=23

STRICT OUTPUT CONTRACT
1) Output MUST be a SINGLE JSON object with EXACTLY these keys and no others:
   "area" (string), "goal_tag" (string), "rationale" (string), "diff" (string)
2) The JSON MUST appear ALONE: no markdown fences, no explanations.
3) All JSON strings MUST be escaped:
   - No raw newlines; use \\n for line breaks.
   - Escape backslashes as \\\\ and quotes as \\".

OUTPUT TEMPLATE (fill and output exactly one object):
{"area":"bandit","goal_tag":"exploration","rationale":"<≤10 words>","diff":"--- a/app/config.py\\n+++ b/app/config.py\\n@@ -20,7 +20,7 @@\\n     \\"web_k\\": 3,\\n     # UCB Bandit Configuration\\n     \\"strategy\\": os.getenv(\\"BANDIT_STRATEGY\\", \\"ucb\\"),\\n-    \\"ucb_c\\": float(os.getenv(\\"UCB_C\\", \\"2.0\\")),\\n+    \\"ucb_c\\": float(os.getenv(\\"UCB_C\\", \\"2.1\\")),\\n     \\"warm_start_min_pulls\\": int(os.getenv(\\"WARM_START_MIN_PULLS\\", \\"1\\")),\\n     \\"stratified_explore\\": os.getenv(\\"STRATIFIED_EXPLORE\\", \\"true\\").lower() == \\"true\\","}"""

        system = "You are a precise code generation system. Output only valid JSON."
        
        try:
            # Skip non-Groq models
            if not model_id.startswith('groq:') and '/' not in model_id:
                print(f"SKIPPING (not a Groq model): {model_id}")
                continue
                
            # Call the model directly
            response, actual_model = groq_generate(
                test_prompt, 
                system, 
                {"model_id": model_id.replace('groq:', ''), "max_tokens": 8192}
            )
            
            print(f"ACTUAL MODEL USED: {actual_model}")
            print(f"RESPONSE LENGTH: {len(response)} chars")
            print("\n--- RAW RESPONSE START ---")
            print(response)
            print("--- RAW RESPONSE END ---")
            
            # Show the response with visible escape sequences
            print("\n--- RESPONSE WITH VISIBLE ESCAPES ---")
            visible = response.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
            print(visible)
            print("--- END VISIBLE ESCAPES ---")
            
            # Try to parse and show result
            print("\n--- PARSE ATTEMPT ---")
            try:
                import json
                parsed = json.loads(response)
                print("✅ Successfully parsed as JSON!")
                print(f"  Keys: {list(parsed.keys())}")
                print(f"  Area: {parsed.get('area', 'MISSING')}")
                print(f"  Goal tag: {parsed.get('goal_tag', 'MISSING')}")
                print(f"  Rationale: {parsed.get('rationale', 'MISSING')}")
                print(f"  Diff present: {'diff' in parsed}")
                if 'diff' in parsed:
                    diff_len = len(parsed['diff'])
                    print(f"  Diff length: {diff_len} chars")
                    # Check if diff ends properly
                    if not parsed['diff'].endswith('"'):
                        print(f"  ⚠️ WARNING: Diff may be truncated (doesn't end with expected pattern)")
            except json.JSONDecodeError as e:
                print(f"❌ JSON parse failed: {e}")
            print("--- END PARSE ATTEMPT ---")
            
        except Exception as e:
            print(f"ERROR calling model: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n\n" + "=" * 80)
    print("END OF RAW MODEL OUTPUTS")
    print("=" * 80)

if __name__ == "__main__":
    test_all_models_raw()