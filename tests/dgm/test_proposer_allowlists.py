"""
Test DGM proposer allowlist functionality via API endpoints.
"""
import pytest
import time
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app.config import DGM_ALLOWED_AREAS
from app.dgm.types import MetaPatch, ProposalResponse


client = TestClient(app)


@pytest.fixture
def mock_sse():
    """Mock SSE emit to prevent dependency on live SSE infrastructure."""
    with patch("app.server.sse.emit", lambda *args, **kwargs: None):
        yield


@pytest.fixture 
def mock_registry():
    """Mock registry to prevent file system operations during tests."""
    with patch("app.dgm.registry.record", lambda *args, **kwargs: None):
        yield


@pytest.fixture
def mock_resource_guards():
    """Mock resource guards to always pass during tests."""
    mock_status = MagicMock()
    mock_status.to_dict.return_value = {"cpu_percent": 50.0, "memory_mb": 1024.0}
    
    with patch("app.dgm.resources.check_resource_guards", return_value=(True, [], mock_status)):
        yield


def test_proposer_respects_allowed_areas(mock_sse, mock_registry, mock_resource_guards):
    """Test that proposer only generates patches for allowed areas."""
    
    # Mock successful patch generation with mixed allowed/disallowed areas
    mock_patches = [
        MetaPatch.create("prompts", "llama-3.1-8b-instant", "Allowed patch 1", "diff content 1", 5),
        MetaPatch.create("forbidden_area", "gpt-oss-120b", "Not allowed", "diff content 2", 10),
        MetaPatch.create("bandit", "llama-3.3-70b-versatile", "Allowed patch 2", "diff content 3", 3),
    ]
    
    # Set validation results for allowed patches
    mock_patches[0].apply_ok = True
    mock_patches[0].lint_ok = True
    mock_patches[0].tests_ok = True
    mock_patches[2].apply_ok = True
    mock_patches[2].lint_ok = True  
    mock_patches[2].tests_ok = True
    
    mock_response = ProposalResponse(
        patches=[mock_patches[0], mock_patches[2]],  # Only allowed ones
        rejected=[{"area": "forbidden_area", "reason": "Area not in allowlist"}],
        total_generated=3,
        execution_time_ms=1500
    )
    
    with patch("app.dgm.proposer.generate", return_value=mock_response):
        with patch.dict("os.environ", {"FF_DGM": "1"}):
            response = client.post("/api/dgm/propose?dry_run=1")
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify response structure
    assert "count" in data
    assert "patches" in data
    assert "rejected" in data
    assert data["count"] == 2
    
    # Verify only allowed areas are in successful patches
    generated_areas = [patch["area"] for patch in data["patches"]]
    for area in generated_areas:
        assert area in DGM_ALLOWED_AREAS, f"Area '{area}' not in allowed list"
    
    # Verify rejected patch is reported
    assert len(data["rejected"]) == 1
    assert data["rejected"][0]["area"] == "forbidden_area"


def test_proposer_blocks_dangerous_operations(mock_sse, mock_registry, mock_resource_guards):
    """Test that proposer blocks dangerous file operations."""
    
    # Mock response with dangerous patches rejected
    mock_response = ProposalResponse(
        patches=[],  # No successful patches
        rejected=[
            {"area": "prompts", "reason": "Contains forbidden pattern: auth", "diff": "auth bypass"},
            {"area": "bandit", "reason": "Modifies restricted path: .env", "diff": "env modification"}
        ],
        total_generated=2,
        execution_time_ms=800
    )
    
    with patch("app.dgm.proposer.generate", return_value=mock_response):
        with patch.dict("os.environ", {"FF_DGM": "1"}):
            response = client.post("/api/dgm/propose?dry_run=1")
    
    assert response.status_code == 200
    data = response.json()
    
    # Should have no successful patches due to safety blocks
    assert data["count"] == 0
    assert len(data["patches"]) == 0
    assert len(data["rejected"]) == 2
    
    # Verify rejection reasons mention security
    rejection_reasons = [r["reason"] for r in data["rejected"]]
    assert any("forbidden" in reason for reason in rejection_reasons)


def test_proposer_validates_loc_delta(mock_sse, mock_registry, mock_resource_guards):
    """Test that proposer respects LOC delta limits."""
    
    # Mock response with patches exceeding LOC limits rejected
    mock_response = ProposalResponse(
        patches=[
            MetaPatch.create("prompts", "llama-3.1-8b-instant", "Small change", "small diff", 10)
        ],
        rejected=[
            {"area": "bandit", "reason": "LOC delta 75 exceeds maximum 50", "loc_delta": 75}
        ],
        total_generated=2,
        execution_time_ms=1200
    )
    
    # Set validation results for accepted patch
    mock_response.patches[0].apply_ok = True
    mock_response.patches[0].lint_ok = True
    mock_response.patches[0].tests_ok = True
    
    with patch("app.dgm.proposer.generate", return_value=mock_response):
        with patch.dict("os.environ", {"FF_DGM": "1"}):
            response = client.post("/api/dgm/propose?dry_run=1")
    
    assert response.status_code == 200
    data = response.json()
    
    # Should accept small change but reject large one
    assert data["count"] == 1
    assert data["patches"][0]["loc_delta"] <= 50
    assert len(data["rejected"]) == 1
    assert "exceeds maximum" in data["rejected"][0]["reason"]


