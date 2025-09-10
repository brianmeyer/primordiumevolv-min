"""
Test DGM Stage-4 commit and rollback functionality.
"""
import pytest
import json
from unittest.mock import patch, MagicMock
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_gitops():
    """Mock all gitops functions."""
    with patch('app.util.gitops.ensure_clean_index', return_value=True) as mock_clean, \
         patch('app.util.gitops.checkout_branch', return_value=True) as mock_checkout, \
         patch('app.util.gitops.apply_unified_diff', return_value=True) as mock_apply, \
         patch('app.util.gitops.run_tests', return_value=(True, True, "✓ All tests passed")) as mock_tests, \
         patch('app.util.gitops.commit_all', return_value="abc123def456789") as mock_commit, \
         patch('app.util.gitops.revert_commit', return_value=True) as mock_revert, \
         patch('app.util.gitops.commit_exists_on_branch', return_value=True) as mock_exists:
        
        yield {
            'ensure_clean_index': mock_clean,
            'checkout_branch': mock_checkout,
            'apply_unified_diff': mock_apply,
            'run_tests': mock_tests,
            'commit_all': mock_commit,
            'revert_commit': mock_revert,
            'commit_exists_on_branch': mock_exists
        }


@pytest.fixture
def mock_registry():
    """Mock registry with test data."""
    mock_records = [
        {
            "ts": "2024-01-01T12:00:00",
            "patch_id": "test_patch_001",
            "event": "propose",
            "diff": "--- a/test.py\n+++ b/test.py\n@@ -1,1 +1,2 @@\n print('hello')\n+print('world')",
            "area": "prompts",
            "origin": "test_origin",
            "notes": "Test patch for commit testing"
        }
    ]
    
    with patch('app.dgm.registry.get_registry') as mock_reg:
        mock_instance = MagicMock()
        mock_instance.list_by_patch.return_value = mock_records
        mock_instance.record.return_value = None
        mock_reg.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_sse():
    """Mock SSE manager."""
    with patch('app.server.sse.get_dgm_sse_manager') as mock_sse_manager:
        mock_instance = MagicMock()
        mock_instance.emit.return_value = None
        mock_sse_manager.return_value = mock_instance
        yield mock_instance


@pytest.fixture 
def enable_dgm():
    """Enable DGM for testing."""
    with patch('app.config.FF_DGM', True), \
         patch('app.config.DGM_REQUIRE_MANUAL', 1), \
         patch('app.config.DGM_COMMIT_BRANCH', 'dgm/active'), \
         patch('app.config.DGM_AUTHOR', 'test-bot <test@example.com>'), \
         patch('app.config.DGM_ARTIFACT_DIR', 'test/artifacts'), \
         patch('app.config.DGM_ALLOWED_AREAS', ['prompts', 'bandit']):
        yield


