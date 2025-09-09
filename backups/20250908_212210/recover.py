#!/usr/bin/env python3
'''
Recovery script for evolution system restoration from backup: backups/20250908_212210
'''
import os
import shutil
import sqlite3

def restore_from_backup():
    backup_dir = "backups/20250908_212210"
    
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
    
    print(f"✓ Full system restored from {backup_dir}")

if __name__ == "__main__":
    restore_from_backup()
