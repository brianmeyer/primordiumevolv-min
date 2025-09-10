"""
Test DGM shadow evaluation and metrics functionality.
"""
import pytest
from unittest.mock import patch, MagicMock
from app.dgm.eval import shadow_eval, batch_shadow_eval, register_shadow_eval, get_shadow_eval
from app.dgm.types import MetaPatch, ShadowEvalResult


@pytest.fixture
def sample_patch():
    """Create a sample MetaPatch for testing."""
    return MetaPatch(
        id="shadow_test_001",
        area="prompts",
        origin="test",
        notes="Shadow eval test patch",
        diff="""--- a/prompts/test.md
+++ b/prompts/test.md
@@ -1,2 +1,3 @@
 # Test Prompt
 This is a test.
+Improved prompt text.""",
        loc_delta=1
    )


def test_shadow_eval_basic_functionality(sample_patch):
    """Test basic shadow evaluation functionality."""
    with patch('app.dgm.apply.try_patch') as mock_apply, \
         patch('app.meta.runner.meta_run') as mock_meta_run:
        
        # Mock successful patch application
        mock_apply.return_value = MagicMock(success=True, apply_ok=True)
        
        # Mock meta run results
        mock_meta_run.return_value = {
            "rewards": [0.7, 0.8, 0.75],
            "avg_reward": 0.75,
            "execution_time_ms": 1200,
            "success": True
        }
        
        result = shadow_eval(sample_patch, runs=3)
        
        assert isinstance(result, ShadowEvalResult)
        assert result.patch_id == "shadow_test_001"
        assert result.success is True
        assert result.baseline_reward is not None
        assert result.shadow_reward is not None
        assert result.execution_time_ms > 0
        assert len(result.individual_rewards) == 3


def test_shadow_eval_patch_application_failure(sample_patch):
    """Test shadow eval when patch application fails."""
    with patch('app.dgm.apply.try_patch') as mock_apply:
        # Mock patch application failure
        mock_apply.return_value = MagicMock(
            success=False, 
            apply_ok=False,
            stderr="Patch failed to apply"
        )
        
        result = shadow_eval(sample_patch, runs=3)
        
        assert result.success is False
        assert "failed to apply" in result.error.lower()
        assert result.shadow_reward is None


def test_shadow_eval_timeout_handling(sample_patch):
    """Test shadow eval timeout handling."""
    with patch('app.dgm.apply.try_patch') as mock_apply, \
         patch('app.meta.runner.meta_run') as mock_meta_run:
        
        mock_apply.return_value = MagicMock(success=True, apply_ok=True)
        
        # Mock timeout
        mock_meta_run.side_effect = TimeoutError("Evaluation timed out")
        
        result = shadow_eval(sample_patch, runs=1, timeout=5)
        
        assert result.success is False
        assert "timeout" in result.error.lower()


def test_shadow_eval_reward_calculation(sample_patch):
    """Test reward calculation and comparison."""
    with patch('app.dgm.apply.try_patch') as mock_apply, \
         patch('app.meta.runner.meta_run') as mock_meta_run:
        
        mock_apply.return_value = MagicMock(success=True, apply_ok=True)
        
        # Mock baseline and shadow results
        baseline_rewards = [0.6, 0.65, 0.7]  # avg: 0.65
        shadow_rewards = [0.75, 0.8, 0.85]   # avg: 0.8
        
        mock_meta_run.side_effect = [
            {"rewards": baseline_rewards, "avg_reward": 0.65, "execution_time_ms": 1000, "success": True},
            {"rewards": shadow_rewards, "avg_reward": 0.8, "execution_time_ms": 1100, "success": True}
        ]
        
        result = shadow_eval(sample_patch, runs=3)
        
        assert result.success is True
        assert result.baseline_reward == 0.65
        assert result.shadow_reward == 0.8
        assert result.reward_delta == 0.15  # 0.8 - 0.65
        assert result.improvement_pct == pytest.approx(23.08, rel=1e-2)  # (0.15 / 0.65) * 100


def test_shadow_eval_regression_detection(sample_patch):
    """Test detection of performance regressions."""
    with patch('app.dgm.apply.try_patch') as mock_apply, \
         patch('app.meta.runner.meta_run') as mock_meta_run:
        
        mock_apply.return_value = MagicMock(success=True, apply_ok=True)
        
        # Mock regression scenario
        baseline_rewards = [0.8, 0.85, 0.9]   # avg: 0.85
        shadow_rewards = [0.6, 0.65, 0.7]     # avg: 0.65 (regression)
        
        mock_meta_run.side_effect = [
            {"rewards": baseline_rewards, "avg_reward": 0.85, "execution_time_ms": 1000, "success": True},
            {"rewards": shadow_rewards, "avg_reward": 0.65, "execution_time_ms": 1200, "success": True}
        ]
        
        result = shadow_eval(sample_patch, runs=3)
        
        assert result.success is True
        assert result.reward_delta < 0  # Negative delta indicates regression
        assert result.improvement_pct < 0


