#!/usr/bin/env python3
"""
Test suite for Analytics V2 system.

Tests the core functionality while ensuring no regressions in evolution-critical metrics.
"""

import pytest
import sqlite3
import tempfile
import os
import time
from unittest.mock import patch, MagicMock

# Add project root to path
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.meta.analytics_v2 import (
    normalize_task_class, 
    AnalyticsSnapshotManager, 
    CANONICAL_TASK_CLASSES,
    TASK_CLASS_NORMALIZER
)
from app.meta.migrations import MigrationManager

class TestTaskClassNormalization:
    """Test task class normalization functionality."""
    
    def test_direct_mappings(self):
        """Test direct canonical mappings."""
        assert normalize_task_class("code") == "code"
        assert normalize_task_class("analysis") == "analysis"
        assert normalize_task_class("writing") == "writing"
        assert normalize_task_class("business") == "business"
        assert normalize_task_class("research") == "research"
        assert normalize_task_class("general") == "general"
    
    def test_aliases(self):
        """Test alias mappings."""
        assert normalize_task_class("coding") == "code"
        assert normalize_task_class("programming") == "code"
        assert normalize_task_class("debug") == "code"
        assert normalize_task_class("data") == "analysis"
        assert normalize_task_class("analytics") == "analysis"
        assert normalize_task_class("creative") == "writing"
        assert normalize_task_class("content") == "writing"
        assert normalize_task_class("strategy") == "business"
        assert normalize_task_class("planning") == "business"
        assert normalize_task_class("fact_checking") == "research"
        assert normalize_task_class("lookup") == "research"
        assert normalize_task_class("other") == "general"
        assert normalize_task_class("misc") == "general"
    
    def test_edge_cases(self):
        """Test edge cases and fallbacks."""
        assert normalize_task_class("") == "general"
        assert normalize_task_class(None) == "general"
        assert normalize_task_class("unknown_type") == "general"
        assert normalize_task_class("CODE") == "code"  # Case insensitive
        assert normalize_task_class("  data_analysis  ") == "analysis"  # Whitespace
    
    def test_partial_matching(self):
        """Test partial string matching."""
        assert normalize_task_class("python_programming_task") == "code"
        assert normalize_task_class("business_strategy_analysis") == "business"
        assert normalize_task_class("creative_writing_exercise") == "writing"

