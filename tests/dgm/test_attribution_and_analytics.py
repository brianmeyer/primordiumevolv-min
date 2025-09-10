"""
Test DGM attribution and analytics functionality.
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from app.dgm.analytics import track_patch_lifecycle, get_attribution_stats, calculate_success_metrics
from app.dgm.types import MetaPatch, ShadowEvalResult


@pytest.fixture
def sample_lifecycle_events():
    """Create sample patch lifecycle events."""
    base_time = datetime.now()
    return [
        {
            "patch_id": "analytics_test_001",
            "event": "proposed",
            "timestamp": base_time,
            "area": "prompts",
            "origin": "llm_generation",
            "metadata": {"proposals_generated": 5}
        },
        {
            "patch_id": "analytics_test_001",
            "event": "shadow_eval_started",
            "timestamp": base_time + timedelta(minutes=1),
            "metadata": {"runs": 25}
        },
        {
            "patch_id": "analytics_test_001",
            "event": "shadow_eval_completed",
            "timestamp": base_time + timedelta(minutes=5),
            "metadata": {"reward_delta": 0.15, "success": True}
        },
        {
            "patch_id": "analytics_test_001",
            "event": "selected_for_commit",
            "timestamp": base_time + timedelta(minutes=6),
            "metadata": {"rank": 1, "score": 0.85}
        },
        {
            "patch_id": "analytics_test_001",
            "event": "committed",
            "timestamp": base_time + timedelta(minutes=7),
            "metadata": {"commit_sha": "abc123def456"}
        }
    ]


def test_track_patch_lifecycle():
    """Test patch lifecycle tracking."""
    patch = MetaPatch(
        id="lifecycle_test_001",
        area="prompts",
        origin="test_generation",
        notes="Lifecycle tracking test",
        diff="test diff",
        loc_delta=1
    )
    
    with patch('app.dgm.storage.get_analytics_storage') as mock_storage:
        mock_store = MagicMock()
        mock_storage.return_value = mock_store
        
        # Track various lifecycle events
        track_patch_lifecycle(patch, "proposed", {"generator": "llm"})
        track_patch_lifecycle(patch, "shadow_eval_started", {"runs": 25})
        track_patch_lifecycle(patch, "shadow_eval_completed", {"success": True, "reward_delta": 0.1})
        track_patch_lifecycle(patch, "committed", {"commit_sha": "abc123"})
        
        # Should have recorded all events
        assert mock_store.record_event.call_count == 4
        
        # Verify event data structure
        for call in mock_store.record_event.call_args_list:
            event_data = call[0][0]
            assert "patch_id" in event_data
            assert "event" in event_data
            assert "timestamp" in event_data
            assert "area" in event_data
            assert "origin" in event_data


def test_get_attribution_stats():
    """Test attribution statistics calculation."""
    with patch('app.dgm.storage.get_analytics_storage') as mock_storage:
        mock_store = MagicMock()
        mock_storage.return_value = mock_store
        
        # Mock analytics data
        mock_store.get_events.return_value = [
            {
                "patch_id": "attr_test_1",
                "event": "committed",
                "origin": "llm_generation",
                "area": "prompts",
                "timestamp": datetime.now(),
                "metadata": {"reward_delta": 0.15}
            },
            {
                "patch_id": "attr_test_2", 
                "event": "committed",
                "origin": "mutation",
                "area": "bandit",
                "timestamp": datetime.now(),
                "metadata": {"reward_delta": 0.08}
            },
            {
                "patch_id": "attr_test_3",
                "event": "committed", 
                "origin": "llm_generation",
                "area": "prompts",
                "timestamp": datetime.now(),
                "metadata": {"reward_delta": 0.12}
            }
        ]
        
        stats = get_attribution_stats(days=30)
        
        assert "by_origin" in stats
        assert "by_area" in stats
        assert "total_commits" in stats
        
        # Should show LLM generation contributing more
        assert stats["by_origin"]["llm_generation"]["count"] == 2
        assert stats["by_origin"]["mutation"]["count"] == 1
        
        # Should track reward contributions
        assert stats["by_origin"]["llm_generation"]["total_reward_delta"] == pytest.approx(0.27, rel=1e-2)


def test_calculate_success_metrics():
    """Test success metrics calculation."""
    with patch('app.dgm.storage.get_analytics_storage') as mock_storage:
        mock_store = MagicMock()
        mock_storage.return_value = mock_store
        
        # Mock patch lifecycle data
        mock_store.get_events.return_value = [
            # Successful patch
            {"patch_id": "success_1", "event": "proposed", "timestamp": datetime.now()},
            {"patch_id": "success_1", "event": "shadow_eval_completed", "metadata": {"success": True}},
            {"patch_id": "success_1", "event": "committed", "timestamp": datetime.now()},
            
            # Failed shadow eval
            {"patch_id": "failed_1", "event": "proposed", "timestamp": datetime.now()},
            {"patch_id": "failed_1", "event": "shadow_eval_completed", "metadata": {"success": False}},
            
            # Rejected after shadow eval
            {"patch_id": "rejected_1", "event": "proposed", "timestamp": datetime.now()},
            {"patch_id": "rejected_1", "event": "shadow_eval_completed", "metadata": {"success": True}},
            {"patch_id": "rejected_1", "event": "rejected", "timestamp": datetime.now()},
        ]
        
        metrics = calculate_success_metrics(days=7)
        
        assert "proposal_to_commit_rate" in metrics
        assert "shadow_eval_success_rate" in metrics
        assert "commit_success_rate" in metrics
        assert "avg_time_to_commit" in metrics
        
        # Should calculate correct ratios
        assert metrics["proposal_to_commit_rate"] == pytest.approx(0.33, rel=1e-1)  # 1 of 3 proposed
        assert metrics["shadow_eval_success_rate"] == pytest.approx(0.67, rel=1e-1)  # 2 of 3 succeeded


def test_attribution_by_area():
    """Test attribution statistics by modification area."""
    with patch('app.dgm.storage.get_analytics_storage') as mock_storage:
        mock_store = MagicMock()
        mock_storage.return_value = mock_store
        
        mock_store.get_events.return_value = [
            {"patch_id": "p1", "event": "committed", "area": "prompts", "metadata": {"reward_delta": 0.1}},
            {"patch_id": "p2", "event": "committed", "area": "prompts", "metadata": {"reward_delta": 0.15}},
            {"patch_id": "p3", "event": "committed", "area": "bandit", "metadata": {"reward_delta": 0.05}},
            {"patch_id": "p4", "event": "committed", "area": "ui_metrics", "metadata": {"reward_delta": 0.08}},
        ]
        
        stats = get_attribution_stats(days=30)
        
        # Prompts should be most productive area
        assert stats["by_area"]["prompts"]["count"] == 2
        assert stats["by_area"]["prompts"]["total_reward_delta"] == 0.25
        assert stats["by_area"]["prompts"]["avg_reward_delta"] == 0.125
        
        # Should have stats for all areas
        assert "bandit" in stats["by_area"]
        assert "ui_metrics" in stats["by_area"]


def test_temporal_analytics():
    """Test temporal analytics and trends."""
    with patch('app.dgm.storage.get_analytics_storage') as mock_storage:
        mock_store = MagicMock()
        mock_storage.return_value = mock_store
        
        # Mock events over time
        base_time = datetime.now() - timedelta(days=7)
        mock_store.get_events.return_value = [
            {
                "patch_id": f"temp_{i}",
                "event": "committed",
                "timestamp": base_time + timedelta(days=i),
                "metadata": {"reward_delta": 0.1 + i * 0.02}  # Improving over time
            }
            for i in range(7)
        ]
        
        from app.dgm.analytics import get_temporal_trends
        trends = get_temporal_trends(days=7)
        
        assert "daily_commits" in trends
        assert "avg_reward_trend" in trends
        assert len(trends["daily_commits"]) == 7
        
        # Should show improvement trend
        first_day_reward = trends["avg_reward_trend"][0]
        last_day_reward = trends["avg_reward_trend"][-1]
        assert last_day_reward > first_day_reward


def test_performance_attribution():
    """Test performance attribution tracking."""
    with patch('app.dgm.storage.get_analytics_storage') as mock_storage:
        mock_store = MagicMock()
        mock_storage.return_value = mock_store
        
        # Mock performance data
        mock_store.get_events.return_value = [
            {
                "patch_id": "perf_1",
                "event": "shadow_eval_completed",
                "metadata": {
                    "execution_time_ms": 1000,
                    "baseline_reward": 0.7,
                    "shadow_reward": 0.8
                }
            },
            {
                "patch_id": "perf_2",
                "event": "shadow_eval_completed", 
                "metadata": {
                    "execution_time_ms": 2000,
                    "baseline_reward": 0.6,
                    "shadow_reward": 0.85
                }
            }
        ]
        
        from app.dgm.analytics import get_performance_stats
        perf_stats = get_performance_stats()
        
        assert "avg_execution_time_ms" in perf_stats
        assert "avg_reward_improvement" in perf_stats
        assert "efficiency_score" in perf_stats
        
        # Should calculate averages correctly
        assert perf_stats["avg_execution_time_ms"] == 1500
        assert perf_stats["avg_reward_improvement"] == pytest.approx(0.175, rel=1e-2)


def test_rollback_attribution():
    """Test tracking of rollback events and their causes."""
    with patch('app.dgm.storage.get_analytics_storage') as mock_storage:
        mock_store = MagicMock()
        mock_storage.return_value = mock_store
        
        # Mock rollback events
        mock_store.get_events.return_value = [
            {
                "patch_id": "rollback_1",
                "event": "committed",
                "timestamp": datetime.now() - timedelta(hours=2)
            },
            {
                "patch_id": "rollback_1",
                "event": "rolled_back",
                "timestamp": datetime.now() - timedelta(hours=1),
                "metadata": {
                    "reason": "guard_violation",
                    "violation_type": "error_rate_exceeded",
                    "original_commit": "abc123"
                }
            }
        ]
        
        from app.dgm.analytics import get_rollback_stats
        rollback_stats = get_rollback_stats(days=1)
        
        assert "total_rollbacks" in rollback_stats
        assert "rollback_reasons" in rollback_stats
        assert "rollback_rate" in rollback_stats
        
        assert rollback_stats["rollback_reasons"]["guard_violation"] == 1


def test_analytics_data_retention():
    """Test analytics data retention and cleanup."""
    with patch('app.dgm.storage.get_analytics_storage') as mock_storage:
        mock_store = MagicMock()
        mock_storage.return_value = mock_store
        
        # Test cleanup of old data
        from app.dgm.analytics import cleanup_old_analytics
        cleanup_old_analytics(retention_days=30)
        
        mock_store.cleanup_old_events.assert_called_once_with(30)


def test_analytics_aggregation_performance():
    """Test that analytics aggregation performs well with large datasets."""
    import time
    
    with patch('app.dgm.storage.get_analytics_storage') as mock_storage:
        mock_store = MagicMock()
        mock_storage.return_value = mock_store
        
        # Mock large dataset (1000 events)
        large_dataset = [
            {
                "patch_id": f"large_{i}",
                "event": "committed",
                "area": "prompts",
                "origin": "llm_generation",
                "timestamp": datetime.now() - timedelta(hours=i),
                "metadata": {"reward_delta": 0.1 + (i % 10) * 0.01}
            }
            for i in range(1000)
        ]
        
        mock_store.get_events.return_value = large_dataset
        
        start_time = time.time()
        stats = get_attribution_stats(days=30)
        end_time = time.time()
        
        # Should complete aggregation quickly (under 1 second)
        assert end_time - start_time < 1.0
        assert stats["total_commits"] == 1000


def test_analytics_privacy_and_security():
    """Test that analytics don't expose sensitive information."""
    with patch('app.dgm.storage.get_analytics_storage') as mock_storage:
        mock_store = MagicMock()
        mock_storage.return_value = mock_store
        
        # Mock events with potentially sensitive data
        mock_store.get_events.return_value = [
            {
                "patch_id": "sensitive_1",
                "event": "committed",
                "area": "prompts",
                "metadata": {
                    "reward_delta": 0.1,
                    "sensitive_field": "should_not_appear_in_stats"
                }
            }
        ]
        
        stats = get_attribution_stats(days=30)
        
        # Should not expose raw metadata in aggregated stats
        stats_str = str(stats)
        assert "sensitive_field" not in stats_str
        assert "should_not_appear_in_stats" not in stats_str


