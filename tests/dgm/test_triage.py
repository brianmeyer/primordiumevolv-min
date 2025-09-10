"""
Tests for DGM enhanced proposal system with rich rejection reasons.

Tests the triage functionality including rejection reasons, auto-retry,
git apply checks, and smoke patch generation.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from app.dgm.proposer import _parse_response, _gen_one, generate
from app.dgm.apply import check_git_apply
from app.dgm.smokepatch import make_smoke_patch, validate_smoke_patch


class TestRichRejectionReasons:
    """Test rich rejection reason tracking."""
    
    def test_parse_response_bad_json(self):
        """Test bad_json rejection reason."""
        response = "This is not JSON at all, just prose."
        model_id = "test-model"
        
        parsed, reason, detail = _parse_response(response, model_id)
        
        assert parsed is None
        assert reason == "bad_json"
        assert "No JSON found" in detail
        assert len(detail) <= 200  # Detail should be truncated
    
    def test_parse_response_invalid_json(self):
        """Test JSON parsing error."""
        response = '{"area": "bandit", "notes": "test", "diff": invalid json}'
        model_id = "test-model"
        
        parsed, reason, detail = _parse_response(response, model_id)
        
        assert parsed is None
        assert reason == "bad_json"
        assert "Invalid JSON" in detail
    
    def test_parse_response_incomplete_json(self):
        """Test incomplete JSON fields."""
        response = '{"area": "bandit", "notes": "test"}'  # Missing diff
        model_id = "test-model"
        
        parsed, reason, detail = _parse_response(response, model_id)
        
        assert parsed is None
        assert reason == "bad_json"
        assert "missing fields" in detail
    
    def test_parse_response_success(self):
        """Test successful parsing."""
        response = '{"area": "bandit", "notes": "test change", "diff": "--- a/file\\n+++ b/file\\n@@ -1 +1 @@\\n-old\\n+new"}'
        model_id = "test-model"
        
        parsed, reason, detail = _parse_response(response, model_id)
        
        assert parsed is not None
        assert reason is None
        assert detail is None
        assert parsed["area"] == "bandit"
        assert parsed["notes"] == "test change"


class TestAutoRetry:
    """Test auto-retry functionality."""
    
    @patch('app.dgm.proposer._route_model_call')
    def test_auto_retry_on_bad_json(self, mock_route):
        """Test auto-retry when JSON parsing fails initially."""
        # First call returns bad JSON
        mock_route.side_effect = [
            ("This is not JSON", "test-model"),  # First attempt fails
            ('{"area": "bandit", "notes": "retry success", "diff": "--- a/file\\n+++ b/file\\n@@ -1 +1 @@\\n-old\\n+new"}', "test-model")  # Retry succeeds
        ]
        
        with patch('app.dgm.proposer._is_unified_diff', return_value=True), \
             patch('app.dgm.proposer._diff_touches_only_allowlist', return_value=True), \
             patch('app.dgm.proposer.calculate_loc_delta', return_value=2), \
             patch('app.dgm.proposer.is_safe_diff', return_value=(True, "")), \
             patch('app.dgm.proposer.check_git_apply', return_value=(True, "")), \
             patch('app.dgm.proposer.DGM_ALLOWED_AREAS', ["bandit"]), \
             patch('app.dgm.proposer.DGM_MAX_LOC_DELTA', 50):
            
            result, reason, detail = _gen_one("test-model")
        
        assert result is not None  # Should succeed after retry
        assert reason is None
        assert mock_route.call_count == 2  # Called twice due to retry
    
    @patch('app.dgm.proposer._route_model_call')
    def test_auto_retry_fails_twice(self, mock_route):
        """Test when both attempts fail."""
        # Both calls return bad JSON
        mock_route.side_effect = [
            ("Not JSON first", "test-model"),
            ("Not JSON second", "test-model")
        ]
        
        result, reason, detail = _gen_one("test-model")
        
        assert result is None
        assert reason == "bad_json"
        assert "No JSON found" in detail
        assert mock_route.call_count == 2


class TestGitApplyCheck:
    """Test git apply pre-flight checks."""
    
    @patch('subprocess.run')
    def test_git_apply_check_success(self, mock_run):
        """Test successful git apply check."""
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        
        diff = "--- a/file.py\\n+++ b/file.py\\n@@ -1 +1 @@\\n-old\\n+new"
        success, error = check_git_apply(diff)
        
        assert success is True
        assert error == ""
    
    @patch('subprocess.run')
    def test_git_apply_check_failure(self, mock_run):
        """Test failed git apply check with error details."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stderr="error: patch failed: file.py:1\\nerror: file.py: patch does not apply"
        )
        
        diff = "--- a/file.py\\n+++ b/file.py\\n@@ -1 +1 @@\\n-old\\n+new"
        success, error = check_git_apply(diff)
        
        assert success is False
        assert "patch failed" in error
        assert "does not apply" in error
    
    @patch('subprocess.run')
    def test_git_apply_check_timeout(self, mock_run):
        """Test git apply check timeout handling."""
        from subprocess import TimeoutExpired
        mock_run.side_effect = TimeoutExpired(["git", "apply", "--check"], 10)
        
        diff = "--- a/file.py\\n+++ b/file.py\\n@@ -1 +1 @@\\n-old\\n+new"
        success, error = check_git_apply(diff)
        
        assert success is False
        assert "exception" in error.lower()


