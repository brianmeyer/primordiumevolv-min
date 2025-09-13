#!/usr/bin/env python3
"""
Test all models systematically to understand failure patterns
"""
import os
import sys
import json
import subprocess
import time
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.dgm.proposer import _gen_one
from app.config import DGM_JUDGE_MODEL_POOL

def test_model(model_id, area="bandit"):
    """Test a single model and return success/failure with reason"""
    try:
        # Generate proposal
        proposal = _gen_one(model_id, area)
        
        if not proposal:
            return False, "No response (None returned)"
        
        # Check if it's a MetaPatch object (success!)
        from app.dgm.types import MetaPatch
        if isinstance(proposal, MetaPatch):
            # It worked! The simple prompt generated a valid MetaPatch
            return True, "Success - valid MetaPatch generated"
        
        # Old dict-based check (shouldn't happen anymore)
        if isinstance(proposal, dict):
            if not all(k in proposal for k in ['area', 'rationale', 'diff']):
                missing = [k for k in ['area', 'rationale', 'diff'] if k not in proposal]
                return False, f"Missing fields: {missing}"
        
        # Test git apply
        diff = proposal.get('diff', '')
        if not diff:
            return False, "Empty diff"
            
        # Write diff to temp file and test
        with open('/tmp/test.patch', 'w') as f:
            f.write(diff)
        
        # Determine target file
        if area == "bandit":
            target = "app/config.py"
        else:
            target = "app/meta/operators.py"
            
        # Test with git apply
        result = subprocess.run(
            f"cd {os.getcwd()} && git apply --check /tmp/test.patch 2>&1",
            shell=True,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            # Extract error message
            error = result.stdout + result.stderr
            if "corrupt patch" in error:
                return False, "Corrupt patch format"
            elif "patch does not apply" in error:
                return False, "Patch doesn't apply cleanly"
            else:
                return False, f"Git apply failed: {error[:50]}"
        
        return True, "Success"
        
    except Exception as e:
        return False, f"Exception: {str(e)[:50]}"

def main():
    # Set environment
    os.environ['FF_DGM'] = '1'
    os.environ['DGM_USE_JUDGE_POOL'] = '0'
    os.environ['DGM_PROPOSALS'] = '1'
    
    # Models to test - using a subset for quick testing
    models = [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "groq/compound",
        "groq/compound-mini",
        "openai/gpt-oss-20b",
        "meta-llama/llama-4-scout-17b-16e-instruct"
    ]
    
    # Test each model 3 times
    results = {}
    for model in models:
        print(f"\nTesting {model}...")
        model_results = []
        
        for run in range(3):
            print(f"  Run {run+1}...", end="")
            success, reason = test_model(model)
            model_results.append((success, reason))
            print(" ✓" if success else f" ✗ ({reason})")
            time.sleep(1)  # Small delay between tests
            
        results[model] = model_results
    
    # Print markdown table
    print("\n\n## Model Test Results\n")
    print("| Model | Run 1 | Run 2 | Run 3 | Success Rate | Common Failure |")
    print("|-------|-------|-------|-------|--------------|----------------|")
    
    for model, runs in results.items():
        model_name = model.replace("groq:", "")
        
        # Format each run
        run_strs = []
        for success, reason in runs:
            if success:
                run_strs.append("✅")
            else:
                run_strs.append(f"❌")
        
        # Calculate success rate
        success_count = sum(1 for s, _ in runs if s)
        success_rate = f"{success_count}/3 ({success_count*100/3:.0f}%)"
        
        # Find most common failure
        failures = [reason for success, reason in runs if not success]
        if failures:
            # Get most common failure
            common_failure = max(set(failures), key=failures.count)
        else:
            common_failure = "N/A"
        
        print(f"| {model_name} | {run_strs[0]} | {run_strs[1]} | {run_strs[2]} | {success_rate} | {common_failure} |")
    
    # Print detailed failure reasons
    print("\n## Detailed Failure Reasons\n")
    for model, runs in results.items():
        model_name = model.replace("groq:", "")
        failures = [(i+1, reason) for i, (success, reason) in enumerate(runs) if not success]
        if failures:
            print(f"**{model_name}:**")
            for run_num, reason in failures:
                print(f"  - Run {run_num}: {reason}")
            print()

if __name__ == "__main__":
    main()