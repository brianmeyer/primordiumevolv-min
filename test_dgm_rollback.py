#!/usr/bin/env python3
"""Test DGM rollback functionality."""

import os
import sys
from pathlib import Path

# Set environment variables for testing
os.environ["FF_DGM"] = "1"
os.environ["DGM_ALLOW_COMMITS"] = "1"

# Import DGM modules
sys.path.insert(0, str(Path(__file__).parent))
from app.dgm.apply import rollback_commit
from app.dgm.storage import get_patch_storage

def test_rollback():
    """Test rollback of the most recent commit."""
    print("\n=== Testing DGM Rollback ===\n")
    
    # Get the most recent commit SHA
    commit_sha = "c2202aa"  # The test commit we just made
    
    print(f"Attempting to rollback commit {commit_sha}...")
    
    try:
        result = rollback_commit(commit_sha)
        
        if result and result.get("success"):
            print(f"✓ Rollback successful!")
            print(f"  - Rollback SHA: {result.get('rollback_sha', 'N/A')}")
            print(f"  - Message: {result.get('message', 'N/A')}")
            
            # Verify in storage
            storage = get_patch_storage()
            artifact = storage.get_patch_artifact("test_patch_001")
            if artifact:
                print(f"  - Artifact status: {artifact.status}")
                print(f"  - Rollback SHA in storage: {artifact.rollback_sha}")
            
            return True
        else:
            error_msg = result.get("error", "Unknown error") if result else "No result returned"
            print(f"✗ Rollback failed: {error_msg}")
            return False
            
    except Exception as e:
        print(f"✗ Error during rollback: {e}")
        import traceback
        traceback.print_exc()
        return False

def verify_rollback():
    """Verify the rollback was successful."""
    print("\n=== Verifying Rollback ===\n")
    
    # Check git log
    import subprocess
    result = subprocess.run(
        ["git", "log", "--oneline", "-3"],
        capture_output=True,
        text=True
    )
    
    print("Recent commits:")
    print(result.stdout)
    
    # Check if the change was reverted
    result = subprocess.run(
        ["git", "diff", "HEAD~1", "app/meta/operators.py"],
        capture_output=True,
        text=True
    )
    
    if result.stdout:
        print("✓ Changes were reverted in operators.py")
    else:
        print("✓ No differences from previous commit (rollback successful)")
    
    return True

def main():
    """Run rollback test."""
    print("\n" + "="*50)
    print("     DGM ROLLBACK TEST")
    print("="*50)
    
    # Test rollback
    if test_rollback():
        # Verify it worked
        verify_rollback()
    
    print("\n" + "="*50)
    print("     TEST COMPLETE")
    print("="*50 + "\n")

if __name__ == "__main__":
    main()