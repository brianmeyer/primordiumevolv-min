"""
Analytics V2 - Modernized analytics system with snapshots and normalization.

Key features:
- Single source of truth via analytics_snapshot table
- Task class normalization to canonical set
- Deprecation handling for operators/voices/judges  
- Cached snapshots with 60s TTL
- Preserves all evolution-critical metrics
"""

import os
import sqlite3
import time
import json
import math
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

# Task class normalization mapping
TASK_CLASS_NORMALIZER = {
    # Direct mappings
    "code": "code",
    "analysis": "analysis", 
    "writing": "writing",
    "business": "business",
    "research": "research",
    "general": "general",
    
    # Aliases and variations
    "coding": "code",
    "programming": "code",
    "debug": "code",
    "debugging": "code",
    "development": "code",
    "data": "analysis",
    "analytics": "analysis",
    "data_analysis": "analysis",
    "reporting": "analysis",
    "creative": "writing",
    "content": "writing",
    "copywriting": "writing",
    "marketing": "writing",
    "strategy": "business",
    "business_strategy": "business",
    "planning": "business",
    "management": "business",
    "operations": "business",
    "fact_checking": "research",
    "investigation": "research",
    "lookup": "research",
    "search": "research",
    "other": "general",
    "misc": "general",
    "default": "general",
}

CANONICAL_TASK_CLASSES = ["code", "analysis", "writing", "business", "research", "general"]

def normalize_task_class(raw_class: str) -> str:
    """Normalize task class to canonical form."""
    if not raw_class:
        return "general"
    
    # Convert to lowercase and strip
    normalized = raw_class.lower().strip()
    
    # Direct lookup
    if normalized in TASK_CLASS_NORMALIZER:
        return TASK_CLASS_NORMALIZER[normalized]
    
    # Partial matching for complex cases - prioritize by specificity
    matches = []
    for key, value in TASK_CLASS_NORMALIZER.items():
        if key in normalized:
            matches.append((key, value, len(key)))  # Include match length for prioritization
    
    if matches:
        # Return the most specific (longest) match
        matches.sort(key=lambda x: x[2], reverse=True)
        return matches[0][1]
            
    # Default fallback
    return "general"

def init_analytics_v2_tables(conn: sqlite3.Connection):
    """Initialize analytics v2 tables."""
    
    # Analytics snapshot table - single source of truth
    conn.execute("""
        CREATE TABLE IF NOT EXISTS analytics_snapshot (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            window_days INTEGER, -- 7, 30, or -1 for all
            created_at REAL,
            
            -- Totals section
            totals_json TEXT, -- {runs, scores, improvement, memory, operators, voices, judges, golden, thresholds, costs}
            
            -- Series data  
            series_json TEXT, -- {score_progression, runs_by_class}
            
            -- Metadata
            meta_json TEXT -- {normalizer_version, snapshot_version, computation_time_ms}
        )
    """)
    
    # Add deprecation flags to existing tables (migrations will handle this)
    # These are added via migrations to preserve existing data
    
    conn.commit()

