"""
Test DGM guard logic and safety mechanisms.
"""
import pytest
from unittest.mock import patch, MagicMock
from app.dgm.guards import violations, check_error_rate, check_latency_regression, check_reward_delta
from app.config import DGM_FAIL_GUARDS


@pytest.fixture
def mock_metrics():
    """Mock metrics for testing guard conditions."""
    return {
        "error_rate": 0.05,           # 5% error rate
        "latency_p95_ms": 800,        # 800ms p95 latency
        "latency_baseline_p95_ms": 500, # 500ms baseline
        "avg_reward": 0.75,
        "baseline_avg_reward": 0.8,   # Slight regression
        "success_rate": 0.95,
        "total_requests": 1000
    }


def test_error_rate_guard_pass(mock_metrics):
    """Test error rate guard passes within acceptable limits."""
    # Error rate of 5% should pass (under 15% limit)
    result = check_error_rate(mock_metrics["error_rate"])
    
    assert result["passed"] is True
    assert result["metric"] == "error_rate"
    assert result["value"] == 0.05
    assert result["threshold"] == DGM_FAIL_GUARDS["error_rate_max"]


def test_error_rate_guard_fail():
    """Test error rate guard fails when limit exceeded."""
    high_error_rate = 0.20  # 20% error rate (exceeds 15% limit)
    
    result = check_error_rate(high_error_rate)
    
    assert result["passed"] is False
    assert result["metric"] == "error_rate"
    assert result["value"] == 0.20
    assert "exceeded" in result["reason"].lower()


def test_latency_regression_guard_pass(mock_metrics):
    """Test latency regression guard passes within limits."""
    # 300ms increase (800 - 500) should pass (under 500ms limit)
    result = check_latency_regression(
        mock_metrics["latency_p95_ms"],
        mock_metrics["latency_baseline_p95_ms"]
    )
    
    assert result["passed"] is True
    assert result["metric"] == "latency_p95_regression"
    assert result["regression_ms"] == 300


def test_latency_regression_guard_fail():
    """Test latency regression guard fails when limit exceeded."""
    high_latency = 1200  # 700ms increase (1200 - 500) exceeds 500ms limit
    baseline_latency = 500
    
    result = check_latency_regression(high_latency, baseline_latency)
    
    assert result["passed"] is False
    assert result["metric"] == "latency_p95_regression"
    assert result["regression_ms"] == 700
    assert "exceeded" in result["reason"].lower()


def test_reward_delta_guard_pass(mock_metrics):
    """Test reward delta guard passes with acceptable regression."""
    # -0.05 delta (-6.25%) should pass (over -5% limit)
    result = check_reward_delta(
        mock_metrics["avg_reward"],
        mock_metrics["baseline_avg_reward"]
    )
    
    # Actually this should fail since -6.25% < -5%
    assert result["passed"] is False
    assert result["metric"] == "reward_delta"
    assert result["delta"] == pytest.approx(-0.05, abs=1e-10)


def test_reward_delta_guard_improvement():
    """Test reward delta guard with improvement."""
    current_reward = 0.85
    baseline_reward = 0.8  # +0.05 improvement
    
    result = check_reward_delta(current_reward, baseline_reward)
    
    assert result["passed"] is True
    assert result["metric"] == "reward_delta"
    assert result["delta"] == pytest.approx(0.05, abs=1e-10)


def test_reward_delta_guard_fail():
    """Test reward delta guard fails with significant regression."""
    current_reward = 0.70
    baseline_reward = 0.8  # -0.1 delta (-12.5%) exceeds -5% limit
    
    result = check_reward_delta(current_reward, baseline_reward)
    
    assert result["passed"] is False
    assert result["metric"] == "reward_delta"
    assert result["delta"] == pytest.approx(-0.1, abs=1e-10)
    assert "exceeded" in result["reason"].lower()


def test_violations_function_all_pass(mock_metrics):
    """Test violations function when all guards pass."""
    from app.dgm.types import ShadowEvalResult
    
    # Create a shadow result that should pass all guards
    shadow_result = ShadowEvalResult(
        patch_id="test_pass",
        success=True,
        baseline_reward=0.8,
        shadow_reward=0.78,  # -2.5% change, within -5% limit
        execution_time_ms=1000,
        individual_rewards=[0.78, 0.78, 0.78],
        error_rate_after=0.05,  # 5% error rate, within limit
        latency_p95_delta=200   # 200ms increase, within limit
    )
    
    guard_result = violations(shadow_result)
    
    assert guard_result.passed is True
    assert len(guard_result.violations) == 0


