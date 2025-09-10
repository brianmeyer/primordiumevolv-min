"""
Test DGM commit and rollback functionality.
"""
import pytest
import tempfile
import os
from unittest.mock import patch, MagicMock
from app.dgm.apply import commit_patch, rollback_commit, rollback_patch
from app.dgm.types import MetaPatch


@pytest.fixture
def sample_patch():
    """Create a sample MetaPatch for testing."""
    return MetaPatch(
        id="commit_test_001",
        area="prompts",
        origin="test",
        notes="Test commit functionality",
        diff="""--- a/prompts/test.md
+++ b/prompts/test.md
@@ -1,2 +1,3 @@
 # Test Prompt
 This is a test.
+Committed change.""",
        loc_delta=1
    )


def test_commit_patch_success(sample_patch):
    """Test successful patch commit."""
    with patch('subprocess.run') as mock_run, \
         patch('app.config.DGM_ALLOW_COMMITS', True), \
         patch('app.config.DGM_TEST_BEFORE_COMMIT', False):
        
        # Mock successful git operations
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),  # git add
            MagicMock(returncode=0, stdout="", stderr=""),  # git commit
            MagicMock(returncode=0, stdout="abc123def456", stderr="")  # git rev-parse HEAD
        ]
        
        result = commit_patch(sample_patch)
        
        assert result["success"] is True
        assert result["patch_id"] == "commit_test_001"
        assert result["commit_sha"] == "abc123def456"
        assert "status" in result
        assert result["status"] == "committed"


def test_commit_patch_disabled(sample_patch):
    """Test commit patch when commits are disabled."""
    with patch('app.config.DGM_ALLOW_COMMITS', False):
        result = commit_patch(sample_patch)
        
        assert result["success"] is False
        assert "disabled" in result["error"].lower()


def test_commit_patch_with_tests_pass(sample_patch):
    """Test commit patch with test requirement - tests pass."""
    with patch('subprocess.run') as mock_run, \
         patch('app.config.DGM_ALLOW_COMMITS', True), \
         patch('app.config.DGM_TEST_BEFORE_COMMIT', True):
        
        # Mock successful test run and git operations
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="All tests passed", stderr=""),  # pytest
            MagicMock(returncode=0, stdout="", stderr=""),  # git add
            MagicMock(returncode=0, stdout="", stderr=""),  # git commit
            MagicMock(returncode=0, stdout="abc123def456", stderr="")  # git rev-parse HEAD
        ]
        
        result = commit_patch(sample_patch)
        
        assert result["success"] is True
        assert result["commit_sha"] == "abc123def456"


def test_commit_patch_with_tests_fail(sample_patch):
    """Test commit patch with test requirement - tests fail."""
    with patch('subprocess.run') as mock_run, \
         patch('app.config.DGM_ALLOW_COMMITS', True), \
         patch('app.config.DGM_TEST_BEFORE_COMMIT', True):
        
        # Mock test failure
        mock_run.return_value = MagicMock(
            returncode=1, 
            stdout="", 
            stderr="2 tests failed"
        )
        
        result = commit_patch(sample_patch)
        
        assert result["success"] is False
        assert "test" in result["error"].lower()
        assert "2 tests failed" in result["error"]


def test_commit_patch_git_add_failure(sample_patch):
    """Test commit patch when git add fails."""
    with patch('subprocess.run') as mock_run, \
         patch('app.config.DGM_ALLOW_COMMITS', True), \
         patch('app.config.DGM_TEST_BEFORE_COMMIT', False):
        
        # Mock git add failure
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="fatal: pathspec 'nonexistent.txt' did not match any files"
        )
        
        result = commit_patch(sample_patch)
        
        assert result["success"] is False
        assert "git add failed" in result["error"]


