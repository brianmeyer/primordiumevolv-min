"""
Test DGM selector and ranking functionality.
"""
import pytest
from unittest.mock import patch, MagicMock
from app.dgm.selector import rank_and_pick, get_top_k_patches, _compute_rank_score
from app.dgm.types import GuardResult
from app.dgm.types import MetaPatch, ShadowEvalResult


@pytest.fixture
def sample_patches():
    """Create sample patches for testing."""
    return [
        MetaPatch(
            id="patch_high_reward",
            area="prompts",
            origin="test",
            notes="High reward patch",
            diff="--- a/test1.md\n+++ b/test1.md\n@@ -1,1 +1,2 @@\n test\n+high quality",
            loc_delta=1
        ),
        MetaPatch(
            id="patch_medium_reward",
            area="bandit",
            origin="test",
            notes="Medium reward patch",
            diff="--- a/test2.py\n+++ b/test2.py\n@@ -1,1 +1,2 @@\n eps=0.3\n+# improvement",
            loc_delta=1
        ),
        MetaPatch(
            id="patch_low_reward",
            area="ui_metrics",
            origin="test",
            notes="Low reward patch",
            diff="--- a/test3.js\n+++ b/test3.js\n@@ -1,1 +1,2 @@\n var x = 1\n+// comment",
            loc_delta=1
        )
    ]


@pytest.fixture
def sample_shadow_results():
    """Create sample shadow evaluation results."""
    return [
        ShadowEvalResult(
            patch_id="patch_high_reward",
            success=True,
            baseline_reward=0.7,
            shadow_reward=0.9,        # +0.2 improvement
            execution_time_ms=1000,
            individual_rewards=[0.9, 0.85, 0.95]
        ),
        ShadowEvalResult(
            patch_id="patch_medium_reward",
            success=True,
            baseline_reward=0.6,
            shadow_reward=0.75,       # +0.15 improvement
            execution_time_ms=1200,
            individual_rewards=[0.75, 0.7, 0.8]
        ),
        ShadowEvalResult(
            patch_id="patch_low_reward",
            success=True,
            baseline_reward=0.8,
            shadow_reward=0.82,       # +0.02 improvement
            execution_time_ms=800,
            individual_rewards=[0.82, 0.8, 0.84]
        )
    ]


def test_compute_rank_score_basic():
    """Test basic patch score calculation."""
    shadow_result = ShadowEvalResult(
        patch_id="test_patch",
        success=True,
        baseline_reward=0.7,
        shadow_reward=0.85,
        execution_time_ms=1000,
        individual_rewards=[0.85, 0.8, 0.9]
    )
    
    guard_result = GuardResult(
        passed=True,
        violations=[],
        resource_status={}
    )
    
    score = _compute_rank_score(shadow_result, guard_result)
    
    assert score > 0
    assert isinstance(score, float)
    # Score should be influenced by reward delta
    lower_shadow = ShadowEvalResult(
        patch_id="lower_patch",
        success=True,
        baseline_reward=0.7,
        shadow_reward=0.75,  # Lower improvement
        execution_time_ms=1000,
        individual_rewards=[0.75, 0.7, 0.8]
    )
    lower_score = _compute_rank_score(lower_shadow, guard_result)
    assert score > lower_score


def test_calculate_patch_score_failed_eval():
    """Test patch score for failed evaluations."""
    failed_result = ShadowEvalResult(
        patch_id="failed_patch",
        success=False,
        baseline_reward=None,
        shadow_reward=None,
        execution_time_ms=0,
        individual_rewards=[],
        error="Evaluation failed"
    )
    
    score = calculate_patch_score(failed_result)
    
    # Failed evaluations should get very low scores
    assert score <= 0


def test_calculate_patch_score_regression():
    """Test patch score for performance regressions."""
    regression_result = ShadowEvalResult(
        patch_id="regression_patch",
        success=True,
        baseline_reward=0.8,
        shadow_reward=0.7,       # -0.1 regression
        execution_time_ms=1500,
        individual_rewards=[0.7, 0.65, 0.75]
    )
    
    score = calculate_patch_score(regression_result)
    
    # Regressions should get negative or very low scores
    assert score <= 0.1