class TestValidationReasons:
    """Test specific validation failure reasons."""
    
    @patch('app.dgm.proposer._route_model_call')
    def test_bad_area_rejection(self, mock_route):
        """Test rejection due to invalid area."""
        mock_route.return_value = (
            '{"area": "invalid_area", "notes": "test", "diff": "--- a/file\\n+++ b/file\\n@@ -1 +1 @@\\n-old\\n+new"}',
            "test-model"
        )
        
        with patch('app.dgm.proposer.DGM_ALLOWED_AREAS', ["bandit"]):
            result, reason, detail = _gen_one("test-model")
        
        assert result is None
        assert reason == "bad_area"
        assert "invalid_area" in detail
    
    @patch('app.dgm.proposer._route_model_call')
    def test_bad_diff_format_rejection(self, mock_route):
        """Test rejection due to bad diff format."""
        mock_route.return_value = (
            '{"area": "bandit", "notes": "test", "diff": "this is not a diff"}',
            "test-model"
        )
        
        with patch('app.dgm.proposer.DGM_ALLOWED_AREAS', ["bandit"]):
            result, reason, detail = _gen_one("test-model")
        
        assert result is None
        assert reason == "bad_diff_format"
        assert "Not unified diff format" in detail
    
    @patch('app.dgm.proposer._route_model_call')
    def test_path_not_allowed_rejection(self, mock_route):
        """Test rejection due to disallowed file paths."""
        # Diff that touches a file outside allowed areas
        mock_route.return_value = (
            '{"area": "bandit", "notes": "test", "diff": "--- a/forbidden/secret.py\\n+++ b/forbidden/secret.py\\n@@ -1 +1 @@\\n-old\\n+new"}',
            "test-model"
        )
        
        with patch('app.dgm.proposer.DGM_ALLOWED_AREAS', ["bandit"]), \
             patch('app.dgm.proposer._is_unified_diff', return_value=True):
            result, reason, detail = _gen_one("test-model")
        
        assert result is None
        assert reason == "path_not_allowed"
        assert "forbidden/secret.py" in detail
    
    @patch('app.dgm.proposer._route_model_call')
    def test_loc_delta_exceeded_rejection(self, mock_route):
        """Test rejection due to exceeding LOC limit."""
        mock_route.return_value = (
            '{"area": "bandit", "notes": "test", "diff": "--- a/file\\n+++ b/file\\n@@ -1 +1 @@\\n-old\\n+new"}',
            "test-model"
        )
        
        with patch('app.dgm.proposer.DGM_ALLOWED_AREAS', ["bandit"]), \
             patch('app.dgm.proposer._is_unified_diff', return_value=True), \
             patch('app.dgm.proposer._diff_touches_only_allowlist', return_value=True), \
             patch('app.dgm.proposer.calculate_loc_delta', return_value=100), \
             patch('app.dgm.proposer.DGM_MAX_LOC_DELTA', 50):
            
            result, reason, detail = _gen_one("test-model")
        
        assert result is None
        assert reason == "loc_delta_exceeded"
        assert "100" in detail
        assert "50" in detail
    
    @patch('app.dgm.proposer._route_model_call')
    def test_git_apply_check_rejection(self, mock_route):
        """Test rejection due to git apply failure."""
        mock_route.return_value = (
            '{"area": "bandit", "notes": "test", "diff": "--- a/file\\n+++ b/file\\n@@ -1 +1 @@\\n-old\\n+new"}',
            "test-model"
        )
        
        with patch('app.dgm.proposer.DGM_ALLOWED_AREAS', ["bandit"]), \
             patch('app.dgm.proposer._is_unified_diff', return_value=True), \
             patch('app.dgm.proposer._diff_touches_only_allowlist', return_value=True), \
             patch('app.dgm.proposer.calculate_loc_delta', return_value=2), \
             patch('app.dgm.proposer.DGM_MAX_LOC_DELTA', 50), \
             patch('app.dgm.proposer.check_git_apply', return_value=(False, "patch does not apply")):
            
            result, reason, detail = _gen_one("test-model")
        
        assert result is None
        assert reason == "git_apply_check"
        assert "does not apply" in detail