class TestCommitEndpoint:
    """Test the /api/dgm/commit endpoint."""
    
    def test_commit_success(self, client, mock_gitops, mock_registry, mock_sse, enable_dgm):
        """Test successful patch commit."""
        response = client.post("/api/dgm/commit", json={
            "patch_id": "test_patch_001",
            "shadow_eval": False
        })
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["ok"] is True
        assert data["patch_id"] == "test_patch_001"
        assert data["branch"] == "dgm/active"
        assert data["commit_sha"] == "abc123def456789"
        assert data["reason"] is None
        assert "artifacts" in data
        assert "dir" in data["artifacts"]
        assert "diff" in data["artifacts"]
        assert "report" in data["artifacts"]
        
        # Verify gitops calls
        mock_gitops['ensure_clean_index'].assert_called_once()
        mock_gitops['checkout_branch'].assert_called_once_with('dgm/active', create_if_missing=True)
        mock_gitops['apply_unified_diff'].assert_called_once()
        mock_gitops['run_tests'].assert_called_once()
        mock_gitops['commit_all'].assert_called_once()
        
        # Verify registry record
        mock_registry.record.assert_called_once_with("test_patch_001", "winner", {
            "branch": "dgm/active",
            "commit_sha": "abc123def456789",
            "artifact_dir": data["artifacts"]["dir"]
        })
        
        # Verify SSE events
        assert mock_sse.emit.call_count >= 2  # start and success events
    
    def test_commit_dgm_disabled(self, client):
        """Test commit fails when DGM is disabled."""
        with patch('app.config.FF_DGM', False):
            response = client.post("/api/dgm/commit", json={
                "patch_id": "test_patch_001"
            })
            
            assert response.status_code == 403
            data = response.json()
            assert "FF_DGM=1" in data["message"]
    
    def test_commit_manual_requirement_not_met(self, client, enable_dgm):
        """Test commit fails when DGM_REQUIRE_MANUAL != 1."""
        with patch('app.config.DGM_REQUIRE_MANUAL', 0):
            response = client.post("/api/dgm/commit", json={
                "patch_id": "test_patch_001"
            })
            
            assert response.status_code == 403
            data = response.json()
            assert "DGM_REQUIRE_MANUAL must be 1" in data["message"]
    
    def test_commit_missing_patch_id(self, client, enable_dgm):
        """Test commit fails with missing patch_id."""
        response = client.post("/api/dgm/commit", json={})
        
        assert response.status_code == 400
        data = response.json()
        assert data["ok"] is False
        assert data["reason"] == "patch_not_found"
    
    def test_commit_patch_not_found(self, client, enable_dgm, mock_sse):
        """Test commit fails when patch not found in registry."""
        with patch('app.dgm.registry.get_registry') as mock_reg:
            mock_instance = MagicMock()
            mock_instance.list_by_patch.return_value = []
            mock_reg.return_value = mock_instance
            
            response = client.post("/api/dgm/commit", json={
                "patch_id": "nonexistent_patch"
            })
            
            assert response.status_code == 400
            data = response.json()
            assert data["ok"] is False
            assert data["reason"] == "patch_not_found"
    
    def test_commit_dirty_index(self, client, mock_registry, mock_sse, enable_dgm):
        """Test commit fails with dirty git index."""
        with patch('app.util.gitops.ensure_clean_index', return_value=False):
            response = client.post("/api/dgm/commit", json={
                "patch_id": "test_patch_001"
            })
            
            assert response.status_code == 409
            data = response.json()
            assert data["ok"] is False
            assert data["reason"] == "dirty_index"
    
    def test_commit_disallowed_area(self, client, mock_sse, enable_dgm):
        """Test commit fails with disallowed modification area."""
        mock_records = [
            {
                "ts": "2024-01-01T12:00:00",
                "patch_id": "bad_patch_001",
                "event": "propose",
                "diff": "--- a/test.py\n+++ b/test.py\n@@ -1,1 +1,2 @@\n print('hello')\n+print('world')",
                "area": "forbidden_area",  # Not in DGM_ALLOWED_AREAS
                "origin": "test_origin",
                "notes": "Test patch for disallowed area"
            }
        ]
        
        with patch('app.dgm.registry.get_registry') as mock_reg:
            mock_instance = MagicMock()
            mock_instance.list_by_patch.return_value = mock_records
            mock_reg.return_value = mock_instance
            
            response = client.post("/api/dgm/commit", json={
                "patch_id": "bad_patch_001"
            })
            
            assert response.status_code == 400
            data = response.json()
            assert data["ok"] is False
            assert data["reason"] == "path_not_allowed"
    
    def test_commit_apply_failed(self, client, mock_registry, mock_sse, enable_dgm):
        """Test commit fails when patch application fails."""
        with patch('app.util.gitops.ensure_clean_index', return_value=True), \
             patch('app.util.gitops.checkout_branch', return_value=True), \
             patch('app.util.gitops.apply_unified_diff', return_value=False):  # Apply fails
            
            response = client.post("/api/dgm/commit", json={
                "patch_id": "test_patch_001"
            })
            
            assert response.status_code == 500
            data = response.json()
            assert data["ok"] is False
            assert data["reason"] == "apply_failed"
    
    def test_commit_tests_failed(self, client, mock_registry, mock_sse, enable_dgm):
        """Test commit fails when tests fail."""
        with patch('app.util.gitops.ensure_clean_index', return_value=True), \
             patch('app.util.gitops.checkout_branch', return_value=True), \
             patch('app.util.gitops.apply_unified_diff', return_value=True), \
             patch('app.util.gitops.run_tests', return_value=(False, True, "✗ Lint failed")):  # Lint fails
            
            response = client.post("/api/dgm/commit", json={
                "patch_id": "test_patch_001"
            })
            
            assert response.status_code == 500
            data = response.json()
            assert data["ok"] is False
            assert data["reason"] == "tests_failed"