def test_analytics_error_handling():
    """Test analytics error handling and resilience."""
    with patch('app.dgm.storage.get_analytics_storage') as mock_storage:
        mock_store = MagicMock()
        mock_storage.return_value = mock_store
        
        # Simulate storage error
        mock_store.get_events.side_effect = Exception("Storage unavailable")
        
        # Should handle errors gracefully
        stats = get_attribution_stats(days=30)
        
        # Should return empty/default stats rather than crashing
        assert isinstance(stats, dict)


def test_real_time_analytics_updates():
    """Test real-time analytics updates."""
    with patch('app.dgm.storage.get_analytics_storage') as mock_storage, \
         patch('app.realtime.emit') as mock_emit:
        
        mock_store = MagicMock()
        mock_storage.return_value = mock_store
        
        patch = MetaPatch(
            id="realtime_test",
            area="prompts",
            origin="test",
            notes="Real-time test",
            diff="test diff",
            loc_delta=1
        )
        
        # Track event with real-time updates
        track_patch_lifecycle(patch, "committed", {"commit_sha": "abc123"}, emit_update=True)
        
        # Should emit real-time update
        mock_emit.assert_called_once()
        emit_call = mock_emit.call_args
        assert emit_call[0][0] == "analytics_update"


if __name__ == "__main__":
    pytest.main([__file__])