def test_calculate_patch_score_execution_time_penalty():
    """Test that execution time affects score calculation."""
    fast_result = ShadowEvalResult(
        patch_id="fast_patch",
        success=True,
        baseline_reward=0.7,
        shadow_reward=0.8,
        execution_time_ms=500,   # Fast execution
        individual_rewards=[0.8, 0.75, 0.85]
    )
    
    slow_result = ShadowEvalResult(
        patch_id="slow_patch",
        success=True,
        baseline_reward=0.7,
        shadow_reward=0.8,
        execution_time_ms=5000,  # Slow execution
        individual_rewards=[0.8, 0.75, 0.85]
    )
    
    fast_score = calculate_patch_score(fast_result)
    slow_score = calculate_patch_score(slow_result)
    
    # Faster execution should result in higher score
    assert fast_score > slow_score


def test_rank_patches_by_score(sample_patches, sample_shadow_results):
    """Test ranking patches by their scores."""
    with patch('app.dgm.eval.get_shadow_eval') as mock_get_eval:
        # Mock shadow eval retrieval
        mock_get_eval.side_effect = lambda patch_id: next(
            (result for result in sample_shadow_results if result.patch_id == patch_id),
            None
        )
        
        ranked_patches = rank_patches(sample_patches)
        
        assert len(ranked_patches) == 3
        
        # Should be ranked by score (highest first)
        assert ranked_patches[0].id == "patch_high_reward"  # Best improvement
        assert ranked_patches[1].id == "patch_medium_reward"  # Medium improvement
        assert ranked_patches[2].id == "patch_low_reward"  # Smallest improvement


def test_rank_patches_no_shadow_results(sample_patches):
    """Test ranking patches when no shadow evaluation results exist."""
    with patch('app.dgm.eval.get_shadow_eval') as mock_get_eval:
        # No shadow eval results available
        mock_get_eval.return_value = None
        
        ranked_patches = rank_patches(sample_patches)
        
        # Should return patches in original order or some default ranking
        assert len(ranked_patches) == len(sample_patches)
        assert all(patch.id in [p.id for p in sample_patches] for patch in ranked_patches)


def test_select_best_patches(sample_patches, sample_shadow_results):
    """Test selecting top N patches."""
    with patch('app.dgm.eval.get_shadow_eval') as mock_get_eval:
        mock_get_eval.side_effect = lambda patch_id: next(
            (result for result in sample_shadow_results if result.patch_id == patch_id),
            None
        )
        
        # Select top 2 patches
        best_patches = select_best_patches(sample_patches, top_n=2)
        
        assert len(best_patches) == 2
        assert best_patches[0].id == "patch_high_reward"
        assert best_patches[1].id == "patch_medium_reward"


def test_select_best_patches_min_score_threshold(sample_patches, sample_shadow_results):
    """Test selecting patches with minimum score threshold."""
    with patch('app.dgm.eval.get_shadow_eval') as mock_get_eval, \
         patch('app.dgm.selector.calculate_patch_score') as mock_score:
        
        mock_get_eval.side_effect = lambda patch_id: next(
            (result for result in sample_shadow_results if result.patch_id == patch_id),
            None
        )
        
        # Mock scores with one below threshold
        mock_score.side_effect = [0.8, 0.6, 0.3]  # Third patch below 0.5 threshold
        
        best_patches = select_best_patches(sample_patches, min_score=0.5)
        
        # Should exclude the patch with score 0.3
        assert len(best_patches) == 2
        assert all(patch.id != "patch_low_reward" for patch in best_patches)


def test_ranking_stability():
    """Test that ranking is stable for patches with similar scores."""
    similar_results = [
        ShadowEvalResult(
            patch_id=f"patch_{i}",
            success=True,
            baseline_reward=0.7,
            shadow_reward=0.75,  # Same improvement
            execution_time_ms=1000,
            individual_rewards=[0.75] * 3
        )
        for i in range(5)
    ]
    
    patches = [
        MetaPatch(
            id=f"patch_{i}",
            area="prompts",
            origin="test",
            notes=f"Patch {i}",
            diff=f"test diff {i}",
            loc_delta=1
        )
        for i in range(5)
    ]
    
    with patch('app.dgm.eval.get_shadow_eval') as mock_get_eval:
        mock_get_eval.side_effect = lambda patch_id: next(
            (result for result in similar_results if result.patch_id == patch_id),
            None
        )
        
        # Rank multiple times
        ranking1 = rank_patches(patches)
        ranking2 = rank_patches(patches)
        
        # Should get consistent ordering
        assert [p.id for p in ranking1] == [p.id for p in ranking2]


