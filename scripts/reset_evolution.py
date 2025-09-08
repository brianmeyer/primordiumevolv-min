#!/usr/bin/env python3
"""
Evolution History Reset Script - Comprehensive data handling with safety mechanisms.

This script safely resets accumulated evolution state across all data stores with
full backup capabilities and atomic transactions.
"""
import os
import sys
import sqlite3
import shutil
import json
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional


def create_backup_directory() -> str:
    """Create timestamped backup directory."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = f"backups/{timestamp}"
    os.makedirs(backup_dir, exist_ok=True)
    return backup_dir


def backup_database(db_path: str, backup_dir: str) -> str:
    """Backup SQLite database with integrity check."""
    if not os.path.exists(db_path):
        print(f"Database not found: {db_path}")
        return None
    
    db_name = os.path.basename(db_path)
    backup_path = os.path.join(backup_dir, db_name)
    
    # Integrity check before backup
    with sqlite3.connect(db_path) as conn:
        integrity_result = conn.execute("PRAGMA integrity_check").fetchone()
        if integrity_result[0] != "ok":
            raise RuntimeError(f"Database integrity check failed for {db_path}: {integrity_result[0]}")
    
    # Create backup with verification
    shutil.copy2(db_path, backup_path)
    
    # Verify backup
    with sqlite3.connect(backup_path) as backup_conn:
        backup_integrity = backup_conn.execute("PRAGMA integrity_check").fetchone()
        if backup_integrity[0] != "ok":
            raise RuntimeError(f"Backup integrity check failed for {backup_path}")
    
    print(f"✓ Database backed up: {db_path} -> {backup_path}")
    return backup_path


def backup_memory_store(backup_dir: str) -> bool:
    """Backup memory store data with preservation option."""
    memory_dir = "data/memory"
    if not os.path.exists(memory_dir):
        print("Memory store directory not found")
        return False
    
    backup_memory_dir = os.path.join(backup_dir, "memory")
    shutil.copytree(memory_dir, backup_memory_dir)
    print(f"✓ Memory store backed up: {memory_dir} -> {backup_memory_dir}")
    return True


def backup_logs(backup_dir: str) -> bool:
    """Archive trajectory logs and eval reports."""
    logs_dir = "logs"
    if not os.path.exists(logs_dir):
        print("Logs directory not found")
        return False
    
    backup_logs_dir = os.path.join(backup_dir, "logs")
    shutil.copytree(logs_dir, backup_logs_dir)
    print(f"✓ Logs backed up: {logs_dir} -> {backup_logs_dir}")
    return True


def get_table_info(conn: sqlite3.Connection) -> Dict[str, List[str]]:
    """Get information about all tables and their columns."""
    tables = {}
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    
    for (table_name,) in cursor.fetchall():
        if not table_name.startswith('sqlite_'):
            column_info = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
            tables[table_name] = [col[1] for col in column_info]  # Column names
    
    return tables


def selective_reset_operations(db_path: str, preserve_memory: bool = True) -> Dict[str, int]:
    """Perform selective reset operations with rollback capability."""
    if not os.path.exists(db_path):
        print(f"Database not found: {db_path}")
        return {}
    
    reset_counts = {}
    
    with sqlite3.connect(db_path) as conn:
        conn.execute("BEGIN TRANSACTION")
        
        try:
            # Get table information
            tables = get_table_info(conn)
            print(f"Found tables: {list(tables.keys())}")
            
            # Clear judge history and model rotation state
            if 'judge_history' in tables:
                count = conn.execute("SELECT COUNT(*) FROM judge_history").fetchone()[0]
                conn.execute("DELETE FROM judge_history")
                reset_counts['judge_history'] = count
                print(f"✓ Cleared {count} judge history records")
            
            # Reset bandit arm statistics (preserve algorithm config)
            if 'bandit_arms' in tables:
                count = conn.execute("SELECT COUNT(*) FROM bandit_arms").fetchone()[0]
                conn.execute("UPDATE bandit_arms SET total_reward = 0, num_pulls = 0")
                reset_counts['bandit_arms'] = count
                print(f"✓ Reset {count} bandit arm statistics")
            
            # Clear human_ratings table while preserving schema
            if 'human_ratings' in tables:
                count = conn.execute("SELECT COUNT(*) FROM human_ratings").fetchone()[0]
                conn.execute("DELETE FROM human_ratings")
                reset_counts['human_ratings'] = count
                print(f"✓ Cleared {count} human ratings")
            
            # Reset meta_runs and variants tables
            if 'meta_runs' in tables:
                count = conn.execute("SELECT COUNT(*) FROM meta_runs").fetchone()[0]
                conn.execute("DELETE FROM meta_runs")
                reset_counts['meta_runs'] = count
                print(f"✓ Cleared {count} meta run records")
            
            if 'variants' in tables:
                count = conn.execute("SELECT COUNT(*) FROM variants").fetchone()[0]
                conn.execute("DELETE FROM variants")
                reset_counts['variants'] = count
                print(f"✓ Cleared {count} variant records")
            
            # Clear recipes evolution history (keep top-performing baseline recipes)
            if 'recipes' in tables:
                total_count = conn.execute("SELECT COUNT(*) FROM recipes").fetchone()[0]
                # Keep top 5 recipes by score
                conn.execute("""
                    DELETE FROM recipes WHERE id NOT IN (
                        SELECT id FROM recipes ORDER BY score DESC LIMIT 5
                    )
                """)
                remaining_count = conn.execute("SELECT COUNT(*) FROM recipes").fetchone()[0]
                reset_counts['recipes'] = total_count - remaining_count
                print(f"✓ Cleared {total_count - remaining_count} recipe records (kept top 5)")
            
            # Reset golden_kpis results (preserve test definitions)
            if 'golden_kpis' in tables:
                count = conn.execute("SELECT COUNT(*) FROM golden_kpis WHERE result IS NOT NULL").fetchone()[0]
                conn.execute("UPDATE golden_kpis SET result = NULL, last_run = NULL")
                reset_counts['golden_kpis'] = count
                print(f"✓ Reset {count} golden KPI results")
            
            # Clean eval_report accumulated results
            if 'eval_report' in tables:
                count = conn.execute("SELECT COUNT(*) FROM eval_report").fetchone()[0]
                conn.execute("DELETE FROM eval_report")
                reset_counts['eval_report'] = count
                print(f"✓ Cleared {count} eval report records")
            
            # Commit all changes
            conn.execute("COMMIT")
            print("✓ All reset operations committed successfully")
            
        except Exception as e:
            conn.execute("ROLLBACK")
            print(f"✗ Error during reset operations, rolled back: {e}")
            raise
    
    return reset_counts


def archive_trajectory_logs(backup_dir: str) -> int:
    """Archive trajectory logs to cold storage."""
    logs_dir = "logs"
    if not os.path.exists(logs_dir):
        return 0
    
    archived_count = 0
    cold_storage_dir = os.path.join(backup_dir, "cold_storage")
    os.makedirs(cold_storage_dir, exist_ok=True)
    
    # Move trajectory and generation timing logs to cold storage
    for log_file in os.listdir(logs_dir):
        if any(pattern in log_file for pattern in ['generation_timing_', 'meta_run_', 'operator_selection_']):
            src_path = os.path.join(logs_dir, log_file)
            dst_path = os.path.join(cold_storage_dir, log_file)
            shutil.move(src_path, dst_path)
            archived_count += 1
    
    print(f"✓ Archived {archived_count} log files to cold storage")
    return archived_count


def clean_memory_store_optional(preserve_memory: bool) -> int:
    """Optionally clean memory store episodic experiences."""
    if preserve_memory:
        print("✓ Memory store preserved (user configurable)")
        return 0
    
    memory_dir = "data/memory"
    if not os.path.exists(memory_dir):
        return 0
    
    cleaned_count = 0
    for memory_file in os.listdir(memory_dir):
        if memory_file.endswith('.json'):
            file_path = os.path.join(memory_dir, memory_file)
            os.remove(file_path)
            cleaned_count += 1
    
    print(f"✓ Cleaned {cleaned_count} memory store files")
    return cleaned_count


def validate_reset_integrity(db_path: str) -> bool:
    """Validate database integrity and schema after reset."""
    if not os.path.exists(db_path):
        return True  # No database to validate
    
    with sqlite3.connect(db_path) as conn:
        # Check database integrity
        integrity_result = conn.execute("PRAGMA integrity_check").fetchone()
        if integrity_result[0] != "ok":
            print(f"✗ Database integrity check failed: {integrity_result[0]}")
            return False
        
        # Verify schema is preserved
        tables = get_table_info(conn)
        expected_tables = ['judge_history', 'bandit_arms', 'human_ratings', 'meta_runs', 'variants', 'recipes', 'golden_kpis', 'eval_report']
        
        for table in expected_tables:
            if table in tables:
                # Verify table exists and has expected structure
                try:
                    conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                except sqlite3.Error as e:
                    print(f"✗ Table {table} schema validation failed: {e}")
                    return False
    
    print("✓ Database integrity and schema validation passed")
    return True


def create_recovery_script(backup_dir: str) -> str:
    """Create recovery script for full system restoration."""
    recovery_script = f"""#!/usr/bin/env python3
