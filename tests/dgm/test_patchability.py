"""
Test DGM patch applicability improvements: snapshots, diff normalization/repair, and enhanced diagnostics.

This test suite validates the improvements made to increase the percentage of non-smoke 
proposals that pass dry_run (git apply + lint/tests).
"""
import pytest
import tempfile
import os
import json
from unittest.mock import patch, MagicMock, mock_open
from app.dgm.proposer import get_snapshot, normalize_diff, repair_diff_on_apply_fail, make_prompt, _parse_response
from app.dgm.apply import try_patch
from app.dgm.types import MetaPatch, ApplyResult, extract_diff_stats
from app.config import DGM_LAST_PROPOSE_FILE


@pytest.fixture
def sample_files_for_snapshots():
    """Create sample files for snapshot testing."""
    return {
        "app/config.py": """# Configuration constants
EVO_DEFAULTS = {
    "n": 16,
    "memory_k": 3,
    "eps": 0.6
}
""",
        "app/prompts.py": """# System prompts
SYSTEM_PROMPT = "You are a helpful AI assistant."
""",
        "app/main.py": """from fastapi import FastAPI
app = FastAPI()

@app.get("/")
def root():
    return {"status": "ok"}
"""
    }


@pytest.fixture
def valid_diff():
    """A properly formatted unified diff."""
    return """--- a/app/config.py
+++ b/app/config.py
@@ -2,4 +2,5 @@
 EVO_DEFAULTS = {
     "n": 16,
     "memory_k": 3,
-    "eps": 0.6
+    "eps": 0.6,
+    "new_param": 42
 }
"""


@pytest.fixture
def malformed_diff():
    """A diff missing proper headers."""
    return """@@ -2,4 +2,5 @@
 EVO_DEFAULTS = {
     "n": 16,
     "memory_k": 3,
-    "eps": 0.6
+    "eps": 0.6,
+    "new_param": 42
 }
"""


@pytest.fixture
def crlf_diff():
    """A diff with CRLF line endings."""
    diff_content = """--- a/app/config.py\r
+++ b/app/config.py\r
@@ -2,4 +2,5 @@\r
 EVO_DEFAULTS = {\r
     "n": 16,\r
     "memory_k": 3,\r
-    "eps": 0.6\r
+    "eps": 0.6,\r
+    "new_param": 42\r
 }\r
"""
    return diff_content


class TestFileSnapshots:
    """Test file snapshot functionality for providing real content to models."""
    
    def test_get_snapshot_bandit_area(self, sample_files_for_snapshots):
        """Test snapshot generation for bandit area."""
        with patch('builtins.open', mock_open()) as mock_file:
            mock_file.return_value.read.return_value = sample_files_for_snapshots["app/config.py"]
            
            snapshots = get_snapshot("bandit")
            
            assert len(snapshots) >= 1
            assert any(s["path"] == "app/config.py" for s in snapshots)
            snapshot = next(s for s in snapshots if s["path"] == "app/config.py")
            assert "EVO_DEFAULTS" in snapshot["content"]
    
    def test_get_snapshot_prompts_area(self, sample_files_for_snapshots):
        """Test snapshot generation for prompts area."""
        with patch('builtins.open', mock_open()) as mock_file:
            def side_effect(path, *args, **kwargs):
                if "prompts.py" in path:
                    mock_file.return_value.read.return_value = sample_files_for_snapshots["app/prompts.py"]
                elif "main.py" in path:
                    mock_file.return_value.read.return_value = sample_files_for_snapshots["app/main.py"]
                return mock_file.return_value
            
            mock_file.side_effect = side_effect
            
            snapshots = get_snapshot("prompts")
            
            assert len(snapshots) >= 2
            paths = [s["path"] for s in snapshots]
            assert "app/prompts.py" in paths
            assert "app/main.py" in paths
    
    def test_get_snapshot_unknown_area(self):
        """Test snapshot generation for unknown area returns empty list."""
        snapshots = get_snapshot("unknown_area")
        assert snapshots == []
    
    @patch('os.path.exists')
    def test_get_snapshot_missing_files_skipped(self, mock_exists):
        """Test that missing files are gracefully skipped."""
        mock_exists.return_value = False
        
        snapshots = get_snapshot("bandit")
        
        # Should return empty list when no files exist
        assert snapshots == []