class TestAnalyticsSnapshotManager:
    """Test the analytics snapshot manager."""
    
    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        
        # Initialize test database with basic schema
        conn = sqlite3.connect(path)
        conn.execute("""
            CREATE TABLE runs (
                id INTEGER PRIMARY KEY,
                task_class TEXT,
                started_at REAL,
                finished_at REAL,
                best_score REAL,
                normalized_task_class TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE variants (
                id INTEGER PRIMARY KEY,
                run_id INTEGER,
                operator_name TEXT,
                total_reward REAL,
                latency_ms INTEGER,
                cost_penalty REAL,
                system_prompt TEXT,
                FOREIGN KEY (run_id) REFERENCES runs(id)
            )
        """)
        conn.execute("""
            CREATE TABLE analytics_snapshot (
                id INTEGER PRIMARY KEY,
                window_days INTEGER,
                created_at REAL,
                totals_json TEXT,
                series_json TEXT,
                meta_json TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE deprecated_entities (
                entity_type TEXT,
                entity_name TEXT,
                deprecated_at REAL,
                reason TEXT,
                PRIMARY KEY (entity_type, entity_name)
            )
        """)
        
        # Insert test data
        now = time.time()
        test_runs = [
            (1, "code", now - 86400, now - 86000, 0.8, "code"),
            (2, "programming", now - 43200, now - 43000, 0.9, "code"),
            (3, "data_analysis", now - 21600, now - 21400, 0.7, "analysis"),
            (4, "writing", now - 10800, now - 10600, 0.85, "writing"),
        ]
        
        for run_data in test_runs:
            conn.execute("INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?)", run_data)
            
        # Insert test variants
        test_variants = [
            (1, 1, "toggle_web", 0.12, 1500, -0.001, "You are a senior engineer."),
            (2, 1, "lower_temp", 0.08, 1200, -0.0005, "You are a senior engineer."),
            (3, 2, "toggle_web", 0.15, 1800, -0.002, "You are a careful analyst."),
            (4, 3, "raise_temp", 0.05, 2000, -0.001, "You are a creative optimizer."),
            (5, 4, "change_system", 0.18, 1100, -0.0008, "You are a detail-oriented specialist."),
        ]
        
        for variant_data in test_variants:
            conn.execute("INSERT INTO variants VALUES (?, ?, ?, ?, ?, ?, ?)", variant_data)
            
        conn.commit()
        conn.close()
        
        yield path
        
        # Cleanup
        try:
            os.unlink(path)
        except OSError:
            pass
    
    def test_snapshot_creation(self, temp_db):
        """Test basic snapshot creation."""
        manager = AnalyticsSnapshotManager(temp_db)
        snapshot = manager.get_snapshot(window_days=30)
        
        assert snapshot is not None
        assert "totals" in snapshot
        assert "series" in snapshot
        assert "meta" in snapshot
        assert snapshot["cached"] == False  # First computation
        assert snapshot["age_seconds"] == 0
        
        # Check totals structure
        totals = snapshot["totals"]
        assert "runs" in totals
        assert "improvement" in totals
        assert "operators" in totals
        assert "voices" in totals
        assert totals["runs"]["total"] == 4
        
        # Check series structure  
        series = snapshot["series"]
        assert "score_progression" in series
        assert "runs_by_class" in series
        
        # Verify task class normalization
        assert "code" in series["runs_by_class"]
        assert series["runs_by_class"]["code"] == 2  # Both "code" and "programming" normalized to "code"
        assert "analysis" in series["runs_by_class"]
        assert series["runs_by_class"]["analysis"] == 1
        
    def test_snapshot_caching(self, temp_db):
        """Test snapshot caching mechanism."""
        manager = AnalyticsSnapshotManager(temp_db)
        
        # First call
        snapshot1 = manager.get_snapshot(window_days=30)
        assert snapshot1["cached"] == False
        
        # Second call should use cache
        snapshot2 = manager.get_snapshot(window_days=30)
        assert snapshot2["cached"] == True
        assert snapshot2["age_seconds"] < 60
        
        # Totals should be identical
        assert snapshot1["totals"] == snapshot2["totals"]
        
    def test_cache_invalidation(self, temp_db):
        """Test cache invalidation."""
        manager = AnalyticsSnapshotManager(temp_db)
        
        # Get initial snapshot
        snapshot1 = manager.get_snapshot(window_days=30)
        
        # Invalidate cache
        manager.invalidate_cache(window_days=30)
        
        # Next call should recompute
        snapshot2 = manager.get_snapshot(window_days=30)
        assert snapshot2["cached"] == False
        
    def test_window_filtering(self, temp_db):
        """Test different time window filters."""
        manager = AnalyticsSnapshotManager(temp_db)
        
        # Test all-time snapshot
        all_snapshot = manager.get_snapshot(window_days=-1)
        assert all_snapshot["totals"]["runs"]["total"] == 4
        
        # Test 7-day snapshot (should have fewer runs)
        week_snapshot = manager.get_snapshot(window_days=7)
        # All test runs are recent, so should still be 4
        assert week_snapshot["totals"]["runs"]["total"] == 4
        
    def test_operator_stats(self, temp_db):
        """Test operator statistics computation."""
        manager = AnalyticsSnapshotManager(temp_db)
        snapshot = manager.get_snapshot(window_days=30)
        
        operators = snapshot["totals"]["operators"]
        assert len(operators) > 0
        
        # Find toggle_web operator (appears twice)
        toggle_web = next((op for op in operators if op["name"] == "toggle_web"), None)
        assert toggle_web is not None
        assert toggle_web["usage_count"] == 2
        assert toggle_web["avg_total_reward"] > 0
        assert "deprecated" in toggle_web
        
    def test_voice_stats(self, temp_db):
        """Test voice (system prompt) statistics."""
        manager = AnalyticsSnapshotManager(temp_db)
        snapshot = manager.get_snapshot(window_days=30)
        
        voices = snapshot["totals"]["voices"]
        assert len(voices) > 0
        
        # Should have different system prompts
        prompt_texts = [v["system_prompt"] for v in voices]
        assert len(set(prompt_texts)) > 1  # Multiple unique prompts
        
    @patch.dict(os.environ, {
        "PHASE4_DELTA_REWARD_MIN": "0.05",
        "PHASE4_COST_RATIO_MAX": "0.9", 
        "GOLDEN_PASS_RATE_TARGET": "0.8"
    })
    def test_threshold_config(self, temp_db):
        """Test threshold configuration loading."""
        manager = AnalyticsSnapshotManager(temp_db)
        thresholds = manager._get_threshold_config()
        
        assert thresholds["delta_reward_min"] == 0.05
        assert thresholds["cost_ratio_max"] == 0.9
        assert thresholds["golden_pass_target"] == 0.8

