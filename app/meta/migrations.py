"""
Database migrations for Analytics V2 system.

Migrations preserve all existing evolution data while adding new functionality.
"""

import sqlite3
import time
from typing import Dict, List
from .analytics_v2 import normalize_task_class, init_analytics_v2_tables

class MigrationManager:
    """Handles database migrations safely."""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        
    def _conn(self):
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn
        
    def get_current_version(self) -> int:
        """Get current migration version."""
        conn = self._conn()
        try:
            # Create migrations table if it doesn't exist
            conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at REAL,
                    description TEXT
                )
            """)
            conn.commit()
            
            cursor = conn.execute("SELECT MAX(version) FROM schema_migrations")
            result = cursor.fetchone()
            return result[0] if result[0] is not None else 0
            
        finally:
            conn.close()
            
    def apply_migrations(self) -> List[str]:
        """Apply all pending migrations. Returns list of applied migrations."""
        current_version = self.get_current_version()
        applied = []
        
        migrations = [
            (1, "normalize_task_class_values", self._migrate_001_normalize_task_classes),
            (2, "add_deprecation_flags", self._migrate_002_add_deprecation_flags), 
            (3, "create_analytics_snapshot", self._migrate_003_create_analytics_snapshot),
            (4, "backfill_30d_snapshot", self._migrate_004_backfill_snapshots)
        ]
        
        conn = self._conn()
        try:
            for version, description, migration_func in migrations:
                if version > current_version:
                    print(f"Applying migration {version}: {description}")
                    migration_func(conn)
                    
                    # Record migration
                    conn.execute("""
                        INSERT INTO schema_migrations (version, applied_at, description)
                        VALUES (?, ?, ?)
                    """, (version, time.time(), description))
                    conn.commit()
                    
                    applied.append(f"Migration {version}: {description}")
                    
        finally:
            conn.close()
            
        return applied
        
    def _migrate_001_normalize_task_classes(self, conn: sqlite3.Connection):
        """Migration 001: Normalize task_class values while preserving originals."""
        
        # Add normalized_task_class column to runs table
        try:
            conn.execute("ALTER TABLE runs ADD COLUMN normalized_task_class TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists
            
        # Update normalized values for all existing runs
        cursor = conn.execute("SELECT id, task_class FROM runs")
        rows = cursor.fetchall()
        
        for run_id, raw_task_class in rows:
            normalized = normalize_task_class(raw_task_class)
            conn.execute("""
                UPDATE runs 
                SET normalized_task_class = ? 
                WHERE id = ?
            """, (normalized, run_id))
            
        print(f"Normalized task classes for {len(rows)} runs")
        
    def _migrate_002_add_deprecation_flags(self, conn: sqlite3.Connection):
        """Migration 002: Add deprecation flags to track obsolete operators/voices/judges."""
        
        # Create deprecated_entities table to track what's deprecated
        conn.execute("""
            CREATE TABLE IF NOT EXISTS deprecated_entities (
                entity_type TEXT, -- 'operator', 'voice', 'judge'
                entity_name TEXT,
                deprecated_at REAL,
                reason TEXT,
                PRIMARY KEY (entity_type, entity_name)
            )
        """)
        
        # Mark some initial deprecated entities (based on usage patterns)
        # This would be customized based on actual deprecated items
        deprecated_operators = []  # Add any known deprecated operators
        
        for op_name in deprecated_operators:
            conn.execute("""
                INSERT OR REPLACE INTO deprecated_entities 
                (entity_type, entity_name, deprecated_at, reason)
                VALUES ('operator', ?, ?, 'Low usage/performance')
            """, (op_name, time.time()))
            
        print(f"Added deprecation tracking for {len(deprecated_operators)} operators")
        
    def _migrate_003_create_analytics_snapshot(self, conn: sqlite3.Connection):
        """Migration 003: Create analytics_snapshot table."""
        init_analytics_v2_tables(conn)
        print("Created analytics_snapshot table")
        
    def _migrate_004_backfill_snapshots(self, conn: sqlite3.Connection):
        """Migration 004: Backfill initial snapshots for 30d window."""
        
        # Import here to avoid circular imports
        from .analytics_v2 import get_snapshot_manager
        
        # Force computation of fresh snapshots
        manager = get_snapshot_manager()
        manager.invalidate_cache()  # Clear any existing cache
        
        # Compute snapshots for different windows
        windows = [7, 30, -1]  # 7 days, 30 days, all time
        
        for window in windows:
            try:
                snapshot = manager.get_snapshot(window)
                print(f"Backfilled snapshot for {window} day window ({snapshot['meta']['computation_time_ms']}ms)")
            except Exception as e:
                print(f"Warning: Failed to backfill {window} day snapshot: {e}")

def get_migration_manager() -> MigrationManager:
    """Get migration manager instance."""
    from app.meta.store import DB_PATH
    return MigrationManager(DB_PATH)

# Convenience function to run migrations
def run_migrations() -> List[str]:
    """Run all pending migrations."""
    manager = get_migration_manager()
    return manager.apply_migrations()

if __name__ == "__main__":
    # Allow running migrations directly
    applied = run_migrations()
    if applied:
        print("Applied migrations:")
        for migration in applied:
            print(f"  - {migration}")
    else:
        print("No migrations to apply")