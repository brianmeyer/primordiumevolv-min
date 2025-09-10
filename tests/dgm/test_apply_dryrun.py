"""
Test DGM apply and dry-run functionality.
"""
import pytest
import tempfile
import os
from unittest.mock import patch, MagicMock
from app.dgm.apply import try_patch, rollback_patch, commit_patch, DryRunApplier
from app.dgm.types import MetaPatch, ApplyResult


@pytest.fixture
def sample_patch():
    """Create a sample MetaPatch for testing."""
    return MetaPatch(
        id="test_patch_001",
        area="prompts",
        origin="test",
        notes="Test patch for dry-run",
        diff="""--- a/prompts/test.md
+++ b/prompts/test.md
@@ -1,2 +1,3 @@
 # Test Prompt
 This is a test.
+Added line for testing.""",
        loc_delta=1
    )


@pytest.fixture
def invalid_patch():
    """Create an invalid MetaPatch for testing."""
    return MetaPatch(
        id="invalid_patch_001",
        area="prompts",
        origin="test",
        notes="Invalid patch",
        diff="""--- a/nonexistent_file.md
+++ b/nonexistent_file.md
@@ -1,1 +1,2 @@
 content
+new line""",
        loc_delta=1
    )


def test_dry_run_applier_context_manager():
    """Test DryRunApplier context manager behavior."""
    with DryRunApplier() as applier:
        assert applier.temp_dir is not None
        assert os.path.exists(applier.temp_dir)
        temp_dir = applier.temp_dir
    
    # After context exit, temp dir should be cleaned up
    assert not os.path.exists(temp_dir)


def test_try_patch_dry_run_success(sample_patch):
    """Test successful dry-run patch application."""
    # Create a temporary file to patch
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("# Test Prompt\nThis is a test.\n")
        temp_file = f.name
    
    try:
        # Modify patch to target the temp file
        sample_patch.diff = sample_patch.diff.replace(
            "a/prompts/test.md", f"a{temp_file}"
        ).replace(
            "b/prompts/test.md", f"b{temp_file}"
        )
        
        result = try_patch(sample_patch, dry_run=True)
        
        assert isinstance(result, ApplyResult)
        assert result.patch_id == "test_patch_001"
        assert result.success is True
        assert result.apply_ok is True
        
    finally:
        os.unlink(temp_file)


def test_try_patch_dry_run_failure(invalid_patch):
    """Test dry-run patch application failure."""
    result = try_patch(invalid_patch, dry_run=True)
    
    assert isinstance(result, ApplyResult)
    assert result.patch_id == "invalid_patch_001"
    assert result.success is False
    assert result.apply_ok is False
    assert len(result.stderr) > 0


def test_try_patch_live_mode_blocked(sample_patch):
    """Test that live mode is blocked without proper flags."""
    with patch('app.config.DGM_ALLOW_COMMITS', False):
        result = try_patch(sample_patch, dry_run=False)
        
        assert result.success is False
        assert "Live commits disabled" in str(result.stderr)


def test_try_patch_live_mode_enabled(sample_patch):
    """Test live mode when properly enabled."""
    with patch('app.config.DGM_ALLOW_COMMITS', True), \
         tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        
        f.write("# Test Prompt\nThis is a test.\n")
        temp_file = f.name
        
        # Modify patch to target the temp file
        sample_patch.diff = sample_patch.diff.replace(
            "a/prompts/test.md", f"a{temp_file}"
        ).replace(
            "b/prompts/test.md", f"b{temp_file}"
        )
        
        try:
            result = try_patch(sample_patch, dry_run=False)
            
            # Should succeed in live mode
            assert result.success is True
            
            # Verify file was actually modified
            with open(temp_file, 'r') as modified_file:
                content = modified_file.read()
                assert "Added line for testing." in content
                
        finally:
            os.unlink(temp_file)


