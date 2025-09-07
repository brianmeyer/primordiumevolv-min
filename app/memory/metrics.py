"""
Memory system metrics tracking and analytics.
Tracks memory usage, hit rates, and performance attribution.
"""
import sqlite3
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

@dataclass
class MemoryMetrics:
    """Per-run memory metrics."""
    run_id: int
    task_class: str
    memory_hits: int
    memory_hit_rate: float
    memory_avg_reward_lift: float
    memory_primer_tokens: int
    memory_store_size: int
    used_memory: bool
    lift_source: str
    created_at: datetime

class MemoryMetricsTracker:
    """Tracks and persists memory system metrics."""
    
    def __init__(self, db_path: str = None):
        """Initialize metrics tracker."""
        if db_path is None:
            db_path = "storage/meta.db"
        
        self.db_path = db_path
        self._ensure_schema()
    
    def _ensure_schema(self):
        """Ensure memory metrics table exists."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS memory_metrics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        run_id INTEGER NOT NULL,
                        task_class TEXT NOT NULL,
                        memory_hits INTEGER DEFAULT 0,
                        memory_hit_rate REAL DEFAULT 0.0,
                        memory_avg_reward_lift REAL DEFAULT 0.0,
                        memory_primer_tokens INTEGER DEFAULT 0,
                        memory_store_size INTEGER DEFAULT 0,
                        used_memory BOOLEAN DEFAULT FALSE,
                        lift_source TEXT DEFAULT 'none',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Add indexes
                conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_run_id ON memory_metrics(run_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_task_class ON memory_metrics(task_class)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_created_at ON memory_metrics(created_at)")
                
        except Exception as e:
            logger.error(f"Failed to ensure memory metrics schema: {e}")
    
    def record_run_metrics(self,
                          run_id: int,
                          task_class: str,
                          memory_hits: int = 0,
                          memory_primer_tokens: int = 0,
                          memory_store_size: int = 0,
                          used_memory: bool = False,
                          lift_source: str = 'none',
                          reward_delta: float = 0.0) -> None:
        """Record memory metrics for a specific run."""
        try:
            # Calculate rolling hit rate and avg lift
            hit_rate = self._calculate_hit_rate(task_class)
            avg_lift = self._calculate_avg_reward_lift(task_class)
            
            # Record metrics
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO memory_metrics (
                        run_id, task_class, memory_hits, memory_hit_rate,
                        memory_avg_reward_lift, memory_primer_tokens, memory_store_size,
                        used_memory, lift_source
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    run_id, task_class, memory_hits, hit_rate, avg_lift,
                    memory_primer_tokens, memory_store_size, used_memory, lift_source
                ))
                
            logger.debug(f"Recorded memory metrics for run {run_id}: hits={memory_hits}, tokens={memory_primer_tokens}")
            
        except Exception as e:
            logger.error(f"Failed to record memory metrics: {e}")
    
    def get_analytics(self, days_back: int = 30) -> Dict[str, Any]:
        """Get comprehensive memory analytics."""
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days_back)
            
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                # Overall metrics
                cursor = conn.execute("""
                    SELECT 
                        AVG(CASE WHEN memory_hits > 0 THEN 1.0 ELSE 0.0 END) as hit_rate,
                        AVG(CASE WHEN used_memory = 1 THEN memory_avg_reward_lift ELSE NULL END) as avg_reward_lift,
                        MAX(memory_store_size) as store_size,
                        AVG(memory_primer_tokens) as avg_primer_tokens,
                        COUNT(*) as total_runs
                    FROM memory_metrics
                    WHERE created_at >= ?
                """, (cutoff_date.isoformat(),))
                
                overall = cursor.fetchone()
                
                # Per-task-class breakdown
                cursor = conn.execute("""
                    SELECT 
                        task_class,
                        AVG(CASE WHEN memory_hits > 0 THEN 1.0 ELSE 0.0 END) as hit_rate,
                        AVG(CASE WHEN used_memory = 1 THEN memory_avg_reward_lift ELSE NULL END) as avg_lift,
                        COUNT(*) as runs_count
                    FROM memory_metrics
                    WHERE created_at >= ?
                    GROUP BY task_class
                    ORDER BY hit_rate DESC
                """, (cutoff_date.isoformat(),))
                
                by_task_class = [dict(row) for row in cursor.fetchall()]
                
                # Primer token percentiles
                cursor = conn.execute("""
                    SELECT memory_primer_tokens
                    FROM memory_metrics 
                    WHERE created_at >= ? AND memory_primer_tokens > 0
                    ORDER BY memory_primer_tokens
                """, (cutoff_date.isoformat(),))
                
                token_counts = [row[0] for row in cursor.fetchall()]
                
                p50_tokens = _percentile(token_counts, 50) if token_counts else 0
                p95_tokens = _percentile(token_counts, 95) if token_counts else 0
                
                return {
                    "hit_rate": overall["hit_rate"] or 0.0,
                    "avg_reward_lift": overall["avg_reward_lift"] or 0.0,
                    "store_size": overall["store_size"] or 0,
                    "primer_tokens_p50": p50_tokens,
                    "primer_tokens_p95": p95_tokens,
                    "total_runs": overall["total_runs"] or 0,
                    "by_task_class": by_task_class,
                    "days_analyzed": days_back
                }
                
        except Exception as e:
            logger.error(f"Failed to get memory analytics: {e}")
            return {}
    
    def _calculate_hit_rate(self, task_class: str, window_size: int = 10) -> float:
        """Calculate rolling hit rate for task class."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT AVG(CASE WHEN memory_hits > 0 THEN 1.0 ELSE 0.0 END) as hit_rate
                    FROM (
                        SELECT memory_hits
                        FROM memory_metrics
                        WHERE task_class = ?
                        ORDER BY created_at DESC
                        LIMIT ?
                    )
                """, (task_class, window_size))
                
                result = cursor.fetchone()
                return result[0] if result[0] is not None else 0.0
                
        except Exception as e:
            logger.error(f"Failed to calculate hit rate: {e}")
            return 0.0
    
    def _calculate_avg_reward_lift(self, task_class: str, window_size: int = 10) -> float:
        """Calculate rolling average reward lift for task class."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT AVG(memory_avg_reward_lift) as avg_lift
                    FROM (
                        SELECT memory_avg_reward_lift
                        FROM memory_metrics
                        WHERE task_class = ? AND used_memory = 1 AND memory_avg_reward_lift IS NOT NULL
                        ORDER BY created_at DESC
                        LIMIT ?
                    )
                """, (task_class, window_size))
                
                result = cursor.fetchone()
                return result[0] if result[0] is not None else 0.0
                
        except Exception as e:
            logger.error(f"Failed to calculate avg reward lift: {e}")
            return 0.0
    
    def get_recent_runs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent runs with memory metrics."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                cursor = conn.execute("""
                    SELECT 
                        run_id, task_class, memory_hits, memory_primer_tokens,
                        memory_store_size, used_memory, lift_source, created_at
                    FROM memory_metrics
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (limit,))
                
                return [dict(row) for row in cursor.fetchall()]
                
        except Exception as e:
            logger.error(f"Failed to get recent runs: {e}")
            return []

def _percentile(data: List[float], percentile: int) -> float:
    """Calculate percentile of data."""
    if not data:
        return 0.0
        
    sorted_data = sorted(data)
    index = (percentile / 100.0) * (len(sorted_data) - 1)
    
    if index.is_integer():
        return sorted_data[int(index)]
    else:
        lower_index = int(index)
        upper_index = lower_index + 1
        weight = index - lower_index
        
        if upper_index >= len(sorted_data):
            return sorted_data[-1]
            
        return sorted_data[lower_index] * (1 - weight) + sorted_data[upper_index] * weight

# Global instance
_metrics_tracker = None

def get_memory_metrics_tracker() -> MemoryMetricsTracker:
    """Get global memory metrics tracker instance."""
    global _metrics_tracker
    if _metrics_tracker is None:
        _metrics_tracker = MemoryMetricsTracker()
    return _metrics_tracker