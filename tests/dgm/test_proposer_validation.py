"""
Test DGM proposer validation enhancements for Stage-2/3.

Tests the robust JSON parsing and validation to eliminate "area":"unknown".
"""

import pytest
import json
from unittest.mock import patch, MagicMock
from app.dgm.proposer import (
    _normalize_area, _infer_area_from_diff, _is_unified_diff, 
    _diff_touches_only_allowlist, _parse_response, make_prompt
)
from app.config import DGM_ALLOWED_AREAS


class TestAreaNormalization:
    """Test area normalization and inference functionality."""
    
    def test_direct_area_matches(self):
        """Test direct matches with allowed areas."""
        for area in DGM_ALLOWED_AREAS:
            assert _normalize_area(area) == area
            assert _normalize_area(area.upper()) == area  # Case insensitive
            assert _normalize_area(f"  {area}  ") == area  # Strip whitespace
    
    def test_area_aliases(self):
        """Test area alias mapping."""
        test_cases = [
            ("prompt", "prompts"),
            ("epsilon", "bandit"), 
            ("bandit_strategy", "bandit"),
            ("asi", "asi_lite"),
            ("asi_architecture", "asi_lite"),
            ("retriever", "rag"),
            ("memory", "memory_policy"),
            ("ui", "ui_metrics"),
            ("dashboard", "ui_metrics")
        ]
        
        for alias, expected in test_cases:
            if expected in DGM_ALLOWED_AREAS:
                assert _normalize_area(alias) == expected
    
    def test_invalid_areas(self):
        """Test invalid area handling."""
        invalid_areas = ["invalid", "unknown", "", None, "database", "security"]
        
        for invalid in invalid_areas:
            assert _normalize_area(invalid) is None
    
    def test_area_inference_from_diff(self):
        """Test area inference from diff file paths."""
        test_cases = [
            # Bandit area
            ("--- a/app/config.py\n+++ b/app/config.py\n@@ -1 +1 @@\n-old\n+new", "bandit"),
            ("--- a/app/meta/bandit.py\n+++ b/app/meta/bandit.py\n", "bandit"),
            
            # Prompts area 
            ("--- a/prompts/system.md\n+++ b/prompts/system.md\n", "prompts"),
            ("--- a/README.md\n+++ b/README.md\n", "prompts"),
            
            # ASI Lite area
            ("--- a/app/meta/asi_arch.py\n+++ b/app/meta/asi_arch.py\n", "asi_lite"),
            
            # RAG area
            ("--- a/app/rag/retriever.py\n+++ b/app/rag/retriever.py\n", "rag"),
            ("--- a/app/tools/rag.py\n+++ b/app/tools/rag.py\n", "rag"),
            
            # Memory policy area
            ("--- a/app/memory/store.py\n+++ b/app/memory/store.py\n", "memory_policy"),
            
            # UI metrics area
            ("--- a/app/ui/panels/main.py\n+++ b/app/ui/panels/main.py\n", "ui_metrics"),
            ("--- a/app/static/style.css\n+++ b/app/static/style.css\n", "ui_metrics"),
            ("--- a/templates/index.html\n+++ b/templates/index.html\n", "ui_metrics")
        ]
        
        for diff, expected_area in test_cases:
            if expected_area in DGM_ALLOWED_AREAS:
                inferred = _infer_area_from_diff(diff)
                assert inferred == expected_area, f"Failed to infer {expected_area} from diff: {diff[:50]}..."
    
    def test_area_inference_invalid_paths(self):
        """Test area inference with invalid or unrecognized paths."""
        invalid_diffs = [
            "--- a/some/random/file.py\n+++ b/some/random/file.py\n",
            "--- a/database/schema.sql\n+++ b/database/schema.sql\n",
            "invalid diff format",
            ""
        ]
        
        for diff in invalid_diffs:
            assert _infer_area_from_diff(diff) is None


class TestDiffValidation:
    """Test unified diff format validation."""
    
    def test_valid_unified_diffs(self):
        """Test recognition of valid unified diff formats."""
        valid_diffs = [
            # Standard unified diff
            """--- a/file.py
+++ b/file.py
@@ -1,3 +1,3 @@
 line1
-old line
+new line
 line3""",
            
            # Diff with context
            """--- a/config.py
+++ b/config.py
@@ -10,7 +10,7 @@
     "param1": "value1",
     "param2": "value2", 
-    "eps": 0.6,
+    "eps": 0.62,
     "param3": "value3"
""",
            
            # Multiple hunks
            """--- a/test.py
+++ b/test.py
@@ -1,2 +1,2 @@
-old1
+new1
@@ -5,2 +5,2 @@
-old2
+new2"""
        ]
        
        for diff in valid_diffs:
            assert _is_unified_diff(diff), f"Should recognize as valid diff: {diff[:50]}..."
    
    def test_invalid_diff_formats(self):
        """Test rejection of invalid diff formats."""
        invalid_diffs = [
            "",  # Empty
            "just some text",  # Not a diff
            "--- a/file.py",  # Missing +++
            "+++ b/file.py",  # Missing ---
            """--- a/file.py
+++ b/file.py
no hunk header""",  # Missing @@ hunk
            """--- a/file.py
+++ b/file.py
@@ invalid hunk @@""",  # Invalid hunk format
            """--- a/file.py
+++ b/file.py
@@ -1,1 +1,1 @@
 no changes"""  # No actual changes
        ]
        
        for diff in invalid_diffs:
            assert not _is_unified_diff(diff), f"Should reject as invalid diff: {diff[:50]}..."
    
    def test_diff_allowlist_validation(self):
        """Test validation that diffs only touch allowed file paths."""
        # Valid diff touching allowed area
        valid_diff = """--- a/app/config.py
+++ b/app/config.py
@@ -1 +1 @@
-old
+new"""
        
        assert _diff_touches_only_allowlist(valid_diff, DGM_ALLOWED_AREAS)
        
        # Invalid diff touching disallowed area
        invalid_diff = """--- a/database/schema.sql
+++ b/database/schema.sql
@@ -1 +1 @@
-old
+new"""
        
        assert not _diff_touches_only_allowlist(invalid_diff, DGM_ALLOWED_AREAS)
        
        # Mixed diff (some allowed, some not) - should fail
        mixed_diff = """--- a/app/config.py
+++ b/app/config.py
@@ -1 +1 @@
-old
+new
--- a/database/schema.sql
+++ b/database/schema.sql
@@ -1 +1 @@
-old
+new"""
        
        assert not _diff_touches_only_allowlist(mixed_diff, DGM_ALLOWED_AREAS)