def test_proposer_ff_dgm_disabled(mock_sse, mock_registry, mock_resource_guards):
    """Test that proposer returns error when FF_DGM=0."""
    
    with patch.dict("os.environ", {"FF_DGM": "0"}):
        response = client.post("/api/dgm/propose?dry_run=1")
    
    assert response.status_code == 403
    data = response.json()
    assert "error" in data
    assert "DGM system disabled" in data["error"]


def test_proposer_live_mode_blocked(mock_sse, mock_registry):
    """Test that live mode (dry_run=false) is blocked in Stage-1."""
    
    with patch.dict("os.environ", {"FF_DGM": "1"}):
        response = client.post("/api/dgm/propose?dry_run=0")
    
    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert "Live application not supported" in data["error"]


def test_proposer_resource_guards_trigger_rollback(mock_sse, mock_registry):
    """Test that resource guard violations trigger rollback."""
    
    from app.dgm.resources import ResourceGuard, ResourceStatus
    
    # Mock resource guards to return violations
    mock_violations = [
        ResourceGuard(
            resource="cpu",
            threshold=80.0,
            current=85.0,
            violated=True,
            reason="CPU usage 85.0% exceeds 80.0% threshold"
        )
    ]
    mock_status = ResourceStatus(
        cpu_percent=85.0,
        memory_mb=1000.0,
        memory_percent=50.0,
        available_memory_mb=1024.0,
        disk_usage_percent=60.0,
        load_avg_1m=2.5,
        timestamp=time.time()
    )
    
    with patch("app.dgm.resources.check_resource_guards", return_value=(False, mock_violations, mock_status)):
        with patch.dict("os.environ", {"FF_DGM": "1"}):
            response = client.post("/api/dgm/propose?dry_run=1")
    
    assert response.status_code == 503
    data = response.json()
    assert "error" in data
    assert "Resource constraints exceeded" in data["error"]


def test_allowlist_configuration_validation(mock_sse, mock_registry):
    """Test that allowlist configuration is properly validated."""
    # This is a configuration test, not an API test
    
    # Verify that DGM_ALLOWED_AREAS is configured correctly
    assert isinstance(DGM_ALLOWED_AREAS, list)
    assert len(DGM_ALLOWED_AREAS) > 0
    assert "prompts" in DGM_ALLOWED_AREAS
    assert "bandit" in DGM_ALLOWED_AREAS
    
    # Verify no obviously dangerous areas are allowed
    dangerous_areas = ["auth", "security", "admin", "billing", "keys"]
    for dangerous in dangerous_areas:
        assert dangerous not in DGM_ALLOWED_AREAS


def test_proposer_error_handling(mock_sse, mock_registry, mock_resource_guards):
    """Test that proposer handles errors gracefully."""
    
    # Mock proposer to raise an exception
    with patch("app.dgm.proposer.generate", side_effect=Exception("Proposer failure")):
        with patch.dict("os.environ", {"FF_DGM": "1"}):
            response = client.post("/api/dgm/propose?dry_run=1")
    
    # Should return 500 error with details
    assert response.status_code == 500
    data = response.json() 
    assert "error" in data


def test_registry_integration(mock_sse, mock_resource_guards):
    """Test that successful proposals are recorded in registry."""
    
    # Don't mock registry for this test - we want to verify it's called
    mock_patches = [
        MetaPatch.create("prompts", "llama-3.1-8b-instant", "Test patch", "diff content", 5)
    ]
    mock_patches[0].apply_ok = True
    mock_patches[0].lint_ok = True
    mock_patches[0].tests_ok = True
    
    mock_response = ProposalResponse(
        patches=mock_patches,
        rejected=[],
        total_generated=1,
        execution_time_ms=1000
    )
    
    with patch("app.dgm.proposer.generate", return_value=mock_response):
        with patch("app.dgm.registry.record") as mock_record:
            with patch.dict("os.environ", {"FF_DGM": "1"}):
                response = client.post("/api/dgm/propose?dry_run=1")
    
    assert response.status_code == 200
    
    # Verify registry.record was called for successful patch
    mock_record.assert_called()
    call_args = mock_record.call_args[0]  # Get positional arguments
    
    assert call_args[0] == mock_patches[0].id  # patch_id
    assert call_args[1] == "llama-3.1-8b-instant"  # origin
    assert call_args[2] == "prompts"  # area
    assert call_args[3] == "Test patch"  # notes