def test_commit_patch_git_commit_failure(sample_patch):
    """Test commit patch when git commit fails."""
    with patch('subprocess.run') as mock_run, \
         patch('app.config.DGM_ALLOW_COMMITS', True), \
         patch('app.config.DGM_TEST_BEFORE_COMMIT', False):
        
        # Mock git add success, commit failure
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),  # git add success
            MagicMock(returncode=1, stdout="", stderr="nothing to commit")  # git commit failure
        ]
        
        result = commit_patch(sample_patch)
        
        assert result["success"] is False
        assert "git commit failed" in result["error"]


def test_rollback_commit_success():
    """Test successful commit rollback."""
    commit_sha = "abc123def456"
    
    with patch('subprocess.run') as mock_run, \
         patch('app.config.DGM_ALLOW_COMMITS', True), \
         patch('app.dgm.storage.get_patch_storage') as mock_storage:
        
        # Mock storage returning patch info
        mock_storage.return_value.get_patch_by_commit.return_value = {
            "patch_id": "test_patch_001",
            "commit_sha": commit_sha
        }
        
        # Mock successful git operations
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=commit_sha, stderr=""),  # git rev-parse (verify)
            MagicMock(returncode=0, stdout="", stderr=""),  # git revert
            MagicMock(returncode=0, stdout="fed456cba321", stderr="")  # git rev-parse HEAD (rollback sha)
        ]
        
        result = rollback_commit(commit_sha)
        
        assert result["success"] is True
        assert result["commit_sha"] == commit_sha
        assert result["rollback_sha"] == "fed456cba321"
        assert result["status"] == "rolled_back"


def test_rollback_commit_disabled():
    """Test rollback when commits are disabled."""
    with patch('app.config.DGM_ALLOW_COMMITS', False):
        result = rollback_commit("abc123def456")
        
        assert result["success"] is False
        assert "disabled" in result["error"].lower()


def test_rollback_commit_not_found():
    """Test rollback of non-existent commit."""
    commit_sha = "nonexistent123"
    
    with patch('subprocess.run') as mock_run, \
         patch('app.config.DGM_ALLOW_COMMITS', True):
        
        # Mock git rev-parse failure (commit not found)
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr=f"fatal: ambiguous argument '{commit_sha}': unknown revision"
        )
        
        result = rollback_commit(commit_sha)
        
        assert result["success"] is False
        assert "not found" in result["error"] or "unknown revision" in result["error"]


def test_rollback_commit_revert_failure():
    """Test rollback when git revert fails."""
    commit_sha = "abc123def456"
    
    with patch('subprocess.run') as mock_run, \
         patch('app.config.DGM_ALLOW_COMMITS', True), \
         patch('app.dgm.storage.get_patch_storage') as mock_storage:
        
        mock_storage.return_value.get_patch_by_commit.return_value = {
            "patch_id": "test_patch_001",
            "commit_sha": commit_sha
        }
        
        # Mock git verify success, revert failure
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=commit_sha, stderr=""),  # git rev-parse success
            MagicMock(returncode=1, stdout="", stderr="error: could not revert")  # git revert failure
        ]
        
        result = rollback_commit(commit_sha)
        
        assert result["success"] is False
        assert "revert failed" in result["error"].lower()


def test_rollback_patch_success(sample_patch):
    """Test successful patch rollback."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        # Create file with applied patch content
        f.write("# Test Prompt\nThis is a test.\nCommitted change.\n")
        temp_file = f.name
    
    try:
        # Modify patch to target the temp file
        sample_patch.diff = sample_patch.diff.replace(
            "a/prompts/test.md", f"a{temp_file}"
        ).replace(
            "b/prompts/test.md", f"b{temp_file}"
        )
        
        result = rollback_patch(sample_patch)
        
        assert result["success"] is True
        assert result["patch_id"] == "commit_test_001"
        
        # Verify file was reverted
        with open(temp_file, 'r') as f:
            content = f.read()
            assert "Committed change." not in content
            
    finally:
        os.unlink(temp_file)


def test_rollback_patch_invalid_diff():
    """Test rollback patch with invalid diff."""
    invalid_patch = MetaPatch(
        id="invalid_rollback",
        area="prompts",
        origin="test",
        notes="Invalid rollback",
        diff="invalid diff format",
        loc_delta=0
    )
    
    result = rollback_patch(invalid_patch)
    
    assert result["success"] is False
    assert "error" in result
    assert result["patch_id"] == "invalid_rollback"


def test_rollback_patch_file_not_found():
    """Test rollback patch when target file doesn't exist."""
    nonexistent_patch = MetaPatch(
        id="nonexistent_file",
        area="prompts",
        origin="test",
        notes="File doesn't exist",
        diff="""--- a/nonexistent/file.md
+++ b/nonexistent/file.md
@@ -1,1 +1,2 @@
 content
+new line""",
        loc_delta=1
    )
    
    result = rollback_patch(nonexistent_patch)
    
    assert result["success"] is False
    assert "error" in result


