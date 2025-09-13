#!/usr/bin/env python3
"""
Test if generated patches are actually valid and apply correctly
"""
import os
import sys
import subprocess
import tempfile
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.dgm.proposer import _gen_one
from app.dgm.types import MetaPatch
from app.config import DGM_JUDGE_MODEL_POOL

def test_patch_quality(model_id, area="bandit"):
    """Test if a patch actually applies and is valid"""
    try:
        # Generate proposal
        proposal = _gen_one(model_id, area)
        
        if not proposal:
            return False, "No proposal generated", None
        
        if not isinstance(proposal, MetaPatch):
            return False, "Not a MetaPatch object", None
        
        # Get the diff from the MetaPatch
        diff = proposal.diff
        
        if not diff:
            return False, "Empty diff", None
        
        # Write diff to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.patch', delete=False) as f:
            f.write(diff)
            patch_file = f.name
        
        try:
            # Test if patch applies cleanly
            result = subprocess.run(
                f"cd {os.getcwd()} && git apply --check {patch_file}",
                shell=True,
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                error = (result.stdout + result.stderr)[:200]
                return False, f"Patch doesn't apply: {error}", diff
            
            # Actually apply the patch to test it
            result = subprocess.run(
                f"cd {os.getcwd()} && git apply {patch_file}",
                shell=True,
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                return False, "Patch apply failed", diff
            
            # Check what changed
            result = subprocess.run(
                "git diff --stat",
                shell=True,
                capture_output=True,
                text=True
            )
            
            changes = result.stdout.strip()
            
            # Revert the patch
            subprocess.run(
                f"cd {os.getcwd()} && git apply -R {patch_file}",
                shell=True,
                capture_output=True,
                text=True
            )
            
            # Analyze the patch
            lines = diff.split('\n')
            added = sum(1 for l in lines if l.startswith('+') and not l.startswith('+++'))
            removed = sum(1 for l in lines if l.startswith('-') and not l.startswith('---'))
            
            # Check if it's a minimal change (1 line changed)
            if added == 1 and removed == 1:
                return True, f"Good patch! Changed {changes}", diff
            else:
                return True, f"Valid but not minimal: +{added}/-{removed} lines", diff
                
        finally:
            os.unlink(patch_file)
            
    except Exception as e:
        return False, f"Exception: {str(e)}", None

def main():
    os.environ['FF_DGM'] = '1'
    os.environ['DGM_USE_JUDGE_POOL'] = '0'
    
    # Test a few models
    models = DGM_JUDGE_MODEL_POOL[:3]
    
    print("## Patch Quality Analysis\n")
    print("Testing if patches actually apply and are minimal...\n")
    
    for model in models:
        print(f"\n### {model}")
        print("-" * 50)
        
        # Test 3 patches
        for i in range(3):
            success, message, diff = test_patch_quality(model)
            
            if success:
                print(f"✅ Test {i+1}: {message}")
                if diff and "Good patch" in message:
                    # Show a snippet of the actual change
                    for line in diff.split('\n'):
                        if line.startswith('-') and not line.startswith('---'):
                            print(f"   OLD: {line}")
                        elif line.startswith('+') and not line.startswith('+++'):
                            print(f"   NEW: {line}")
            else:
                print(f"❌ Test {i+1}: {message}")
    
    # Also test if the patches make sensible changes
    print("\n## Sample Patch Analysis")
    print("Generating a patch and showing the actual change...")
    
    proposal = _gen_one(DGM_JUDGE_MODEL_POOL[0], "bandit")
    if proposal and isinstance(proposal, MetaPatch):
        print(f"\nArea: {proposal.area}")
        print(f"Notes: {proposal.notes}")
        print(f"LOC Delta: {proposal.loc_delta}")
        print("\nDiff preview:")
        for line in proposal.diff.split('\n')[:15]:
            print(f"  {line}")

if __name__ == "__main__":
    main()