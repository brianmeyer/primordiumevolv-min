#!/usr/bin/env python3
"""Test script to see what models are actually returning."""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.dgm.proposer import make_prompt, _route_model_call, _parse_response, DGM_ALLOWED_AREAS
import logging
import json

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def test_model_response():
    """Test what a model actually returns."""
    
    # Create a simple prompt
    prompt = make_prompt(DGM_ALLOWED_AREAS, 20)
    
    # Show the prompt
    print("=" * 80)
    print("PROMPT BEING SENT:")
    print("=" * 80)
    print(prompt[:2000])  # First 2000 chars
    print("..." if len(prompt) > 2000 else "")
    print("=" * 80)
    
    # Try with a specific model
    model_id = "groq/compound-mini"
    
    try:
        # Get raw response
        response, actual_id = _route_model_call(model_id, prompt)
        
        print(f"\nMODEL USED: {actual_id}")
        print("=" * 80)
        print("RAW RESPONSE:")
        print("=" * 80)
        print(f"Type: {type(response)}")
        print(f"Length: {len(response) if response else 0}")
        print("Content:")
        print(response if response else "None")
        print("=" * 80)
        
        # Try to parse it
        parsed = _parse_response(response, model_id)
        print("\nPARSED RESULT:")
        print("=" * 80)
        if parsed:
            print(json.dumps(parsed, indent=2))
        else:
            print("Failed to parse")
        print("=" * 80)
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_model_response()