class AnalyticsSnapshotManager:
    """Manages analytics snapshots with caching and computation."""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.cache_ttl_seconds = 60
        
    def _conn(self):
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;") 
        return conn
        
    def get_snapshot(self, window_days: int = 30) -> Dict[str, Any]:
        """Get analytics snapshot, using cache if fresh enough."""
        conn = self._conn()
        
        try:
            # Check for recent snapshot
            cursor = conn.execute("""
                SELECT totals_json, series_json, meta_json, created_at
                FROM analytics_snapshot 
                WHERE window_days = ?
                ORDER BY created_at DESC 
                LIMIT 1
            """, (window_days,))
            
            result = cursor.fetchone()
            now = time.time()
            
            if result and (now - result[3]) < self.cache_ttl_seconds:
                # Use cached snapshot
                return {
                    "totals": json.loads(result[0]),
                    "series": json.loads(result[1]), 
                    "meta": json.loads(result[2]),
                    "cached": True,
                    "age_seconds": int(now - result[3])
                }
            
            # Compute fresh snapshot
            return self._compute_snapshot(conn, window_days)
            
        finally:
            conn.close()
    
    def _compute_snapshot(self, conn: sqlite3.Connection, window_days: int) -> Dict[str, Any]:
        """Compute fresh analytics snapshot."""
        start_time = time.time()
        
        # Calculate date filter
        if window_days > 0:
            cutoff_date = time.time() - (window_days * 24 * 3600)
            date_filter = f"AND started_at >= {cutoff_date}"
        else:
            date_filter = ""
        
        # Compute totals
        totals = self._compute_totals(conn, date_filter)
        
        # Compute series
        series = self._compute_series(conn, date_filter)
        
        # Metadata
        computation_time_ms = int((time.time() - start_time) * 1000)
        meta = {
            "normalizer_version": "1.0",
            "snapshot_version": "2.0", 
            "computation_time_ms": computation_time_ms,
            "window_days": window_days,
            "computed_at": time.time()
        }
        
        # Save snapshot
        conn.execute("""
            INSERT INTO analytics_snapshot (window_days, created_at, totals_json, series_json, meta_json)
            VALUES (?, ?, ?, ?, ?)
        """, (
            window_days,
            time.time(),
            json.dumps(totals),
            json.dumps(series),
            json.dumps(meta)
        ))
        conn.commit()
        
        return {
            "totals": totals,
            "series": series,
            "meta": meta,
            "cached": False,
            "age_seconds": 0
        }
    
    def _compute_totals(self, conn: sqlite3.Connection, date_filter: str) -> Dict[str, Any]:
        """Compute totals section of snapshot."""
        
        # Basic run stats with normalization
        cursor = conn.execute(f"""
            SELECT 
                COUNT(*) as total_runs,
                AVG(CASE WHEN best_score != '-Inf' AND best_score IS NOT NULL THEN best_score END) as avg_score,
                MIN(started_at) as first_run,
                MAX(started_at) as latest_run
            FROM runs 
            WHERE finished_at IS NOT NULL {date_filter}
        """)
        basic_stats = cursor.fetchone()
        
        # Score improvement (early vs recent)  
        cursor = conn.execute(f"""
            WITH scored_runs AS (
                SELECT best_score, started_at,
                       ROW_NUMBER() OVER (ORDER BY started_at) as run_number,
                       COUNT(*) OVER () as total_count
                FROM runs 
                WHERE finished_at IS NOT NULL 
                  AND best_score IS NOT NULL 
                  AND best_score != '-Inf' 
                  {date_filter}
            )
            SELECT 
                AVG(CASE WHEN run_number <= total_count * 0.3 THEN best_score END) as early_avg,
                AVG(CASE WHEN run_number > total_count * 0.7 THEN best_score END) as recent_avg
            FROM scored_runs
        """)
        improvement_stats = cursor.fetchone()
        
        early_avg = improvement_stats[0] if improvement_stats[0] else 0
        recent_avg = improvement_stats[1] if improvement_stats[1] else 0
        delta_improvement = recent_avg - early_avg if (early_avg and recent_avg) else 0
        
        # Memory stats (if enabled)
        memory_stats = self._compute_memory_stats(conn, date_filter)
        
        # Operator stats
        operators = self._compute_operator_stats(conn, date_filter)
        
        # Voice stats
        voices = self._compute_voice_stats(conn, date_filter)
        
        # Judge stats  
        judges = self._compute_judge_stats(conn, date_filter)
        
        # Golden set stats
        golden = self._compute_golden_stats(conn, date_filter)
        
        # Cost stats (to be merged into other tabs)
        costs = self._compute_cost_stats(conn, date_filter)
        
        # Thresholds (from config/environment)
        thresholds = self._get_threshold_config()
        
        return {
            "runs": {
                "total": basic_stats[0] if basic_stats[0] else 0,
                "avg_score": basic_stats[1],
                "first_run": basic_stats[2],
                "latest_run": basic_stats[3],
                "timespan_days": (basic_stats[3] - basic_stats[2]) / 86400 if (basic_stats[2] and basic_stats[3]) else 0
            },
            "improvement": {
                "early_avg_score": early_avg,
                "recent_avg_score": recent_avg, 
                "delta_total_reward": delta_improvement
            },
            "memory": memory_stats,
            "operators": operators,
            "voices": voices,
            "judges": judges, 
            "golden": golden,
            "costs": costs,
            "thresholds": thresholds
        }
    
    def _compute_series(self, conn: sqlite3.Connection, date_filter: str) -> Dict[str, Any]:
        """Compute series data for charts."""
        
        # Score progression over time
        cursor = conn.execute(f"""
            SELECT 
                id,
                started_at,
                best_score,
                task_class
            FROM runs 
            WHERE finished_at IS NOT NULL 
              AND best_score IS NOT NULL 
              AND best_score != '-Inf'
              {date_filter}
            ORDER BY started_at
        """)
        
        runs_data = cursor.fetchall()
        
        # Build rolling average for score progression
        window_size = max(3, len(runs_data) // 20)  # Adaptive window
        score_progression = []
        
        for i, (run_id, timestamp, score, task_class) in enumerate(runs_data):
            if i >= window_size - 1:
                window_scores = [r[2] for r in runs_data[max(0, i-window_size+1):i+1]]
                rolling_avg = sum(window_scores) / len(window_scores)
                score_progression.append({
                    "run_id": run_id,
                    "timestamp": timestamp,
                    "score": score,
                    "rolling_avg": rolling_avg,
                    "task_class": normalize_task_class(task_class)
                })
        
        # Runs by normalized task class
        cursor = conn.execute(f"""
            SELECT task_class, COUNT(*) as count
            FROM runs 
            WHERE finished_at IS NOT NULL {date_filter}
            GROUP BY task_class
        """)
        
        runs_by_class = {}
        for raw_class, count in cursor.fetchall():
            canonical = normalize_task_class(raw_class)
            runs_by_class[canonical] = runs_by_class.get(canonical, 0) + count
        
        return {
            "score_progression": score_progression,
            "runs_by_class": runs_by_class
        }
    
    def _compute_memory_stats(self, conn: sqlite3.Connection, date_filter: str) -> Dict[str, Any]:
        """Compute memory system stats."""
        try:
            from app.memory.metrics import get_memory_metrics_tracker
            from app.config import FF_MEMORY
            
            if not FF_MEMORY:
                return {"enabled": False}
                
            tracker = get_memory_metrics_tracker()
            analytics = tracker.get_analytics(days_back=30)
            
            return {
                "enabled": True,
                "hit_rate": analytics.get("hit_rate", 0.0),
                "reward_lift": analytics.get("reward_lift", 0.0), 
                "store_size": analytics.get("store_size", 0),
                "primer_tokens": analytics.get("avg_primer_tokens", 0)
            }
        except Exception:
            return {"enabled": False, "error": "Failed to load memory stats"}
    
    def _compute_operator_stats(self, conn: sqlite3.Connection, date_filter: str) -> List[Dict[str, Any]]:
        """Compute operator usage and performance stats."""
        cursor = conn.execute(f"""
            SELECT 
                operator_name,
                COUNT(*) as usage_count,
                AVG(total_reward) as avg_total_reward,
                AVG(execution_time_ms) as avg_latency_ms,
                COUNT(CASE WHEN total_reward > 0 THEN 1 END) as positive_outcomes
            FROM variants v
            JOIN runs r ON v.run_id = r.id  
            WHERE r.finished_at IS NOT NULL 
              AND v.operator_name IS NOT NULL
              {date_filter.replace('started_at', 'r.started_at') if date_filter else ''}
            GROUP BY operator_name
            ORDER BY avg_total_reward DESC
        """)
        
        operators = []
        for row in cursor.fetchall():
            op_name, count, avg_reward, avg_latency, positive = row
            success_rate = (positive / count) if count > 0 else 0
            
            operators.append({
                "name": op_name,
                "usage_count": count,
                "avg_total_reward": avg_reward or 0,
                "avg_latency_ms": avg_latency or 0,
                "success_rate": success_rate,
                "deprecated": False  # Will be set by migration
            })
            
        return operators
    
    def _compute_voice_stats(self, conn: sqlite3.Connection, date_filter: str) -> List[Dict[str, Any]]:
        """Compute voice (system prompt) usage and performance."""
        cursor = conn.execute(f"""
            SELECT 
                system,
                COUNT(*) as usage_count,
                AVG(total_reward) as avg_total_reward,
                AVG(cost_penalty) as avg_cost_penalty
            FROM variants v
            JOIN runs r ON v.run_id = r.id
            WHERE r.finished_at IS NOT NULL
              AND v.system IS NOT NULL 
              {date_filter.replace('started_at', 'r.started_at') if date_filter else ''}
            GROUP BY system
            ORDER BY avg_total_reward DESC
        """)
        
        voices = []
        for row in cursor.fetchall():
            system, count, avg_reward, avg_cost = row
            voices.append({
                "system_prompt": system[:100] + "..." if len(system) > 100 else system,
                "usage_count": count,
                "avg_total_reward": avg_reward or 0,
                "avg_cost_penalty": avg_cost or 0,
                "deprecated": False  # Will be set by migration
            })
            
        return voices
    
    def _compute_judge_stats(self, conn: sqlite3.Connection, date_filter: str) -> Dict[str, Any]:
        """Compute judge evaluation stats."""
        # This would need to be adapted based on actual judge evaluation table structure
        # For now, return placeholder that matches existing structure
        return {
            "evaluated": 0,
            "tie_breaker_rate": 0.0,
            "eval_latency_ms": {"p50": None, "p90": None}
        }
    
    def _compute_golden_stats(self, conn: sqlite3.Connection, date_filter: str) -> Dict[str, Any]:
        """Compute Golden Set performance stats."""
        # Placeholder - would integrate with existing Golden Set system
        return {
            "total_tests": 0,
            "pass_rate": 0.0,
            "avg_reward": 0.0,
            "avg_cost": 0.0
        }
    
    def _compute_cost_stats(self, conn: sqlite3.Connection, date_filter: str) -> Dict[str, Any]:
        """Compute cost and latency stats (to be merged into other tabs)."""
        cursor = conn.execute(f"""
            SELECT 
                AVG(execution_time_ms) as avg_latency,
                AVG(cost_penalty) as avg_cost_penalty,
                SUM(execution_time_ms) as total_latency_ms
            FROM variants v
            JOIN runs r ON v.run_id = r.id
            WHERE r.finished_at IS NOT NULL
              {date_filter.replace('started_at', 'r.started_at') if date_filter else ''}
        """)
        
        result = cursor.fetchone()
        return {
            "avg_latency_ms": result[0] or 0,
            "avg_cost_penalty": result[1] or 0,
            "total_latency_ms": result[2] or 0
        }
    
    def _get_threshold_config(self) -> Dict[str, Any]:
        """Get threshold configuration from environment/config."""
        return {
            "delta_reward_min": float(os.getenv("PHASE4_DELTA_REWARD_MIN", "0.05")),
            "cost_ratio_max": float(os.getenv("PHASE4_COST_RATIO_MAX", "0.9")),
            "golden_pass_target": float(os.getenv("GOLDEN_PASS_RATE_TARGET", "0.8"))
        }
    
    def invalidate_cache(self, window_days: Optional[int] = None):
        """Invalidate cached snapshots."""
        conn = self._conn()
        try:
            # Check if table exists first
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='analytics_snapshot'")
            if cursor.fetchone() is None:
                return  # Table doesn't exist yet
                
            if window_days is not None:
                conn.execute("DELETE FROM analytics_snapshot WHERE window_days = ?", (window_days,))
            else:
                conn.execute("DELETE FROM analytics_snapshot")
            conn.commit()
        finally:
            conn.close()

# Global instance
_snapshot_manager = None

def get_snapshot_manager() -> AnalyticsSnapshotManager:
    """Get global analytics snapshot manager."""
    global _snapshot_manager
    if _snapshot_manager is None:
        from app.meta.store import DB_PATH
        _snapshot_manager = AnalyticsSnapshotManager(DB_PATH)
    return _snapshot_manager