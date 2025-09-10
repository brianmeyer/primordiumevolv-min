#!/usr/bin/env python3
"""Test DGM canary mode with auto-rollback."""

import os
import sys
import json
import time
import asyncio
from pathlib import Path

# Set environment variables
os.environ["FF_DGM"] = "1"
os.environ["DGM_ALLOW_COMMITS"] = "0"  # Canary doesn't need commits

sys.path.insert(0, str(Path(__file__).parent))

from app.dgm.types import MetaPatch
from app.dgm.canary_state import get_canary_manager

def create_test_patches():
    """Create test patches - one safe, one that will violate guards."""
    
    # Safe patch
    safe_patch = MetaPatch(
        id="canary_safe_001",
        area="prompts",
        origin="test",
        notes="Safe patch: Add helpful comment",
        diff="""--- a/prompts/code_gen.md
+++ b/prompts/code_gen.md
@@ -5,6 +5,7 @@
 
 ## Guidelines
 - Write clear, maintainable code
+- Document complex logic
 - Consider edge cases
 - Follow best practices
""",
        loc_delta=1
    )
    
    # Dangerous patch (will cause errors)
    dangerous_patch = MetaPatch(
        id="canary_danger_001",
        area="bandit",
        origin="test",
        notes="Dangerous patch: Break epsilon logic",
        diff="""--- a/app/config.py
+++ b/app/config.py
@@ -19,7 +19,7 @@
     "memory_k": 3,
     "rag_k": 3,
-    "eps": float(os.getenv("META_DEFAULT_EPS", "0.6")),
+    "eps": float(os.getenv("META_DEFAULT_EPS", "10.0")),  # BROKEN!
     "web_k": 3,
""",
        loc_delta=0
    )
    
    return safe_patch, dangerous_patch

def test_canary_manager():
    """Test canary manager functionality."""
    print("\n=== Testing Canary Manager ===\n")
    
    manager = get_canary_manager()
    
    # Start a canary
    canary = manager.start_canary(
        patch_id="test_patch_001",
        traffic_share=0.2,
        target_runs=10
    )
    
    print(f"Started canary: {canary.patch_id}")
    print(f"  Traffic share: {canary.traffic_share}")
    print(f"  Target runs: {canary.target_runs}")
    
    # Simulate some requests
    for i in range(20):
        use_canary, patch_id = manager.should_use_canary()
        
        if use_canary:
            print(f"  Request {i+1}: Using canary")
            manager.record_request(patch_id, error=False, latency_ms=100, reward=0.8)
        else:
            print(f"  Request {i+1}: Using baseline")
            manager.record_request(None, error=False, latency_ms=90, reward=0.75)
    
    # Check final metrics
    canary = manager.get_canary("test_patch_001")
    metrics = canary.metrics.to_dict()
    
    print(f"\nCanary Results:")
    print(f"  Total requests: {metrics['total_requests']}")
    print(f"  Canary requests: {metrics['canary_requests']}")
    print(f"  Canary error rate: {metrics['canary_error_rate']:.2%}")
    print(f"  Reward delta: {metrics['reward_delta']:.3f}")
    print(f"  Status: {canary.status}")

def test_guard_violations():
    """Test guard violation detection."""
    print("\n=== Testing Guard Violations ===\n")
    
    manager = get_canary_manager()
    
    # Start canary with low threshold
    canary = manager.start_canary(
        patch_id="guard_test_001",
        traffic_share=1.0,  # All traffic
        target_runs=10
    )
    
    # Simulate requests with increasing errors
    for i in range(10):
        error = i >= 5  # 50% error rate after 5 requests
        manager.record_request(
            "guard_test_001",
            error=error,
            latency_ms=100 + (i * 50),  # Increasing latency
            reward=0.5 - (i * 0.05)  # Decreasing reward
        )
        
        # Check guards
        violation = manager.check_guards(
            "guard_test_001",
            {"error_rate_max": 0.15, "latency_p95_regression": 200, "reward_delta_min": -0.1}
        )
        
        if violation:
            print(f"  Request {i+1}: GUARD VIOLATION - {violation}")
            manager.rollback_canary("guard_test_001", violation)
            break
        else:
            print(f"  Request {i+1}: OK")
    
    canary = manager.get_canary("guard_test_001")
    print(f"\nFinal status: {canary.status}")
    if canary.rollback_reason:
        print(f"Rollback reason: {canary.rollback_reason}")

async def test_canary_api():
    """Test canary API endpoint."""
    print("\n=== Testing Canary API ===\n")
    
    import aiohttp
    
    safe_patch, _ = create_test_patches()
    
    # Test API
    async with aiohttp.ClientSession() as session:
        url = "http://localhost:8000/api/dgm/canary"
        
        # Start canary via API
        params = {
            "patch_id": safe_patch.id,
            "traffic_share": 0.1
        }
        
        payload = {
            "patch": {
                "area": safe_patch.area,
                "origin": safe_patch.origin,
                "notes": safe_patch.notes,
                "diff": safe_patch.diff,
                "loc_delta": safe_patch.loc_delta
            }
        }
        
        try:
            async with session.post(url, params=params, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    print(f"Canary API response: {json.dumps(data, indent=2)}")
                else:
                    print(f"API error: {resp.status}")
                    text = await resp.text()
                    print(text)
        except Exception as e:
            print(f"API call failed: {e}")
            print("(Server may not be running)")

def main():
    """Run all canary tests."""
    print("\n" + "="*50)
    print("     DGM CANARY MODE TEST SUITE")
    print("="*50)
    
    # Test canary manager
    test_canary_manager()
    
    # Test guard violations
    test_guard_violations()
    
    # Test API (requires server)
    try:
        asyncio.run(test_canary_api())
    except Exception as e:
        print(f"\nAPI test skipped: {e}")
    
    print("\n" + "="*50)
    print("     TEST COMPLETE")
    print("="*50 + "\n")

if __name__ == "__main__":
    main()