class TestRollbackEndpoint:
    """Test the /api/dgm/rollback endpoint."""
    
    def test_rollback_success(self, client, mock_gitops, mock_registry, mock_sse, enable_dgm):
        """Test successful commit rollback."""
        response = client.post("/api/dgm/rollback", json={
            "commit_sha": "abc123def456789"
        })
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["ok"] is True
        assert data["reverted_sha"] == "abc123def456789"
        assert data["reason"] is None
        
        # Verify gitops calls
        mock_gitops['commit_exists_on_branch'].assert_called_once_with("abc123def456789", "dgm/active")
        mock_gitops['revert_commit'].assert_called_once_with("abc123def456789")
        
        # Verify registry record
        mock_registry.record.assert_called_once_with("rollback_abc123def456789", "winner", {
            "rollback_of": "abc123def456789",
            "branch": "dgm/active"
        })
        
        # Verify SSE events
        assert mock_sse.emit.call_count >= 2  # start and success events
    
    def test_rollback_dgm_disabled(self, client):
        """Test rollback fails when DGM is disabled."""
        with patch('app.config.FF_DGM', False):
            response = client.post("/api/dgm/rollback", json={
                "commit_sha": "abc123def456789"
            })
            
            assert response.status_code == 403
            data = response.json()
            assert "FF_DGM=1" in data["message"]
    
    def test_rollback_manual_requirement_not_met(self, client, enable_dgm):
        """Test rollback fails when DGM_REQUIRE_MANUAL != 1."""
        with patch('app.config.DGM_REQUIRE_MANUAL', 0):
            response = client.post("/api/dgm/rollback", json={
                "commit_sha": "abc123def456789"
            })
            
            assert response.status_code == 403
            data = response.json()
            assert "DGM_REQUIRE_MANUAL must be 1" in data["message"]
    
    def test_rollback_missing_commit_sha(self, client, enable_dgm):
        """Test rollback fails with missing commit_sha."""
        response = client.post("/api/dgm/rollback", json={})
        
        assert response.status_code == 400
        data = response.json()
        assert data["ok"] is False
        assert data["reason"] == "missing_commit_sha"
    
    def test_rollback_invalid_commit_sha(self, client, enable_dgm):
        """Test rollback fails with invalid commit SHA format."""
        response = client.post("/api/dgm/rollback", json={
            "commit_sha": "abc"  # Too short
        })
        
        assert response.status_code == 400
        data = response.json()
        assert data["ok"] is False
        assert data["reason"] == "invalid_commit_sha"
    
    def test_rollback_commit_not_found(self, client, mock_registry, mock_sse, enable_dgm):
        """Test rollback fails when commit not found on branch."""
        with patch('app.util.gitops.commit_exists_on_branch', return_value=False):
            response = client.post("/api/dgm/rollback", json={
                "commit_sha": "nonexistent123456"
            })
            
            assert response.status_code == 404
            data = response.json()
            assert data["ok"] is False
            assert data["reason"] == "commit_not_found"
    
    def test_rollback_revert_failed(self, client, mock_registry, mock_sse, enable_dgm):
        """Test rollback fails when git revert fails."""
        with patch('app.util.gitops.commit_exists_on_branch', return_value=True), \
             patch('app.util.gitops.revert_commit', return_value=False):  # Revert fails
            
            response = client.post("/api/dgm/rollback", json={
                "commit_sha": "abc123def456789"
            })
            
            assert response.status_code == 500
            data = response.json()
            assert data["ok"] is False
            assert data["reason"] == "revert_failed"