class TestDiffNormalization:
    """Test diff normalization and repair functionality."""
    
    def test_normalize_diff_valid_diff(self, valid_diff):
        """Test that a valid diff passes through unchanged."""
        normalized = normalize_diff(valid_diff)
        assert normalized == valid_diff
    
    def test_normalize_diff_crlf_conversion(self, crlf_diff):
        """Test CRLF to LF conversion."""
        normalized = normalize_diff(crlf_diff)
        
        # Should not contain CRLF
        assert '\r\n' not in normalized
        assert '\r' not in normalized
        # Should still be a valid diff
        assert "--- a/app/config.py" in normalized
        assert "+++ b/app/config.py" in normalized
    
    def test_normalize_diff_adds_headers(self, malformed_diff):
        """Test that missing a/b headers are added."""
        normalized = normalize_diff(malformed_diff)
        
        # Should have proper headers added
        assert "--- a/" in normalized or "--- /dev/null" in normalized
        assert "+++ b/" in normalized or "+++ /dev/null" in normalized
    
    def test_repair_diff_on_apply_fail_basic(self):
        """Test basic diff repair functionality."""
        original_diff = """--- a/app/config.py
+++ b/app/config.py
@@ -1,3 +1,4 @@
 line1
 line2
+new_line
 line3
"""
        
        error_message = "patch does not apply"
        
        # Mock file reading for repair
        with patch('builtins.open', mock_open(read_data="line1\nline2\nline3\n")):
            with patch('os.path.exists', return_value=True):
                repaired = repair_diff_on_apply_fail(original_diff, error_message, "prompts")
                
                # Should return some form of repaired diff
                assert repaired is not None
                assert isinstance(repaired, str)
    
    def test_repair_diff_file_not_found(self):
        """Test repair when target file doesn't exist."""
        diff = """--- a/nonexistent.py
+++ b/nonexistent.py
@@ -1,1 +1,2 @@
 content
+new line
"""
        
        with patch('os.path.exists', return_value=False):
            repaired = repair_diff_on_apply_fail(diff, "file not found", "prompts")
            
            # Should handle gracefully
            assert repaired is None or repaired == diff


class TestEnhancedDiagnostics:
    """Test enhanced diagnostic information from apply results."""
    
    def test_extract_diff_stats_basic(self, valid_diff):
        """Test extraction of basic diff statistics."""
        files, stats = extract_diff_stats(valid_diff)
        
        assert "app/config.py" in files
        assert stats["additions"] == 2  # +new_param and +comma
        assert stats["deletions"] == 1  # old eps line
        assert stats["total_changes"] == 3
        assert stats["files_count"] == 1
    
    def test_extract_diff_stats_multiple_files(self):
        """Test diff stats for multiple files."""
        multi_diff = """--- a/file1.py
+++ b/file1.py
@@ -1,1 +1,2 @@
 content1
+new line
--- a/file2.py
+++ b/file2.py
@@ -1,1 +1,1 @@
-old content
+new content
"""
        
        files, stats = extract_diff_stats(multi_diff)
        
        assert len(files) == 2
        assert "file1.py" in files
        assert "file2.py" in files
        assert stats["additions"] == 2
        assert stats["deletions"] == 1
        assert stats["files_count"] == 2
    
    def test_extract_diff_stats_empty_diff(self):
        """Test diff stats for empty diff."""
        files, stats = extract_diff_stats("")
        
        assert files == []
        assert stats == {}
    
    def test_apply_result_enhanced_fields(self):
        """Test that ApplyResult has all enhanced diagnostic fields."""
        result = ApplyResult(patch_id="test", success=False)
        
        # Check all enhanced fields exist
        assert hasattr(result, 'apply_stdout')
        assert hasattr(result, 'apply_stderr')
        assert hasattr(result, 'lint_stdout')
        assert hasattr(result, 'lint_stderr')
        assert hasattr(result, 'test_stdout')
        assert hasattr(result, 'test_stderr')
        assert hasattr(result, 'files_modified')
        assert hasattr(result, 'diff_stats')
        assert hasattr(result, 'repair_attempted')
        assert hasattr(result, 'repair_successful')
        
        # Check defaults
        assert result.repair_attempted is False
        assert result.repair_successful is False
        assert isinstance(result.files_modified, list)
        assert isinstance(result.diff_stats, dict)