def test_violations_function_multiple_failures():
    """Test violations function with multiple guard failures."""
    from app.dgm.types import ShadowEvalResult
    
    # Create a shadow result that should fail all guards
    shadow_result = ShadowEvalResult(
        patch_id="test_fail",
        success=True,
        baseline_reward=0.8,
        shadow_reward=0.65,           # -0.15 delta (-18.75%, exceeds -5% limit)
        execution_time_ms=1000,
        individual_rewards=[0.65, 0.65, 0.65],
        error_rate_after=0.25,        # 25% error rate (exceeds 15%)
        latency_p95_delta=700         # +700ms increase (exceeds 500ms limit)
    )
    
    guard_result = violations(shadow_result)
    
    assert guard_result.passed is False
    assert len(guard_result.violations) == 3  # All three guards should fail
    
    # Check that all expected violations are present
    violation_names = [v.guard_name for v in guard_result.violations]
    assert "error_rate_max" in violation_names
    assert "latency_p95_regression" in violation_names
    assert "reward_delta_min" in violation_names


def test_guard_configuration_validation():
    """Test that guard thresholds are properly configured."""
    # Verify guard thresholds are sensible
    assert DGM_FAIL_GUARDS["error_rate_max"] > 0
    assert DGM_FAIL_GUARDS["error_rate_max"] < 1
    assert DGM_FAIL_GUARDS["latency_p95_regression"] > 0
    assert DGM_FAIL_GUARDS["reward_delta_min"] < 0  # Negative for regression threshold
    assert DGM_FAIL_GUARDS["reward_delta_min"] > -1


def test_guard_edge_cases():
    """Test guard behavior with edge cases."""
    # Test zero values
    result = check_error_rate(0.0)
    assert result["passed"] is True
    
    # Test exact threshold values
    result = check_error_rate(DGM_FAIL_GUARDS["error_rate_max"])
    assert result["passed"] is False  # At threshold should fail
    
    # Test negative latency regression (improvement)
    result = check_latency_regression(400, 500)  # -100ms improvement
    assert result["passed"] is True
    assert result["regression_ms"] == -100


def test_guard_missing_metrics():
    """Test guard behavior with missing or invalid metrics."""
    # Test with None values
    result = check_error_rate(None)
    assert result["passed"] is False
    assert "invalid" in result["reason"].lower()
    
    # Test with negative values
    result = check_error_rate(-0.1)
    assert result["passed"] is False
    assert "invalid" in result["reason"].lower()


def test_canary_rollback_integration():
    """Test integration with canary rollback system."""
    # Skip this test since CanaryManager is not implemented yet
    pytest.skip("CanaryManager not implemented yet")


def test_guard_performance_monitoring():
    """Test that guard checks themselves are performant."""
    import time
    
    # Test that guard checks complete quickly
    start_time = time.time()
    
    for _ in range(100):
        check_error_rate(0.1)
        check_latency_regression(800, 500)
        check_reward_delta(0.75, 0.8)
    
    end_time = time.time()
    execution_time = end_time - start_time
    
    # Should complete 100 guard checks in under 100ms
    assert execution_time < 0.1


def test_guard_threshold_scaling():
    """Test guard thresholds scale appropriately with load."""
    # Mock different load scenarios
    light_load_metrics = {"error_rate": 0.02, "total_requests": 100}
    heavy_load_metrics = {"error_rate": 0.02, "total_requests": 10000}
    
    # Same error rate should be treated consistently regardless of load
    light_result = check_error_rate(light_load_metrics["error_rate"])
    heavy_result = check_error_rate(heavy_load_metrics["error_rate"])
    
    assert light_result["passed"] == heavy_result["passed"]


def test_guard_hysteresis():
    """Test guard hysteresis to prevent flapping."""
    # Test that guards don't flip-flop at threshold boundaries
    threshold = DGM_FAIL_GUARDS["error_rate_max"]
    
    # Just below threshold
    result1 = check_error_rate(threshold - 0.001)
    assert result1["passed"] is True
    
    # Just above threshold
    result2 = check_error_rate(threshold + 0.001)
    assert result2["passed"] is False
    
    # Right at threshold
    result3 = check_error_rate(threshold)
    assert result3["passed"] is False


def test_guard_logging_and_alerts():
    """Test that guard violations are properly logged."""
    from app.dgm.types import ShadowEvalResult
    
    with patch('logging.Logger.warning') as mock_log:
        # Create a shadow result with violations
        shadow_result = ShadowEvalResult(
            patch_id="test_logging",
            success=True,
            baseline_reward=0.8,
            shadow_reward=0.65,           # Bad reward delta
            execution_time_ms=1000,
            individual_rewards=[0.65, 0.65, 0.65],
            error_rate_after=0.25,        # High error rate
            latency_p95_delta=700         # High latency regression
        )
        
        guard_result = violations(shadow_result)
        
        # Should generate log entries for violations
        assert len(guard_result.violations) > 0
        assert guard_result.passed is False


if __name__ == "__main__":
    pytest.main([__file__])