"""
DGM Smoke Patch - Guaranteed valid patch for end-to-end pipeline testing

Creates minimal, safe patches that are guaranteed to pass validation
to ensure at least one valid candidate in the proposal pipeline.
"""

import time
import logging
from typing import Dict, Any
from app.config import DGM_ALLOWED_AREAS

logger = logging.getLogger(__name__)


def make_smoke_patch() -> Dict[str, Any]:
    """
    Generate a known-good smoke patch for pipeline testing.
    
    Creates a minimal change that:
    - Is strictly within allowlist areas
    - Has minimal LOC delta (≤10 lines)
    - Passes ruff/pytest subset
    - Is completely safe and reversible
    
    Returns:
        Dict with area, notes, diff for a valid patch
    """
    # Generate smoke patch for ui_metrics area targeting app/ui/smoke_metrics.py
    smoke_diff = """diff --git a/app/ui/smoke_metrics.py b/app/ui/smoke_metrics.py
new file mode 100644
index 0000000..e69de29
--- /dev/null
+++ b/app/ui/smoke_metrics.py
@@ -0,0 +1,2 @@
+# DGM smoke metric (read-only; no runtime import)
+SMOKE_METRIC_TILE = {"id": "dgm_smoke", "label": "DGM Smoke", "value": 0}
"""
    
    return {
        "area": "ui_metrics",
        "notes": "Add DGM smoke patch validation file",
        "diff": smoke_diff
    }


def make_memory_ui_patch() -> Dict[str, Any]:
    """
    Alternative smoke patch that creates a simple UI metrics file.
    
    Returns:
        Dict with area, notes, diff for creating a minimal UI file
    """
    timestamp = int(time.time())
    
    # Create a minimal UI metrics file
    smoke_diff = f"""--- /dev/null
+++ b/app/ui/metrics.py
@@ -0,0 +1,12 @@
+\"\"\"
+Simple UI metrics module for DGM smoke testing.
+Generated at {timestamp} by DGM smoke patch system.
+\"\"\"
+
+def get_smoke_metrics():
+    \"\"\"Return basic smoke test metrics.\"\"\"
+    return {{
+        "smoke_test": True,
+        "timestamp": {timestamp},
+        "status": "active"
+    }}"""
    
    return {
        "area": "ui_metrics",
        "notes": f"Add smoke test UI metrics module (timestamp: {timestamp})",
        "diff": smoke_diff
    }


def make_bandit_smoke_patch() -> Dict[str, Any]:
    """
    Conservative smoke patch for bandit area.
    
    Makes a tiny epsilon adjustment that's guaranteed safe.
    
    Returns:
        Dict with area, notes, diff for epsilon tweak
    """
    # Very simple working diff - add comment after EVO_DEFAULTS dict
    smoke_diff = """--- a/app/config.py
+++ b/app/config.py
@@ -29,6 +29,7 @@
     "stratified_explore": os.getenv("STRATIFIED_EXPLORE", "true").lower() == "true",  # First pass diversity
 }
 
+# DGM smoke patch: bandit configuration validated
 # ---- Active Feature Flags ----
 FF_TRAJECTORY_LOG = os.getenv("FF_TRAJECTORY_LOG", "1") == "1"""
    
    return {
        "area": "bandit",
        "notes": "Add DGM smoke patch comment for bandit configuration testing",
        "diff": smoke_diff
    }


def get_smoke_patch_variants() -> list[Dict[str, Any]]:
    """
    Get all available smoke patch variants.
    
    Returns:
        List of smoke patch dictionaries
    """
    return [
        make_smoke_patch(),      # Primary: config comment
        make_bandit_smoke_patch(),  # Alternative: bandit comment
        make_memory_ui_patch()   # Fallback: create new file
    ]


def select_smoke_patch(preferred_area: str = "ui_metrics") -> Dict[str, Any]:
    """
    Select appropriate smoke patch based on preferences and safety.
    
    Args:
        preferred_area: Preferred area if available
        
    Returns:
        Selected smoke patch dict
    """
    # Use bandit smoke patch (modifies existing file) instead of creating new file
    # This avoids git apply issues with new file creation
    bandit_patch = make_bandit_smoke_patch()
    logger.info(f"Using bandit smoke patch for reliability: {bandit_patch['area']}")
    return bandit_patch


def validate_smoke_patch(patch_dict: Dict[str, Any]) -> tuple[bool, str]:
    """
    Validate that smoke patch meets safety requirements.
    
    Args:
        patch_dict: Smoke patch dictionary
        
    Returns:
        (is_valid, reason)
    """
    required_fields = ["area", "notes", "diff"]
    
    # Check required fields
    for field in required_fields:
        if field not in patch_dict:
            return False, f"Missing required field: {field}"
    
    # Check area is allowed
    area = patch_dict["area"]
    if area not in DGM_ALLOWED_AREAS:
        return False, f"Area {area} not in allowed areas: {DGM_ALLOWED_AREAS}"
    
    # Check diff format
    diff = patch_dict["diff"]
    if not diff.startswith("---") or "+++" not in diff:
        return False, "Diff does not appear to be unified diff format"
    
    # Check diff size (smoke patches should be tiny)
    lines = diff.split('\n')
    add_lines = sum(1 for line in lines if line.startswith('+') and not line.startswith('+++'))
    del_lines = sum(1 for line in lines if line.startswith('-') and not line.startswith('---'))
    loc_delta = add_lines + del_lines
    
    if loc_delta > 10:
        return False, f"Smoke patch too large: {loc_delta} LOC (max 10)"
    
    logger.info(f"Smoke patch validated: area={area}, loc_delta={loc_delta}")
    return True, "Valid smoke patch"