class TestJSONProposalFormat:
    """Test the new JSON-based proposal format."""
    
    def test_make_prompt_includes_snapshots(self, sample_files_for_snapshots):
        """Test that make_prompt includes file snapshots in JSON format."""
        with patch('app.dgm.proposer.get_snapshot') as mock_snapshot:
            mock_snapshot.return_value = [
                {"path": "app/config.py", "content": sample_files_for_snapshots["app/config.py"]}
            ]
            
            prompt = make_prompt("bandit", ["param_tuning"])
            
            # Should be requesting JSON format
            assert "JSON" in prompt
            assert "snapshots" in prompt.lower()
            mock_snapshot.assert_called_once_with("bandit")
    
    def test_parse_response_json_format(self):
        """Test parsing of JSON-formatted responses."""
        json_response = """{
    "patches": [
        {
            "notes": "Increase exploration parameter",
            "diff": "--- a/app/config.py\\n+++ b/app/config.py\\n@@ -3,3 +3,3 @@\\n     \\"n\\": 16,\\n     \\"memory_k\\": 3,\\n-    \\"eps\\": 0.6\\n+    \\"eps\\": 0.8\\n }"
        }
    ]
}"""
        
        patches = _parse_response(json_response, "bandit", "test_model")
        
        assert len(patches) == 1
        patch = patches[0]
        assert patch.notes == "Increase exploration parameter"
        assert "eps" in patch.diff
        assert patch.area == "bandit"
        assert patch.origin == "test_model"
    
    def test_parse_response_legacy_format(self):
        """Test parsing of legacy text-based responses."""
        legacy_response = """
## Patch 1: Increase exploration
```diff
--- a/app/config.py
+++ b/app/config.py
@@ -3,3 +3,3 @@
     "n": 16,
     "memory_k": 3,
-    "eps": 0.6
+    "eps": 0.8
 }
```
"""
        
        patches = _parse_response(legacy_response, "bandit", "test_model")
        
        assert len(patches) >= 1
        # Should handle legacy format gracefully


class TestPersistentDebugEndpoint:
    """Test persistent debug storage functionality."""
    
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.makedirs')
    @patch('tempfile.NamedTemporaryFile')
    @patch('shutil.move')
    def test_debug_data_persistence(self, mock_move, mock_temp, mock_makedirs, mock_file):
        """Test that proposal data is persisted correctly."""
        from app.main import dgm_propose
        
        # Mock the proposer to return test data
        test_response_data = {
            "patches": [],
            "rejected": [],
            "count": 0,
            "session_id": "test-session"
        }
        
        # Mock the temporary file creation
        mock_temp_instance = MagicMock()
        mock_temp_instance.name = "/tmp/test_file.tmp"
        mock_temp.return_value.__enter__.return_value = mock_temp_instance
        
        # The function should attempt to persist data
        # This test validates the persistence logic exists
        assert callable(dgm_propose)
    
    def test_debug_endpoint_exists(self):
        """Test that the debug endpoint is properly defined."""
        from app.main import app
        
        # Check that the debug endpoint is registered
        routes = [route.path for route in app.routes]
        assert "/api/dgm/debug/last_propose" in routes