def test_commit_and_rollback_integration(sample_patch):
    """Test full commit and rollback cycle."""
    with patch('subprocess.run') as mock_run, \
         patch('app.config.DGM_ALLOW_COMMITS', True), \
         patch('app.config.DGM_TEST_BEFORE_COMMIT', False), \
         patch('app.dgm.storage.get_patch_storage') as mock_storage:
        
        commit_sha = "abc123def456"
        rollback_sha = "fed456cba321"
        
        # Mock storage
        mock_storage.return_value.get_patch_by_commit.return_value = {
            "patch_id": sample_patch.id,
            "commit_sha": commit_sha
        }
        
        # Phase 1: Commit
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),  # git add
            MagicMock(returncode=0, stdout="", stderr=""),  # git commit
            MagicMock(returncode=0, stdout=commit_sha, stderr="")  # git rev-parse HEAD
        ]
        
        commit_result = commit_patch(sample_patch)
        
        assert commit_result["success"] is True
        assert commit_result["commit_sha"] == commit_sha
        
        # Phase 2: Rollback
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=commit_sha, stderr=""),  # git rev-parse (verify)
            MagicMock(returncode=0, stdout="", stderr=""),  # git revert
            MagicMock(returncode=0, stdout=rollback_sha, stderr="")  # git rev-parse HEAD
        ]
        
        rollback_result = rollback_commit(commit_sha)
        
        assert rollback_result["success"] is True
        assert rollback_result["rollback_sha"] == rollback_sha


def test_commit_storage_integration(sample_patch):
    """Test commit patch storage integration."""
    with patch('subprocess.run') as mock_run, \
         patch('app.config.DGM_ALLOW_COMMITS', True), \
         patch('app.config.DGM_TEST_BEFORE_COMMIT', False), \
         patch('app.dgm.storage.get_patch_storage') as mock_storage:
        
        # Mock successful git operations
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),
            MagicMock(returncode=0, stdout="", stderr=""),
            MagicMock(returncode=0, stdout="abc123def456", stderr="")
        ]
        
        # Mock storage
        mock_store = MagicMock()
        mock_storage.return_value = mock_store
        
        result = commit_patch(sample_patch)
        
        assert result["success"] is True
        # Should have stored patch information
        mock_store.store_patch.assert_called_once()


def test_atomic_commit_rollback():
    """Test that commit/rollback operations are atomic."""
    # This test would verify that partial failures are handled correctly
    # and system state remains consistent
    
    sample_patch = MetaPatch(
        id="atomic_test",
        area="prompts",
        origin="test",
        notes="Atomic operation test",
        diff="test diff",
        loc_delta=1
    )
    
    with patch('subprocess.run') as mock_run, \
         patch('app.config.DGM_ALLOW_COMMITS', True):
        
        # Simulate partial failure (add succeeds, commit fails)
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),  # git add success
            MagicMock(returncode=1, stdout="", stderr="commit failed")  # git commit failure
        ]
        
        result = commit_patch(sample_patch)
        
        assert result["success"] is False
        # System should be in consistent state (staged changes should be handled)


if __name__ == "__main__":
    pytest.main([__file__])