class TestJSONResponseParsing:
    """Test JSON response parsing and validation."""
    
    def test_valid_json_parsing(self):
        """Test parsing of valid JSON responses."""
        valid_responses = [
            # Standard format
            '''```json
{
  "area": "bandit",
  "rationale": "Increase exploration for better diversity",
  "diff": "--- a/app/config.py\\n+++ b/app/config.py\\n@@ -1 +1 @@\\n-old\\n+new"
}
```''',
            
            # Without code fences
            '''{
  "area": "prompts", 
  "rationale": "Clarify system instructions",
  "diff": "--- a/prompts/system.md\\n+++ b/prompts/system.md\\n@@ -1 +1 @@\\n-old\\n+new"
}''',
            
            # With extra text around JSON
            '''Here is my response:
```json
{
  "area": "rag",
  "rationale": "Adjust similarity threshold", 
  "diff": "--- a/app/rag/retriever.py\\n+++ b/app/rag/retriever.py\\n@@ -1 +1 @@\\n-old\\n+new"
}
```
That's my proposal.'''
        ]
        
        for response in valid_responses:
            parsed = _parse_response(response, "test-model")
            assert parsed is not None
            assert "area" in parsed
            assert "rationale" in parsed  
            assert "diff" in parsed
            assert parsed["area"] in ["bandit", "prompts", "rag"]
    
    def test_invalid_json_parsing(self):
        """Test handling of invalid JSON responses."""
        invalid_responses = [
            "",  # Empty
            "No JSON here",  # No JSON
            "```json\n{invalid json}\n```",  # Invalid JSON syntax
            '{"area": "bandit"}',  # Missing required fields
            '{"area": "", "rationale": "", "diff": ""}',  # Empty fields
            '''```json
{
  "area": "invalid_area",
  "rationale": "Test", 
  "diff": "valid diff"
}
```'''  # Invalid area (should be caught by validation later)
        ]
        
        for response in invalid_responses:
            parsed = _parse_response(response, "test-model")
            # Should either be None or fail validation
            if parsed is not None:
                # If parsed, should have required fields
                assert "area" in parsed
                assert "rationale" in parsed
                assert "diff" in parsed
    
    def test_json_extraction_edge_cases(self):
        """Test JSON extraction from various response formats."""
        # JSON at start
        response1 = '{"area": "bandit", "rationale": "test", "diff": "test"} extra text'
        parsed1 = _parse_response(response1, "model")
        assert parsed1 is not None
        
        # Nested braces
        response2 = '''```json
{
  "area": "bandit",
  "rationale": "Adjust config {param: value}",
  "diff": "--- a/config\\n+++ b/config\\n@@ -1 +1 @@\\n-{\\"old\\": true}\\n+{\\"new\\": true}"
}
```'''
        parsed2 = _parse_response(response2, "model")
        assert parsed2 is not None
        assert "config {param: value}" in parsed2["rationale"]


class TestPromptGeneration:
    """Test enhanced prompt generation for JSON output."""
    
    def test_json_prompt_format(self):
        """Test that prompt explicitly requests JSON format."""
        allowed_areas = ["bandit", "prompts"]
        max_loc = 10
        
        prompt = make_prompt(allowed_areas, max_loc)
        
        # Check JSON requirements
        assert "OUTPUT STRICTLY AS JSON:" in prompt
        assert "```json" in prompt
        assert '"area":' in prompt
        assert '"rationale":' in prompt
        assert '"diff":' in prompt
        
        # Check area specification
        assert "bandit, prompts" in prompt
        assert str(max_loc) in prompt
    
    def test_prompt_area_inclusion(self):
        """Test that all provided areas are included in prompt."""
        test_areas = ["bandit", "prompts", "rag"]
        prompt = make_prompt(test_areas, 20)
        
        for area in test_areas:
            assert area in prompt
    
    def test_prompt_example_format(self):
        """Test that prompt includes proper JSON example."""
        prompt = make_prompt(["bandit"], 50)
        
        # Should have example JSON
        assert "EXAMPLE:" in prompt
        assert '"area": "bandit"' in prompt
        assert '"rationale":' in prompt
        assert '"diff":' in prompt
        
        # Example should show escaped newlines for diff
        assert "\\n" in prompt


if __name__ == "__main__":
    pytest.main([__file__])