def test_ranking_with_mixed_success_failure():
    """Test ranking when some patches have failed evaluations."""
    mixed_results = [
        ShadowEvalResult(
            patch_id="success_patch",
            success=True,
            baseline_reward=0.7,
            shadow_reward=0.8,
            execution_time_ms=1000,
            individual_rewards=[0.8, 0.75, 0.85]
        ),
        ShadowEvalResult(
            patch_id="failed_patch",
            success=False,
            baseline_reward=None,
            shadow_reward=None,
            execution_time_ms=0,
            individual_rewards=[],
            error="Failed"
        )
    ]
    
    patches = [
        MetaPatch(id="success_patch", area="prompts", origin="test", notes="Success", diff="diff1", loc_delta=1),
        MetaPatch(id="failed_patch", area="prompts", origin="test", notes="Failed", diff="diff2", loc_delta=1)
    ]
    
    with patch('app.dgm.eval.get_shadow_eval') as mock_get_eval:
        mock_get_eval.side_effect = lambda patch_id: next(
            (result for result in mixed_results if result.patch_id == patch_id),
            None
        )
        
        ranked_patches = rank_patches(patches)
        
        # Successful patch should rank higher than failed patch
        assert ranked_patches[0].id == "success_patch"
        assert ranked_patches[1].id == "failed_patch"


def test_ranking_performance_scalability():
    """Test ranking performance with large number of patches."""
    import time
    
    # Create 100 patches
    large_patch_set = [
        MetaPatch(
            id=f"perf_patch_{i}",
            area="prompts",
            origin="test",
            notes=f"Performance patch {i}",
            diff=f"test diff {i}",
            loc_delta=1
        )
        for i in range(100)
    ]
    
    # Mock shadow results
    large_results = [
        ShadowEvalResult(
            patch_id=f"perf_patch_{i}",
            success=True,
            baseline_reward=0.7,
            shadow_reward=0.7 + (i % 20) * 0.01,  # Varying scores
            execution_time_ms=1000 + i * 10,
            individual_rewards=[0.7 + (i % 20) * 0.01] * 3
        )
        for i in range(100)
    ]
    
    with patch('app.dgm.eval.get_shadow_eval') as mock_get_eval:
        mock_get_eval.side_effect = lambda patch_id: next(
            (result for result in large_results if result.patch_id == patch_id),
            None
        )
        
        start_time = time.time()
        ranked_patches = rank_patches(large_patch_set)
        end_time = time.time()
        
        # Should complete ranking in reasonable time (under 1 second)
        assert end_time - start_time < 1.0
        assert len(ranked_patches) == 100


def test_ranking_with_area_preferences():
    """Test ranking with area-based preferences."""
    area_patches = [
        MetaPatch(id="prompt_patch", area="prompts", origin="test", notes="Prompt", diff="diff1", loc_delta=1),
        MetaPatch(id="bandit_patch", area="bandit", origin="test", notes="Bandit", diff="diff2", loc_delta=1),
        MetaPatch(id="ui_patch", area="ui_metrics", origin="test", notes="UI", diff="diff3", loc_delta=1)
    ]
    
    # All have same evaluation results
    uniform_results = [
        ShadowEvalResult(
            patch_id=patch.id,
            success=True,
            baseline_reward=0.7,
            shadow_reward=0.8,
            execution_time_ms=1000,
            individual_rewards=[0.8] * 3
        )
        for patch in area_patches
    ]
    
    with patch('app.dgm.eval.get_shadow_eval') as mock_get_eval:
        mock_get_eval.side_effect = lambda patch_id: next(
            (result for result in uniform_results if result.patch_id == patch_id),
            None
        )
        
        # Test with area preferences
        ranked_patches = rank_patches(area_patches, area_weights={"prompts": 1.5, "bandit": 1.2, "ui_metrics": 1.0})
        
        # Prompts should rank highest due to higher weight
        assert ranked_patches[0].area == "prompts"


if __name__ == "__main__":
    pytest.main([__file__])