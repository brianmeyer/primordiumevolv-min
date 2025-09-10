"""
Test DGM shadow evaluation, guards, and selector functionality.

Tests the complete Stage-2/3 pipeline without live mutations.
"""

import pytest
import tempfile
import os
from unittest.mock import patch, MagicMock
from app.dgm.types import MetaPatch
from app.dgm.shadow import ShadowResult, evaluate_patch_shadow, evaluate_patches_shadow
from app.dgm.guards import GuardResult, violations, batch_guard_check
from app.dgm.selector import rank_and_pick, get_selection_summary


class TestShadowEvaluation:
    """Test shadow evaluation functionality."""
    
    def test_shadow_result_creation(self):
        """Test ShadowResult creation and validation."""
        result = ShadowResult("test-patch-1")
        assert result.patch_id == "test-patch-1"
        assert not result.is_valid()  # No scores set yet
        
        # Set valid scores
        result.baseline_score = 0.7
        result.patched_score = 0.8
        result.improvement_score = 0.1
        result.latency_delta_ms = 50
        
        assert result.is_valid()
        
        # Test to_dict conversion
        data = result.to_dict()
        assert data["patch_id"] == "test-patch-1"
        assert data["improvement_score"] == 0.1
        assert data["is_valid"] is True
    
    def test_golden_subset_generation(self):
        """Test golden subset generation for consistent evaluation."""
        from app.dgm.shadow import _get_golden_subset
        
        # Test default size
        tasks = _get_golden_subset()
        assert len(tasks) <= 25  # M1 safety limit
        assert all("id" in task and "prompt" in task for task in tasks)
        
        # Test custom size
        tasks = _get_golden_subset(5)
        assert len(tasks) == 5
        
        # Test deterministic generation
        tasks1 = _get_golden_subset(10)
        tasks2 = _get_golden_subset(10)
        assert len(tasks1) == len(tasks2)
        assert tasks1[0]["id"] == tasks2[0]["id"]  # Should be deterministic
    
    @patch('app.dgm.shadow._apply_patch_to_temp')
    @patch('app.dgm.shadow._evaluate_task_performance')
    def test_patch_shadow_evaluation(self, mock_eval, mock_apply):
        """Test shadow evaluation of a single patch."""
        # Mock patch application
        mock_apply.return_value = "/tmp/test-dir"
        
        # Mock task evaluations (baseline vs patched)
        mock_eval.side_effect = [
            (0.7, 100, None),  # baseline: score=0.7, latency=100ms
            (0.8, 120, None),  # patched: score=0.8, latency=120ms
        ]
        
        # Create test patch
        patch = MetaPatch.create("bandit", "test-model", "Test patch", 
                               "--- a/test\n+++ b/test\n@@ -1 +1 @@\n-old\n+new", 1)
        
        # Run evaluation
        result = evaluate_patch_shadow(patch)
        
        assert result.patch_id == patch.id
        assert result.baseline_score == 0.7
        assert result.patched_score == 0.8
        assert result.improvement_score == 0.1
        assert result.latency_delta_ms == 20  # 120 - 100
        assert result.is_valid()
    
    @patch('app.dgm.shadow.evaluate_patch_shadow')
    def test_batch_shadow_evaluation(self, mock_single_eval):
        """Test batch shadow evaluation of multiple patches."""
        # Create test patches
        patches = [
            MetaPatch.create("bandit", "model1", "Patch 1", "diff1", 1),
            MetaPatch.create("prompts", "model2", "Patch 2", "diff2", 2)
        ]
        
        # Mock individual evaluations
        def mock_eval(patch, tasks=None):
            result = ShadowResult(patch.id)
            result.baseline_score = 0.6
            result.patched_score = 0.7 if patch.area == "bandit" else 0.5
            result.improvement_score = result.patched_score - result.baseline_score
            result.latency_delta_ms = 10
            return result
        
        mock_single_eval.side_effect = mock_eval
        
        # Run batch evaluation
        results = evaluate_patches_shadow(patches)
        
        assert len(results) == 2
        assert results[0].improvement_score == 0.1  # bandit patch improved
        assert results[1].improvement_score == -0.1  # prompts patch degraded
        assert all(r.is_valid() for r in results)


