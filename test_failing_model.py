#!/usr/bin/env python3
"""
Debug failing model by showing exact prompt and raw response
"""
import os
import sys
import json
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.groq_client import generate as groq_generate
from app.dgm.proposer import _gen_one, build_prompt

def test_failing_model_debug():
    """Debug a failing model with exact prompt and response"""
    
    # Set environment
    os.environ['FF_DGM'] = '1'
    os.environ['DGM_USE_JUDGE_POOL'] = '0'
    os.environ['DGM_PROPOSALS'] = '1'
    
    # Test with a failing model
    model_id = 'groq/compound-mini'
    
    print("=" * 80)
    print(f"DEBUGGING FAILING MODEL: {model_id}")
    print("=" * 80)
    
    # Get the exact prompt that would be sent
    prompt = build_prompt()
    
    print("\n" + "=" * 80)
    print("EXACT PROMPT BEING SENT:")
    print("=" * 80)
    print(prompt[:2000])  # First 2000 chars
    print("... [truncated] ...")
    print(prompt[-1000:])  # Last 1000 chars
    
    # Call the model directly  
    system = "You are a precise JSON generation system modifying system code."
    
    try:
        response, actual_model = groq_generate(
            prompt, 
            system, 
            {"model_id": model_id.replace('groq:', ''), "max_tokens": 8192}
        )
        
        print("\n" + "=" * 80)
        print("RAW RESPONSE FROM MODEL:")
        print("=" * 80)
        print(f"Model used: {actual_model}")
        print(f"Response length: {len(response)} chars")
        print("\n--- RAW RESPONSE START ---")
        print(response)
        print("--- RAW RESPONSE END ---")
        
        # Check if response ends abruptly
        if response and not response.rstrip().endswith('}'):
            print("\n⚠️ WARNING: Response appears to be truncated (doesn't end with '}')")
            
        # Try to parse
        print("\n" + "=" * 80)
        print("PARSE ATTEMPT:")
        print("=" * 80)
        try:
            parsed = json.loads(response)
            print("✅ Successfully parsed as JSON!")
            print(f"Keys present: {list(parsed.keys())}")
            
            # Check for expected keys
            expected_keys = ['area', 'goal_tag', 'rationale', 'diff_lines']
            missing_keys = [k for k in expected_keys if k not in parsed]
            if missing_keys:
                print(f"❌ Missing expected keys: {missing_keys}")
                
            # Check if using old format
            if 'diff' in parsed and 'diff_lines' not in parsed:
                print("⚠️ Model is using OLD 'diff' string format instead of NEW 'diff_lines' array format")
                
        except json.JSONDecodeError as e:
            print(f"❌ JSON parse failed: {e}")
            # Try to find where it fails
            for i in range(len(response), 0, -100):
                try:
                    json.loads(response[:i])
                except:
                    continue
                else:
                    print(f"✓ JSON is valid up to character {i}")
                    print(f"Last valid chunk ends with: ...{response[i-50:i]}")
                    print(f"Invalid part starts with: {response[i:i+50]}...")
                    break
                    
    except Exception as e:
        print(f"\n❌ ERROR calling model: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_failing_model_debug()