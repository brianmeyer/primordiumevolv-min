#!/usr/bin/env python3
"""
Debug test for DGM to capture raw responses and understand failures
"""
import os
import sys
import json
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.dgm.proposer import generate_single
from app.groq_client import generate as groq_generate

def test_single_model_raw():
    """Test a single model to see raw response"""
    
    # Test with one of the "good" models
    test_model = "groq/compound"
    
    print(f"Testing model: {test_model}")
    print("=" * 80)
    
    # Create the prompt for bandit area
    prompt = """You are a Darwin Gödel Machine (DGM) proposer. Generate EXACTLY ONE concrete patch to improve the system.

CRITICAL REQUIREMENTS:
1. Output ONLY valid JSON with these exact fields: area, rationale, diff
2. The diff MUST be a valid unified diff format that can be applied with 'git apply'
3. Start diff headers with --- a/ and +++ b/ (with the a/ and b/ prefixes)
4. Include proper @@ line markers
5. NO markdown, NO explanations, NO thinking tags, JUST the JSON

Target area: bandit (Multi-armed bandit algorithms and parameters)

Files you can modify for bandit:
- app/meta/runner.py (bandit implementation)

Example of CORRECT output format:
{"area": "bandit", "rationale": "Increase exploration rate", "diff": "--- a/app/meta/runner.py\n+++ b/app/meta/runner.py\n@@ -50,7 +50,7 @@\n     def select_operator(self):\n-        epsilon = 0.3\n+        epsilon = 0.4\n         if random.random() < epsilon:"}

Generate ONE improvement for the bandit area:"""

    system = "You are a precise code generation system. Output only valid JSON."
    
    # Call the model directly
    try:
        response, model_used = groq_generate(prompt, system, {"model_id": test_model})
        print(f"\nModel used: {model_used}")
        print(f"\nRaw response length: {len(response)} chars")
        print(f"\nRaw response (first 500 chars):")
        print(response[:500])
        print(f"\n\nFull raw response:")
        print(response)
        
        # Try to parse it
        print("\n" + "=" * 80)
        print("Attempting to parse response...")
        try:
            parsed = json.loads(response)
            print("✅ Successfully parsed JSON!")
            print(f"  Area: {parsed.get('area', 'MISSING')}")
            print(f"  Rationale: {parsed.get('rationale', 'MISSING')[:100]}")
            
            diff = parsed.get('diff', '')
            if diff:
                print(f"  Diff present: {len(diff)} chars")
                print("  Diff preview (first 200 chars):")
                print("  " + diff[:200].replace('\n', '\n  '))
                
                # Test if diff would apply
                import tempfile
                import subprocess
                
                with tempfile.NamedTemporaryFile(mode='w', suffix='.patch', delete=False) as f:
                    f.write(diff)
                    patch_file = f.name
                
                result = subprocess.run(
                    ['git', 'apply', '--check', patch_file],
                    capture_output=True,
                    text=True,
                    cwd=os.path.dirname(os.path.abspath(__file__))
                )
                
                os.unlink(patch_file)
                
                if result.returncode == 0:
                    print("  ✅ Diff would apply cleanly!")
                else:
                    print(f"  ❌ Diff would NOT apply: {result.stderr}")
            else:
                print("  ❌ No diff in response!")
                
        except json.JSONDecodeError as e:
            print(f"❌ Failed to parse JSON: {e}")
            
    except Exception as e:
        print(f"❌ Error calling model: {e}")

def test_with_proposer():
    """Test using the actual proposer function"""
    print("\n" + "=" * 80)
    print("Testing with actual proposer function...")
    print("=" * 80)
    
    # Test with a single good model
    os.environ['DGM_USE_JUDGE_POOL'] = '0'  # Use default model
    
    patch = generate_single("bandit")
    
    if patch:
        print(f"✅ Got patch from proposer!")
        print(f"  Model: {patch.origin}")
        print(f"  Area: {patch.area}")
        print(f"  Rationale: {patch.notes[:100] if patch.notes else 'N/A'}")
        print(f"  Valid: {patch.is_valid()}")
        if patch.diff:
            print(f"  Diff preview:")
            for line in patch.diff.split('\n')[:10]:
                print(f"    {line}")
    else:
        print("❌ No patch returned from proposer")

if __name__ == "__main__":
    # Set environment
    os.environ['FF_DGM'] = '1'
    
    print("DGM Debug Test")
    print("=" * 80)
    
    # Test raw response first
    test_single_model_raw()
    
    # Then test with proposer
    test_with_proposer()