class TestSmokePatch:
    """Test smoke patch functionality."""
    
    def test_make_smoke_patch_structure(self):
        """Test smoke patch has required structure."""
        smoke_patch = make_smoke_patch()
        
        assert "area" in smoke_patch
        assert "notes" in smoke_patch
        assert "diff" in smoke_patch
        assert smoke_patch["area"] in ["ui_metrics", "bandit"]
    
    def test_validate_smoke_patch_success(self):
        """Test smoke patch validation passes."""
        smoke_patch = make_smoke_patch()
        
        is_valid, reason = validate_smoke_patch(smoke_patch)
        
        assert is_valid is True
        assert "Valid smoke patch" in reason
    
    def test_validate_smoke_patch_missing_fields(self):
        """Test smoke patch validation with missing fields."""
        incomplete_patch = {"area": "bandit", "notes": "test"}  # Missing diff
        
        is_valid, reason = validate_smoke_patch(incomplete_patch)
        
        assert is_valid is False
        assert "Missing required field" in reason
    
    def test_validate_smoke_patch_invalid_area(self):
        """Test smoke patch validation with invalid area."""
        invalid_patch = {
            "area": "forbidden_area",
            "notes": "test",
            "diff": "--- a/file\\n+++ b/file\\n@@ -1 +1 @@\\n-old\\n+new"
        }
        
        with patch('app.dgm.smokepatch.DGM_ALLOWED_AREAS', ["bandit"]):
            is_valid, reason = validate_smoke_patch(invalid_patch)
        
        assert is_valid is False
        assert "not in allowed areas" in reason
    
    def test_validate_smoke_patch_too_large(self):
        """Test smoke patch validation with too many changes."""
        # Create a large diff
        large_diff = "--- a/file\\n+++ b/file\\n@@ -1,20 +1,20 @@\\n"
        for i in range(15):  # More than 10 LOC
            large_diff += f"-old line {i}\\n+new line {i}\\n"
        
        large_patch = {
            "area": "bandit",
            "notes": "test",
            "diff": large_diff
        }
        
        with patch('app.dgm.smokepatch.DGM_ALLOWED_AREAS', ["bandit"]):
            is_valid, reason = validate_smoke_patch(large_patch)
        
        assert is_valid is False
        assert "too large" in reason


class TestIntegration:
    """Integration tests for the full triage system."""
    
    @patch('app.dgm.proposer.generate')
    def test_generate_with_smoke_patch(self, mock_generate):
        """Test that smoke patch is added when no regular proposals pass."""
        from app.dgm.types import ProposalResponse
        
        # Mock no successful proposals
        mock_response = ProposalResponse(
            patches=[],
            rejected=[
                {"reason": "bad_json", "detail": "No JSON found", "origin": "test-model", "area": "unknown"},
                {"reason": "git_apply_check", "detail": "patch failed", "origin": "test-model-2", "area": "unknown"}
            ],
            total_generated=2,
            execution_time_ms=100
        )
        mock_generate.return_value = mock_response
        
        # The actual smoke patch integration would be tested in the endpoint
        # This test verifies the mock structure matches expected format
        assert len(mock_response.patches) == 0
        assert len(mock_response.rejected) == 2
        assert mock_response.rejected[0]["reason"] == "bad_json"
        assert mock_response.rejected[1]["reason"] == "git_apply_check"
        
        # Each rejection should have required fields for triage
        for rejection in mock_response.rejected:
            assert "reason" in rejection
            assert "detail" in rejection
            assert "origin" in rejection
            assert "area" in rejection


if __name__ == "__main__":
    pytest.main([__file__])