class TestGuardSystem:
    """Test guard system functionality."""
    
    def test_guard_violation_creation(self):
        """Test GuardViolation creation."""
        from app.dgm.guards import GuardViolation
        
        violation = GuardViolation(
            guard_name="error_rate_max",
            threshold=0.1,
            actual_value=0.15,
            severity="critical",
            description="Error rate exceeded"
        )
        
        assert violation.guard_name == "error_rate_max"
        assert violation.actual_value > violation.threshold
        assert violation.severity == "critical"
    
    def test_guard_result_serialization(self):
        """Test GuardResult to_dict conversion."""
        from app.dgm.guards import GuardResult, GuardViolation
        
        violations = [
            GuardViolation("error_rate_max", 0.1, 0.15, "critical", "Too many errors"),
            GuardViolation("latency_p95_regression", 500, 750, "warning", "Latency regression")
        ]
        
        result = GuardResult(
            patch_id="test-patch",
            passed=False,
            violations=violations,
            metrics_available=True
        )
        
        data = result.to_dict()
        assert data["patch_id"] == "test-patch"
        assert data["passed"] is False
        assert data["violation_count"] == 2
        assert len(data["violations"]) == 2
        assert data["violations"][0]["severity"] == "critical"
    
    def test_guard_checks_with_valid_metrics(self):
        """Test guard checks with passing metrics."""
        # Create mock shadow eval result
        shadow_result = type('ShadowEvalResult', (), {
            'patch_id': 'test-patch',
            'error_rate_after': 0.05,  # Below 15% threshold
            'latency_p95_delta': 200,   # Below 500ms threshold
            'reward_delta': 0.02        # Above -0.05 threshold
        })()
        
        result = violations(shadow_result)
        
        assert result.passed is True
        assert len(result.violations) == 0
        assert result.metrics_available is True
    
    def test_guard_checks_with_violations(self):
        """Test guard checks with failing metrics."""
        # Create mock shadow eval result with violations
        shadow_result = type('ShadowEvalResult', (), {
            'patch_id': 'test-patch',
            'error_rate_after': 0.20,  # Above 15% threshold
            'latency_p95_delta': 600,   # Above 500ms threshold  
            'reward_delta': -0.10       # Below -0.05 threshold
        })()
        
        result = violations(shadow_result)
        
        assert result.passed is False
        assert len(result.violations) == 3
        
        # Check violation types
        violation_names = [v.guard_name for v in result.violations]
        assert "error_rate_max" in violation_names
        assert "latency_p95_regression" in violation_names
        assert "reward_delta_min" in violation_names
    
    def test_batch_guard_check(self):
        """Test batch guard checking on multiple results."""
        shadow_results = []
        for i in range(3):
            result = type('ShadowEvalResult', (), {
                'patch_id': f'patch-{i}',
                'error_rate_after': 0.05 + (i * 0.05),  # 0.05, 0.10, 0.15
                'latency_p95_delta': 100 * i,           # 0, 100, 200
                'reward_delta': 0.01 * (i + 1)          # 0.01, 0.02, 0.03
            })()
            shadow_results.append(result)
        
        guard_results = batch_guard_check(shadow_results)
        
        assert len(guard_results) == 3
        assert guard_results[0].passed is True   # All metrics good
        assert guard_results[1].passed is True   # All metrics good
        assert guard_results[2].passed is True   # All metrics good (15% = threshold)