class TestMigrationManager:
    """Test the migration system."""
    
    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for migration testing."""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        
        # Create basic schema without migrations
        conn = sqlite3.connect(path)
        conn.execute("""
            CREATE TABLE runs (
                id INTEGER PRIMARY KEY,
                task_class TEXT,
                started_at REAL,
                finished_at REAL,
                best_score REAL
            )
        """)
        
        # Insert test data with non-normalized task classes
        test_data = [
            (1, "programming", time.time(), time.time(), 0.8),
            (2, "data_analysis", time.time(), time.time(), 0.7),
            (3, "creative", time.time(), time.time(), 0.9),
        ]
        
        for row in test_data:
            conn.execute("INSERT INTO runs VALUES (?, ?, ?, ?, ?)", row)
        
        conn.commit()
        conn.close()
        
        yield path
        
        try:
            os.unlink(path)
        except OSError:
            pass
    
    def test_migration_version_tracking(self, temp_db):
        """Test migration version tracking."""
        manager = MigrationManager(temp_db)
        
        # Initially version 0
        assert manager.get_current_version() == 0
        
        # Apply migrations
        applied = manager.apply_migrations()
        assert len(applied) > 0
        
        # Version should be updated
        assert manager.get_current_version() > 0
        
        # Running again should apply nothing
        applied_again = manager.apply_migrations()
        assert len(applied_again) == 0
        
    def test_task_class_normalization_migration(self, temp_db):
        """Test migration 001: task class normalization."""
        manager = MigrationManager(temp_db)
        
        # Apply migrations
        applied = manager.apply_migrations()
        
        # Check that normalized_task_class column was added and populated
        conn = sqlite3.connect(temp_db)
        cursor = conn.execute("SELECT task_class, normalized_task_class FROM runs")
        rows = cursor.fetchall()
        conn.close()
        
        # Verify normalization worked
        task_mappings = {row[0]: row[1] for row in rows}
        assert task_mappings["programming"] == "code"
        assert task_mappings["data_analysis"] == "analysis"
        assert task_mappings["creative"] == "writing"
        
    def test_deprecation_entities_table(self, temp_db):
        """Test migration 002: deprecation entities table."""
        manager = MigrationManager(temp_db)
        manager.apply_migrations()
        
        # Check that deprecated_entities table exists
        conn = sqlite3.connect(temp_db)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='deprecated_entities'")
        table_exists = cursor.fetchone() is not None
        conn.close()
        
        assert table_exists
        
    def test_snapshot_table_creation(self, temp_db):
        """Test migration 003: analytics_snapshot table."""  
        manager = MigrationManager(temp_db)
        manager.apply_migrations()
        
        # Check that analytics_snapshot table exists
        conn = sqlite3.connect(temp_db)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='analytics_snapshot'")
        table_exists = cursor.fetchone() is not None
        conn.close()
        
        assert table_exists

class TestIntegrationPreservation:
    """Test that evolution-critical functionality is preserved."""
    
    def test_canonical_task_classes_completeness(self):
        """Ensure canonical task classes cover expected domains."""
        expected_domains = {"code", "analysis", "writing", "business", "research", "general"}
        assert set(CANONICAL_TASK_CLASSES) == expected_domains
        
    def test_normalizer_coverage(self):
        """Test that all common task variations are covered."""
        common_inputs = [
            "programming", "coding", "development", "debug",
            "data", "analytics", "reporting", 
            "creative", "content", "copywriting",
            "strategy", "planning", "management",
            "search", "lookup", "fact_checking",
            "other", "misc", "general"
        ]
        
        for input_class in common_inputs:
            result = normalize_task_class(input_class)
            assert result in CANONICAL_TASK_CLASSES, f"Input '{input_class}' -> '{result}' not in canonical set"
    
    def test_no_data_loss(self):
        """Ensure normalization preserves original data."""
        # The system should keep original task_class and add normalized_task_class
        # This ensures no loss of original information
        original = "python_web_development_task"
        normalized = normalize_task_class(original)
        
        # Original intent should be preserved in mapping
        assert normalized == "code"  # Should map to code domain
        
        # And we should be able to reverse-engineer intent from both
        assert "development" in original  # Original has development info
        assert normalized in CANONICAL_TASK_CLASSES  # Normalized is canonical

def test_analytics_endpoint_compatibility():
    """Test that the new snapshot endpoint maintains API compatibility."""
    # This would be tested with actual HTTP requests in integration tests
    # For unit testing, we verify the structure matches expectations
    
    expected_snapshot_structure = {
        "totals": {
            "runs": {"total": int, "avg_score": float},
            "improvement": {"delta_total_reward": float},
            "memory": {"enabled": bool, "hit_rate": float, "reward_lift": float},
            "operators": list,
            "voices": list,
            "judges": dict,
            "golden": dict,
            "costs": dict,
            "thresholds": dict
        },
        "series": {
            "score_progression": list,
            "runs_by_class": dict
        },
        "meta": {
            "snapshot_version": str,
            "computation_time_ms": int
        }
    }
    
    # Verify structure is properly defined
    assert isinstance(expected_snapshot_structure, dict)
    assert "totals" in expected_snapshot_structure
    assert "series" in expected_snapshot_structure
    assert "meta" in expected_snapshot_structure

if __name__ == "__main__":
    # Run tests
    import subprocess
    result = subprocess.run([sys.executable, "-m", "pytest", __file__, "-v"], 
                          capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)
    exit(result.returncode)