def test_batch_shadow_eval(sample_patch):
    """Test batch shadow evaluation of multiple patches."""
    patches = [
        MetaPatch(
            id=f"batch_shadow_{i}",
            area="prompts",
            origin="test",
            notes=f"Batch shadow patch {i}",
            diff=f"--- a/test{i}.md\n+++ b/test{i}.md\n@@ -1,1 +1,2 @@\n test\n+improvement {i}",
            loc_delta=1
        )
        for i in range(3)
    ]
    
    with patch('app.dgm.eval.shadow_eval') as mock_shadow_eval:
        # Mock individual shadow eval results
        mock_shadow_eval.side_effect = [
            ShadowEvalResult(
                patch_id=f"batch_shadow_{i}",
                success=True,
                baseline_reward=0.6,
                shadow_reward=0.7 + i * 0.05,
                execution_time_ms=1000 + i * 100,
                individual_rewards=[0.7 + i * 0.05] * 3
            )
            for i in range(3)
        ]
        
        results = batch_shadow_eval(patches, runs=3)
        
        assert len(results) == 3
        assert all(isinstance(r, ShadowEvalResult) for r in results)
        assert all(r.success for r in results)
        assert results[0].shadow_reward < results[1].shadow_reward < results[2].shadow_reward


def test_shadow_eval_registry():
    """Test shadow evaluation result registry."""
    # Clear registry first
    from app.dgm.eval import clear_shadow_eval_registry
    clear_shadow_eval_registry()
    
    test_result = ShadowEvalResult(
        patch_id="registry_test_001",
        success=True,
        baseline_reward=0.7,
        shadow_reward=0.8,
        execution_time_ms=1500,
        individual_rewards=[0.8, 0.8, 0.8]
    )
    
    # Register result
    register_shadow_eval(test_result)
    
    # Retrieve result
    retrieved = get_shadow_eval("registry_test_001")
    
    assert retrieved is not None
    assert retrieved.patch_id == "registry_test_001"
    assert retrieved.shadow_reward == 0.8
    
    # Test retrieval of non-existent result
    missing = get_shadow_eval("nonexistent_patch")
    assert missing is None


def test_shadow_eval_statistics():
    """Test shadow evaluation statistics and aggregation."""
    from app.dgm.eval import get_registry_stats
    
    # Clear and populate registry
    from app.dgm.eval import clear_shadow_eval_registry
    clear_shadow_eval_registry()
    
    test_results = [
        ShadowEvalResult(
            patch_id=f"stats_test_{i}",
            success=True,
            baseline_reward=0.6,
            shadow_reward=0.6 + i * 0.1,
            execution_time_ms=1000 + i * 200,
            individual_rewards=[0.6 + i * 0.1] * 3
        )
        for i in range(5)
    ]
    
    for result in test_results:
        register_shadow_eval(result)
    
    stats = get_registry_stats()
    
    assert stats["total"] == 5
    assert stats["completed"] == 5
    assert stats["improvements"] > 0  # Some patches should show improvement
    assert "avg_reward_delta" in stats
    assert "avg_execution_time_ms" in stats


def test_shadow_eval_error_scenarios(sample_patch):
    """Test various error scenarios in shadow evaluation."""
    # Test meta run failure
    with patch('app.dgm.apply.try_patch') as mock_apply, \
         patch('app.meta.runner.meta_run') as mock_meta_run:
        
        mock_apply.return_value = MagicMock(success=True, apply_ok=True)
        mock_meta_run.side_effect = Exception("Meta run failed")
        
        result = shadow_eval(sample_patch, runs=1)
        
        assert result.success is False
        assert "failed" in result.error.lower()


def test_shadow_eval_performance_metrics(sample_patch):
    """Test performance metric collection during shadow eval."""
    with patch('app.dgm.apply.try_patch') as mock_apply, \
         patch('app.meta.runner.meta_run') as mock_meta_run:
        
        mock_apply.return_value = MagicMock(success=True, apply_ok=True)
        
        # Mock different execution times
        mock_meta_run.side_effect = [
            {"rewards": [0.6], "avg_reward": 0.6, "execution_time_ms": 1000, "success": True},
            {"rewards": [0.8], "avg_reward": 0.8, "execution_time_ms": 2000, "success": True}
        ]
        
        result = shadow_eval(sample_patch, runs=1)
        
        assert result.success is True
        assert result.execution_time_ms > 0
        # Shadow should include both baseline and shadow execution time
        assert result.execution_time_ms >= 2000


def test_shadow_eval_confidence_intervals(sample_patch):
    """Test confidence interval calculation for shadow eval results."""
    with patch('app.dgm.apply.try_patch') as mock_apply, \
         patch('app.meta.runner.meta_run') as mock_meta_run:
        
        mock_apply.return_value = MagicMock(success=True, apply_ok=True)
        
        # Mock results with variance
        baseline_rewards = [0.5, 0.6, 0.7, 0.8, 0.9]  # High variance
        shadow_rewards = [0.75, 0.8, 0.85, 0.9, 0.95]   # Lower variance, higher mean
        
        mock_meta_run.side_effect = [
            {"rewards": baseline_rewards, "avg_reward": 0.7, "execution_time_ms": 1000, "success": True},
            {"rewards": shadow_rewards, "avg_reward": 0.85, "execution_time_ms": 1100, "success": True}
        ]
        
        result = shadow_eval(sample_patch, runs=5)
        
        assert result.success is True
        assert len(result.individual_rewards) == 5
        assert result.baseline_reward == 0.7
        assert result.shadow_reward == 0.85


if __name__ == "__main__":
    pytest.main([__file__])