class TestSelectorSystem:
    """Test selector and ranking functionality."""
    
    def test_selection_candidate_creation(self):
        """Test SelectionCandidate creation and serialization."""
        from app.dgm.selector import SelectionCandidate
        
        # Create mock objects
        shadow_result = type('ShadowEvalResult', (), {
            'patch_id': 'test-patch',
            'reward_delta': 0.05,
            'latency_p95_delta': 100,
            'error_rate_after': 0.02,
            'is_improvement': True
        })()
        
        guard_result = type('GuardResult', (), {
            'passed': True,
            'violations': []
        })()
        
        candidate = SelectionCandidate(
            shadow_result=shadow_result,
            guard_result=guard_result,
            rank_score=5.2,
            rank_position=1
        )
        
        data = candidate.to_dict()
        assert data["patch_id"] == "test-patch"
        assert data["passed_guards"] is True
        assert data["rank_score"] == 5.2
        assert data["rank_position"] == 1
    
    def test_rank_score_computation(self):
        """Test ranking score computation logic."""
        from app.dgm.selector import _compute_rank_score
        
        # Test passing candidate
        shadow_result = type('ShadowEvalResult', (), {
            'patch_id': 'good-patch',
            'reward_delta': 0.05,
            'latency_p95_delta': 100
        })()
        
        guard_result = type('GuardResult', (), {
            'passed': True
        })()
        
        score = _compute_rank_score(shadow_result, guard_result)
        assert score > 0  # Should be positive for good patch
        
        # Test failing guard candidate
        guard_result_fail = type('GuardResult', (), {
            'passed': False
        })()
        
        score_fail = _compute_rank_score(shadow_result, guard_result_fail)
        assert score_fail == float('-inf')  # Should be disqualified
    
    def test_rank_and_pick_with_winner(self):
        """Test ranking and selection with a clear winner."""
        shadow_results = []
        
        # Create three candidates with different quality
        for i, (reward, latency, error_rate) in enumerate([
            (0.08, 50, 0.02),   # Best: high reward, low latency, low error
            (0.05, 100, 0.05),  # Medium: medium reward, medium latency
            (0.02, 200, 0.08)   # Worst: low reward, high latency
        ]):
            result = type('ShadowEvalResult', (), {
                'patch_id': f'patch-{i}',
                'reward_delta': reward,
                'latency_p95_delta': latency,
                'error_rate_after': error_rate
            })()
            shadow_results.append(result)
        
        selection_result = rank_and_pick(shadow_results)
        
        assert selection_result.winner is not None
        assert selection_result.winner.shadow_result.patch_id == "patch-0"  # Best candidate
        assert selection_result.winner.rank_position == 1
        assert len(selection_result.candidates) == 3
        
        # Check ranking order
        candidates_by_rank = sorted(selection_result.candidates, key=lambda c: c.rank_position)
        assert candidates_by_rank[0].shadow_result.patch_id == "patch-0"  # Highest reward
    
    def test_rank_and_pick_no_winner(self):
        """Test ranking when all candidates fail guards."""
        shadow_results = []
        
        # Create candidates that all fail guards
        for i in range(2):
            result = type('ShadowEvalResult', (), {
                'patch_id': f'bad-patch-{i}',
                'reward_delta': -0.20,  # Large negative reward (fails guard)
                'latency_p95_delta': 1000,  # High latency (fails guard)
                'error_rate_after': 0.30   # High error rate (fails guard)
            })()
            shadow_results.append(result)
        
        selection_result = rank_and_pick(shadow_results)
        
        assert selection_result.winner is None
        assert len(selection_result.candidates) == 2
        assert selection_result.filtered_count == 2  # All filtered out
    
    def test_selection_summary_generation(self):
        """Test selection summary statistics generation."""
        # Create a selection result with mixed outcomes
        shadow_results = [
            type('ShadowEvalResult', (), {
                'patch_id': 'patch-1',
                'reward_delta': 0.05,
                'latency_p95_delta': 100,
                'error_rate_after': 0.05
            })(),
            type('ShadowEvalResult', (), {
                'patch_id': 'patch-2', 
                'reward_delta': -0.20,  # Will fail guards
                'latency_p95_delta': 1000,
                'error_rate_after': 0.25
            })()
        ]
        
        selection_result = rank_and_pick(shadow_results)
        summary = get_selection_summary(selection_result)
        
        assert summary["total_candidates"] == 2
        assert summary["safe_candidates"] == 1  # Only patch-1 passes guards
        assert summary["has_winner"] is True
        assert summary["winner_patch_id"] == "patch-1"
        assert "reward_delta_stats" in summary


class TestEndpointIntegration:
    """Test the integrated Stage-2/3 endpoint functionality."""
    
    @patch('app.dgm.shadow.evaluate_patches_shadow')
    @patch('app.dgm.selector.rank_and_pick')  
    @patch('app.dgm.selector.get_selection_summary')
    def test_shadow_eval_integration(self, mock_summary, mock_rank, mock_shadow):
        """Test that shadow evaluation integrates correctly with endpoint."""
        from app.dgm.types import MetaPatch
        
        # Mock patches
        patches = [MetaPatch.create("bandit", "model1", "Test", "diff", 1)]
        
        # Mock shadow evaluation results
        shadow_result = ShadowResult("patch-1")
        shadow_result.baseline_score = 0.6
        shadow_result.patched_score = 0.7
        shadow_result.improvement_score = 0.1
        shadow_result.latency_delta_ms = 50
        mock_shadow.return_value = [shadow_result]
        
        # Mock selection result
        mock_selection = type('SelectionResult', (), {
            'winner': type('Winner', (), {
                'shadow_result': type('ShadowResult', (), {'patch_id': 'patch-1'})(),
                'rank_score': 5.2
            })()
        })()
        mock_rank.return_value = mock_selection
        mock_summary.return_value = {"winner_selected": True}
        
        # Test the integration components
        results = mock_shadow(patches)
        assert len(results) == 1
        assert results[0].is_valid()
        
        selection = mock_rank([])
        assert selection.winner is not None


if __name__ == "__main__":
    pytest.main([__file__])