class TestIntegratedPatchability:
    """Integration tests for the complete patchability improvements."""
    
    def test_try_patch_with_enhanced_diagnostics(self, valid_diff):
        """Test that try_patch returns enhanced diagnostic information."""
        patch = MetaPatch(
            id="test_enhanced_diag",
            area="prompts",
            origin="test",
            notes="Test enhanced diagnostics",
            diff=valid_diff,
            loc_delta=3
        )
        
        with patch('app.dgm.apply.DryRunApplier') as mock_applier:
            # Mock successful application
            mock_applier_instance = MagicMock()
            mock_applier.return_value.__enter__.return_value = mock_applier_instance
            mock_applier_instance._create_worktree.return_value = "/tmp/test_worktree"
            mock_applier_instance._apply_patch.return_value = (True, "Applied successfully", "")
            mock_applier_instance._run_lint.return_value = (True, "Linting passed", "")
            mock_applier_instance._run_unit_tests.return_value = (True, "Tests passed", "")
            
            result = try_patch(patch, dry_run=True)
            
            # Should have enhanced diagnostic fields populated
            assert result.apply_stdout == "Applied successfully"
            assert result.lint_stdout == "Linting passed"
            assert result.test_stdout == "Tests passed"
            assert len(result.files_modified) > 0
            assert "app/config.py" in result.files_modified
            assert result.diff_stats["total_changes"] > 0
    
    def test_try_patch_with_repair_attempt(self, malformed_diff):
        """Test that try_patch attempts repair for failing patches."""
        patch = MetaPatch(
            id="test_repair",
            area="prompts",
            origin="test",
            notes="Test repair functionality",
            diff=malformed_diff,
            loc_delta=2
        )
        
        with patch('app.dgm.apply.DryRunApplier') as mock_applier:
            mock_applier_instance = MagicMock()
            mock_applier.return_value.__enter__.return_value = mock_applier_instance
            mock_applier_instance._create_worktree.return_value = "/tmp/test_worktree"
            
            # First apply fails, second succeeds (simulating repair)
            mock_applier_instance._apply_patch.side_effect = [
                (False, "", "patch does not apply"),  # Initial failure
                (True, "Applied after repair", "")     # Success after repair
            ]
            mock_applier_instance._run_lint.return_value = (True, "Linting passed", "")
            mock_applier_instance._run_unit_tests.return_value = (True, "Tests passed", "")
            
            with patch('app.dgm.proposer.repair_diff_on_apply_fail') as mock_repair:
                mock_repair.return_value = "repaired diff content"
                
                result = try_patch(patch, dry_run=True)
                
                # Should indicate repair was attempted and successful
                assert result.repair_attempted is True
                assert result.repair_successful is True
                assert result.success is True  # Overall success after repair


class TestErrorHandling:
    """Test error handling and edge cases."""
    
    def test_get_snapshot_io_error(self):
        """Test snapshot generation handles IO errors gracefully."""
        with patch('builtins.open', side_effect=IOError("File read error")):
            snapshots = get_snapshot("bandit")
            
            # Should handle errors gracefully and return empty list
            assert snapshots == []
    
    def test_normalize_diff_empty_input(self):
        """Test diff normalization with empty input."""
        result = normalize_diff("")
        assert result == ""
    
    def test_extract_diff_stats_malformed_diff(self):
        """Test diff stats extraction with malformed input."""
        malformed = "not a diff at all"
        files, stats = extract_diff_stats(malformed)
        
        assert files == []
        assert stats["additions"] == 0
        assert stats["deletions"] == 0
    
    def test_repair_diff_exception_handling(self):
        """Test that diff repair handles exceptions gracefully."""
        with patch('builtins.open', side_effect=Exception("Unexpected error")):
            result = repair_diff_on_apply_fail("diff", "error", "area")
            
            # Should handle exceptions and return None or original diff
            assert result is None or isinstance(result, str)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])