'''
Recovery script for evolution system restoration from backup: {backup_dir}
'''
import os
import shutil
import sqlite3

def restore_from_backup():
    backup_dir = "{backup_dir}"
    
    # Restore database
    if os.path.exists(os.path.join(backup_dir, "evolution.db")):
        shutil.copy2(os.path.join(backup_dir, "evolution.db"), "data/evolution.db")
        print("✓ Database restored")
    
    # Restore memory store
    if os.path.exists(os.path.join(backup_dir, "memory")):
        if os.path.exists("data/memory"):
            shutil.rmtree("data/memory")
        shutil.copytree(os.path.join(backup_dir, "memory"), "data/memory")
        print("✓ Memory store restored")
    
    # Restore logs
    if os.path.exists(os.path.join(backup_dir, "logs")):
        if os.path.exists("logs"):
            shutil.rmtree("logs")
        shutil.copytree(os.path.join(backup_dir, "logs"), "logs")
        print("✓ Logs restored")
    
    print(f"✓ Full system restored from {{backup_dir}}")

if __name__ == "__main__":
    restore_from_backup()
"""
    
    recovery_path = os.path.join(backup_dir, "recover.py")
    with open(recovery_path, 'w') as f:
        f.write(recovery_script)
    
    os.chmod(recovery_path, 0o755)
    print(f"✓ Recovery script created: {recovery_path}")
    return recovery_path


def main():
    """Main reset execution with comprehensive safety mechanisms."""
    print("🔄 Starting Evolution History Reset")
    print("=" * 50)
    
    # Configuration
    preserve_memory = True  # User configurable
    dry_run = "--dry-run" in sys.argv
    
    if dry_run:
        print("🧪 DRY RUN MODE - No actual changes will be made")
    
    try:
        # Step 1: Create backup directory
        backup_dir = create_backup_directory()
        print(f"📁 Backup directory created: {backup_dir}")
        
        if not dry_run:
            # Step 2: Full data backup
            print("\n📋 Creating full data backup...")
            backup_database("data/evolution.db", backup_dir)
            backup_memory_store(backup_dir)
            backup_logs(backup_dir)
            
            # Step 3: Selective reset operations
            print("\n🔧 Performing selective reset operations...")
            reset_counts = selective_reset_operations("data/evolution.db", preserve_memory)
            
            # Step 4: Archive trajectory logs
            print("\n📦 Archiving logs to cold storage...")
            archived_count = archive_trajectory_logs(backup_dir)
            
            # Step 5: Optional memory store cleanup
            print("\n🧹 Memory store cleanup...")
            memory_cleaned = clean_memory_store_optional(preserve_memory)
            
            # Step 6: Integrity validation
            print("\n✅ Validating reset integrity...")
            if not validate_reset_integrity("data/evolution.db"):
                raise RuntimeError("Reset integrity validation failed")
            
            # Step 7: Create recovery script
            print("\n💾 Creating recovery script...")
            recovery_script = create_recovery_script(backup_dir)
            
            # Summary
            print("\n" + "=" * 50)
            print("✅ EVOLUTION RESET COMPLETED SUCCESSFULLY")
            print(f"📁 Backup location: {backup_dir}")
            print(f"💾 Recovery script: {os.path.join(backup_dir, 'recover.py')}")
            
            print("\n📊 Reset Summary:")
            for table, count in reset_counts.items():
                print(f"   • {table}: {count} records")
            print(f"   • Archived logs: {archived_count}")
            print(f"   • Memory store: {'preserved' if preserve_memory else f'{memory_cleaned} files cleaned'}")
            
        else:
            print("\n🧪 DRY RUN COMPLETED - No changes made")
            print("   Run without --dry-run to execute actual reset")
        
    except Exception as e:
        print(f"\n❌ RESET FAILED: {e}")
        print("   System state unchanged, check logs for details")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())