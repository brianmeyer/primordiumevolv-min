#!/usr/bin/env python3
"""Test DGM commit and rollback functionality."""

import os
import sys
import json
import time
import requests
from pathlib import Path

# Set environment variables for testing
os.environ["FF_DGM"] = "1"
os.environ["DGM_ALLOW_COMMITS"] = "1"
os.environ["DGM_TEST_BEFORE_COMMIT"] = "0"  # Skip tests for this test

# Import DGM modules
sys.path.insert(0, str(Path(__file__).parent))
from app.dgm.types import MetaPatch
from app.dgm.eval import ShadowEvalResult
from app.dgm.storage import get_patch_storage
from app.dgm.apply import commit_patch, rollback_commit

def create_test_patch():
    """Create a safe test patch that will pass guards."""
    # Create a valid unified diff patch - add comment
    patch = MetaPatch(
        id="test_patch_001",
        area="bandit",
        origin="test_script",
        notes="Test patch: Add clarifying comment",
        diff="""--- a/app/meta/operators.py
+++ b/app/meta/operators.py
@@ -95,6 +95,7 @@ def apply_operator(plan, operator_name):
     elif operator_name == "toggle_web":
         plan["use_web"] = not plan["use_web"]
         
+    # Adjust top_k sampling parameter
     elif operator_name == "raise_top_k":
         current_k = plan["params"].get("top_k", 40)
         plan["params"]["top_k"] = min(100, current_k + random.randint(5, 15))
""",
        loc_delta=1
    )
    return patch

def create_mock_shadow_result(patch_id):
    """Create a mock shadow result that passes all guards."""
    result = ShadowEvalResult(
        patch_id=patch_id,
        status="completed",
        avg_reward_before=0.70,
        avg_reward_after=0.75,  # +0.05 improvement
        error_rate_before=0.05,
        error_rate_after=0.04,   # Slight improvement
        latency_p95_before=500.0,
        latency_p95_after=480.0,  # 20ms improvement
        tests_run=10,
        baseline_samples=3,
        execution_time_ms=1500
    )
    # Calculate deltas
    result.reward_delta = result.avg_reward_after - result.avg_reward_before
    result.error_rate_delta = result.error_rate_after - result.error_rate_before
    result.latency_p95_delta = result.latency_p95_after - result.latency_p95_before
    return result

def test_commit():
    """Test patch commit functionality."""
    print("\n=== Testing DGM Commit ===\n")
    
    # Create test patch
    patch = create_test_patch()
    print(f"✓ Created test patch: {patch.id}")
    
    # Create mock shadow result
    shadow_result = create_mock_shadow_result(patch.id)
    print(f"✓ Created shadow result: reward_delta={shadow_result.reward_delta:+.3f}")
    
    # Attempt to commit the patch
    print("\nAttempting to commit patch...")
    try:
        result = commit_patch(patch, shadow_result)
        
        if result and result.get("success"):
            print(f"✓ Patch committed successfully!")
            print(f"  - Commit SHA: {result.get('commit_sha', 'N/A')}")
            print(f"  - Artifact path: {result.get('artifact_path', 'N/A')}")
            print(f"  - Message: {result.get('message', 'N/A')}")
            return result.get("commit_sha")
        else:
            error_msg = result.get("error", "Unknown error") if result else "No result returned"
            print(f"✗ Commit failed: {error_msg}")
            return None
            
    except Exception as e:
        print(f"✗ Error during commit: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_rollback(commit_sha):
    """Test patch rollback functionality."""
    print("\n=== Testing DGM Rollback ===\n")
    
    if not commit_sha:
        print("✗ No commit SHA to rollback")
        return False
    
    print(f"Attempting to rollback commit {commit_sha[:8]}...")
    try:
        result = rollback_commit(commit_sha)
        
        if result and result.get("success"):
            print(f"✓ Rollback successful!")
            print(f"  - Rollback SHA: {result.get('rollback_sha', 'N/A')}")
            print(f"  - Message: {result.get('message', 'N/A')}")
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

def test_storage():
    """Test artifact storage."""
    print("\n=== Testing Artifact Storage ===\n")
    
    storage = get_patch_storage()
    
    # Check storage stats
    stats = storage.get_storage_stats()
    print(f"Storage stats:")
    print(f"  - Total patches: {stats['total_patches']}")
    print(f"  - Storage path: {stats['storage_path']}")
    print(f"  - Total size: {stats['total_size_mb']} MB")
    
    # List recent commits
    history = storage.get_commit_history(limit=5)
    if history:
        print(f"\nRecent commits:")
        for commit in history:
            print(f"  - {commit['patch_id'][:8]} | {commit['area']} | "
                  f"reward_delta={commit.get('reward_delta', 'N/A')} | "
                  f"status={commit['status']}")
    else:
        print("\nNo commits found in storage")
    
    return True

def test_api_endpoints():
    """Test the API endpoints (requires server running)."""
    print("\n=== Testing API Endpoints ===\n")
    
    base_url = "http://localhost:8000"
    
    # Check if server is running
    try:
        response = requests.get(f"{base_url}/api/health")
        if response.status_code != 200:
            print("✗ Server not responding at localhost:8000")
            return False
    except:
        print("✗ Server not running - skipping API tests")
        return False
    
    print("✓ Server is running")
    
    # Test /api/dgm/propose endpoint
    print("\nTesting /api/dgm/propose...")
    try:
        response = requests.post(
            f"{base_url}/api/dgm/propose",
            params={"proposals": 2, "canary_runs": 5}
        )
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Propose endpoint working - {data['proposals_generated']} proposals generated")
        else:
            print(f"✗ Propose failed: {response.status_code}")
    except Exception as e:
        print(f"✗ Error calling propose: {e}")
    
    return True

def main():
    """Run all tests."""
    print("\n" + "="*50)
    print("     DGM COMMIT/ROLLBACK TEST SUITE")
    print("="*50)
    
    # Test commit
    commit_sha = test_commit()
    
    # Test rollback if commit succeeded
    if commit_sha:
        time.sleep(1)  # Brief pause
        test_rollback(commit_sha)
    
    # Test storage
    test_storage()
    
    # Test API endpoints (optional)
    test_api_endpoints()
    
    print("\n" + "="*50)
    print("     TEST SUITE COMPLETE")
    print("="*50 + "\n")

if __name__ == "__main__":
    main()