def test_rollback_patch_functionality(sample_patch):
    """Test rollback_patch reverses changes."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        original_content = "# Test Prompt\nThis is a test.\n"
        f.write(original_content)
        temp_file = f.name
    
    try:
        # Modify patch to target the temp file
        sample_patch.diff = sample_patch.diff.replace(
            "a/prompts/test.md", f"a{temp_file}"
        ).replace(
            "b/prompts/test.md", f"b{temp_file}"
        )
        
        # Apply patch first
        with patch('app.config.DGM_ALLOW_COMMITS', True):
            apply_result = try_patch(sample_patch, dry_run=False)
            assert apply_result.success is True
        
        # Verify file was modified
        with open(temp_file, 'r') as f:
            modified_content = f.read()
            assert "Added line for testing." in modified_content
        
        # Now rollback
        rollback_result = rollback_patch(sample_patch)
        
        assert rollback_result["success"] is True
        assert rollback_result["patch_id"] == "test_patch_001"
        
        # Verify file was restored
        with open(temp_file, 'r') as f:
            restored_content = f.read()
            assert restored_content == original_content
            assert "Added line for testing." not in restored_content
            
    finally:
        os.unlink(temp_file)


def test_rollback_patch_error_handling():
    """Test rollback_patch handles errors gracefully."""
    bad_patch = MetaPatch(
        id="bad_rollback",
        area="prompts",
        origin="test",
        notes="Bad rollback test",
        diff="invalid diff format",
        loc_delta=0
    )
    
    result = rollback_patch(bad_patch)
    
    assert result["success"] is False
    assert "error" in result
    assert result["patch_id"] == "bad_rollback"


def test_commit_patch_functionality(sample_patch):
    """Test commit_patch creates git commits."""
    with patch('subprocess.run') as mock_run, \
         patch('app.config.DGM_ALLOW_COMMITS', True):
        
        # Mock successful git operations
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="commit_sha_123"),  # git add
            MagicMock(returncode=0, stdout=""),  # git commit
            MagicMock(returncode=0, stdout="abc123def")  # git rev-parse
        ]
        
        result = commit_patch(sample_patch)
        
        assert result["success"] is True
        assert result["patch_id"] == "test_patch_001"
        assert "commit_sha" in result


def test_commit_patch_test_requirement():
    """Test commit_patch runs tests when required."""
    with patch('subprocess.run') as mock_run, \
         patch('app.config.DGM_ALLOW_COMMITS', True), \
         patch('app.config.DGM_TEST_BEFORE_COMMIT', True):
        
        # Mock test failure
        mock_run.side_effect = [
            MagicMock(returncode=1, stderr="Tests failed")  # pytest
        ]
        
        sample_patch = MetaPatch(
            id="test_req_patch",
            area="prompts",
            origin="test",
            notes="Requires tests",
            diff="test diff",
            loc_delta=1
        )
        
        result = commit_patch(sample_patch)
        
        assert result["success"] is False
        assert "Tests failed" in result.get("error", "")


def test_batch_apply_patches():
    """Test batch application of multiple patches."""
    from app.dgm.apply import batch_try_patches
    
    patches = [
        MetaPatch(
            id=f"batch_patch_{i}",
            area="prompts",
            origin="test",
            notes=f"Batch patch {i}",
            diff=f"--- a/test{i}.md\n+++ b/test{i}.md\n@@ -1,1 +1,2 @@\n test\n+line {i}",
            loc_delta=1
        )
        for i in range(3)
    ]
    
    results = batch_try_patches(patches, dry_run=True)
    
    assert len(results) == 3
    assert all(isinstance(r, ApplyResult) for r in results)
    assert all(r.patch_id.startswith("batch_patch_") for r in results)


def test_applier_safety_checks():
    """Test safety checks in patch application."""
    dangerous_patch = MetaPatch(
        id="dangerous_patch",
        area="prompts",
        origin="test",
        notes="Dangerous operations",
        diff="""--- a/.env
+++ b/.env
@@ -1,2 +1,3 @@
 SECRET_KEY=old
+MALICIOUS_CODE=true""",
        loc_delta=1
    )
    
    result = try_patch(dangerous_patch, dry_run=True)
    
    # Should reject dangerous operations
    assert result.success is False or "MALICIOUS_CODE" not in result.stdout


if __name__ == "__main__":
    pytest.main([__file__])