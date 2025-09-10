"""
Test DGM registry API endpoints and functionality.

Tests registry read endpoints and proposal generation with registry writes.
"""

import pytest
import os
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    """Test client with mocked SSE."""
    with patch("app.server.sse.emit") as mock_sse:
        with TestClient(app) as client:
            yield client


@pytest.fixture
def enable_dgm():
    """Enable DGM for testing."""
    with patch("app.config.FF_DGM", True):
        yield


@pytest.fixture
def mock_registry():
    """Mock registry for testing."""
    from app.dgm.registry import DGMRegistry
    
    class MockRegistry(DGMRegistry):
        def __init__(self):
            self.records = []
            
        def record(self, patch_id, event, data):
            self.records.append({
                "ts": "2025-09-10T12:00:00",
                "patch_id": patch_id,
                "event": event,
                **data
            })
            
        def list_recent(self, n=50):
            return self.records[-n:][::-1]  # newest first
            
        def list_by_patch(self, patch_id):
            return [r for r in self.records if r["patch_id"] == patch_id][::-1]
            
        def stats(self):
            event_counts = {}
            for record in self.records:
                event = record["event"]
                event_counts[event] = event_counts.get(event, 0) + 1
            return {
                "total_records": len(self.records),
                "event_counts": event_counts,
                "last_ts": self.records[-1]["ts"] if self.records else None,
                "file_size_mb": 0.01
            }
    
    mock_registry = MockRegistry()
    
    with patch("app.dgm.registry.get_registry", return_value=mock_registry):
        yield mock_registry


def test_registry_stats_endpoint_ff_dgm_disabled(client):
    """Test registry stats endpoint with DGM disabled."""
    with patch("app.config.FF_DGM", False):
        response = client.get("/api/dgm/registry/stats")
        assert response.status_code == 403
        assert response.json() == {"enabled": False}


def test_registry_stats_endpoint_ff_dgm_enabled(client, enable_dgm, mock_registry):
    """Test registry stats endpoint with DGM enabled."""
    # Add some test data
    mock_registry.record("patch1", "propose", {"origin": "test", "area": "prompts"})
    mock_registry.record("patch1", "dry_run", {"lint_ok": True})
    
    response = client.get("/api/dgm/registry/stats")
    assert response.status_code == 200
    
    data = response.json()
    assert "stats" in data
    stats = data["stats"]
    assert stats["total_records"] == 2
    assert stats["event_counts"]["propose"] == 1
    assert stats["event_counts"]["dry_run"] == 1


def test_registry_recent_endpoint(client, enable_dgm, mock_registry):
    """Test registry recent endpoint."""
    # Add test records
    mock_registry.record("patch1", "propose", {"origin": "model1", "area": "prompts"})
    mock_registry.record("patch2", "propose", {"origin": "model2", "area": "bandit"})
    mock_registry.record("patch1", "dry_run", {"lint_ok": True, "tests_ok": False})
    
    response = client.get("/api/dgm/registry/recent?n=2")
    assert response.status_code == 200
    
    data = response.json()
    assert "items" in data
    assert len(data["items"]) == 2
    # Should be newest first
    assert data["items"][0]["event"] == "dry_run"
    assert data["items"][1]["event"] == "propose"
    assert data["items"][1]["origin"] == "model2"


def test_registry_patch_endpoint(client, enable_dgm, mock_registry):
    """Test registry patch-specific endpoint."""
    # Add test records
    mock_registry.record("patch1", "propose", {"origin": "model1", "area": "prompts"})
    mock_registry.record("patch2", "propose", {"origin": "model2", "area": "bandit"})
    mock_registry.record("patch1", "dry_run", {"lint_ok": True, "tests_ok": False})
    
    response = client.get("/api/dgm/registry/patch/patch1")
    assert response.status_code == 200
    
    data = response.json()
    assert "items" in data
    assert len(data["items"]) == 2  # 2 events for patch1
    assert all(item["patch_id"] == "patch1" for item in data["items"])
    # Should be newest first
    assert data["items"][0]["event"] == "dry_run"
    assert data["items"][1]["event"] == "propose"


@patch("app.dgm.proposer.generate")
@patch("app.dgm.apply.batch_try_patches")
def test_propose_endpoint_writes_to_registry(mock_apply, mock_generate, client, enable_dgm, mock_registry):
    """Test that the propose endpoint writes to registry."""
    # Mock proposer response
    
    patch_obj = MagicMock()
    patch_obj.id = "test-patch-123"
    patch_obj.origin = "llama-3.1-8b-instant"
    patch_obj.area = "prompts"
    patch_obj.loc_delta = 5
    patch_obj.notes = "Test improvement"
    
    proposal_response = MagicMock()
    proposal_response.patches = [patch_obj]
    proposal_response.rejected = [{"reason": "Too complex", "origin": "model", "area": "bandit"}]
    
    mock_generate.return_value = proposal_response
    
    # Mock apply results
    apply_result = MagicMock()
    apply_result.apply_ok = True
    apply_result.lint_ok = True
    apply_result.tests_ok = False
    mock_apply.return_value = [apply_result]
    
    # Make request
    response = client.post("/api/dgm/propose?dry_run=1")
    assert response.status_code == 200
    
    data = response.json()
    assert data["count"] == 1
    assert len(data["patches"]) == 1
    assert data["patches"][0]["id"] == "test-patch-123"
    assert data["patches"][0]["lint_ok"] is True
    assert data["patches"][0]["tests_ok"] is False
    
    # Verify registry writes
    records = mock_registry.records
    assert len(records) == 2  # propose + dry_run events
    
    # Check propose event
    propose_record = next(r for r in records if r["event"] == "propose")
    assert propose_record["patch_id"] == "test-patch-123"
    assert propose_record["origin"] == "llama-3.1-8b-instant"
    assert propose_record["area"] == "prompts"
    assert propose_record["loc_delta"] == 5
    assert propose_record["notes"] == "Test improvement"
    
    # Check dry_run event
    dry_run_record = next(r for r in records if r["event"] == "dry_run")
    assert dry_run_record["patch_id"] == "test-patch-123"
    assert dry_run_record["lint_ok"] is True
    assert dry_run_record["tests_ok"] is False
    assert dry_run_record["apply_ok"] is True


def test_sse_mocking_prevents_emit_calls(client, enable_dgm, mock_registry):
    """Test that SSE emit is properly mocked to prevent actual events."""
    with patch("app.dgm.proposer.generate") as mock_generate:
        with patch("app.dgm.apply.batch_try_patches") as mock_apply:
            with patch("app.server.sse.emit") as mock_sse:
                
                # Setup mocks
                patch_obj = MagicMock()
                patch_obj.id = "mock-patch"
                patch_obj.origin = "test-model"
                patch_obj.area = "prompts" 
                patch_obj.loc_delta = 1
                patch_obj.notes = "Mock"
                
                proposal_response = MagicMock()
                proposal_response.patches = [patch_obj]
                proposal_response.rejected = []
                mock_generate.return_value = proposal_response
                
                apply_result = MagicMock()
                apply_result.apply_ok = True
                apply_result.lint_ok = True
                apply_result.tests_ok = True
                mock_apply.return_value = [apply_result]
                
                # Make request
                response = client.post("/api/dgm/propose?dry_run=1")
                assert response.status_code == 200
                
                # Verify SSE emit was called (but mocked out)
                mock_sse.assert_called_once()
                call_args = mock_sse.call_args
                assert call_args[0][0] == "dgm.proposals"  # topic
                assert "patches" in call_args[0][1]  # payload has patches