#!/usr/bin/env python3
"""
Test the simplified patch enforcement directly
"""
import sys
import os
sys.path.insert(0, '/Users/brianmeyer/Desktop/primordiumevolv-min')

from app.dgm.simple_prompt import make_simple_prompt
from app.groq_client import chat_complete
import json

def test_simple_patch():
    """Test the full simple patch process"""
    
    # Test data - simulate a file snapshot
    test_snapshot = {
        'path': 'app/config.py',
        'content': """import os
from typing import Dict, Any

# DGM Configuration
FF_TRAJECTORY_LOG = os.getenv("FF_TRAJECTORY_LOG", "1") == "1"

# Basic settings
BASIC_SETTING = "test"
ANOTHER_SETTING = 42
"""
    }
    
    # Generate a simple prompt
    allowed_areas = ["bandit"]
    prompt = make_simple_prompt(allowed_areas, 100, [test_snapshot])
    
    print("Generated prompt:")
    print("=" * 50)
    print(prompt)
    print("=" * 50)
    
    try:
        # Test with groq API
        messages = [{"role": "user", "content": prompt}]
        response = chat_complete(messages, "llama-3.3-70b-versatile")
        
        print("Model response:")
        print(response)
        print("=" * 50)
        
        # Try to parse as JSON - handle markdown wrapping
        try:
            parsed = json.loads(response)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown blocks
            import re
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
                parsed = json.loads(json_str)
            else:
                # Try to find JSON object directly
                json_match = re.search(r'(\{[^{}]*"area"[^{}]*\})', response, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1)
                    parsed = json.loads(json_str)
                else:
                    print(f"Could not extract JSON from response")
                    return
        
        print("Successfully parsed JSON:")
        print(f"Area: {parsed.get('area')}")
        print(f"Rationale: {parsed.get('rationale')}")
        print(f"Diff present: {'diff' in parsed}")
        
        # Test the simplified extraction
        diff = parsed.get('diff', '')
        if not diff:
            print("ERROR: No diff field in response")
        else:
            print("SUCCESS: Got diff field")
            print("Diff content:")
            print(diff[:200] + "..." if len(diff) > 200 else diff)
            
    except Exception as e:
        print(f"API call failed: {e}")

if __name__ == "__main__":
    test_simple_patch()