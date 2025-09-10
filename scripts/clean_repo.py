#!/usr/bin/env python3
"""
Repository cleanup script for safe deletion of temporary files and runtime artifacts.

Reads DELETE_PLAN.md and provides --dry-run and --execute modes with retention policies.
"""

import os
import sys
import argparse
import shutil
import glob
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple


def parse_delete_plan() -> List[str]:
    """Parse DELETE_PLAN.md and extract targets for deletion."""
    delete_plan_path = Path("DELETE_PLAN.md")
    if not delete_plan_path.exists():
        print("❌ DELETE_PLAN.md not found")
        return []
    
    targets = []
    with open(delete_plan_path) as f:
        content = f.read()
    
    # Extract targets from DELETE_PLAN.md
    # Look for patterns like:
    # .reset_live.out
    # .uvicorn.pid
    # backups/
    # logs/
    # runs/
    
    lines = content.split('\n')
    for line in lines:
        line = line.strip()
        if line and not line.startswith('#') and not line.startswith('**'):
            # Remove markdown code block markers and comments
            if line.startswith('```') or line.startswith('└──') or line.startswith('├──'):
                continue
            if '#' in line:
                line = line.split('#')[0].strip()
            if line and not line.startswith('-'):
                targets.append(line)
    
    # Add known targets from DELETE_PLAN.md
    known_targets = [
        ".reset_live.out",
        ".uvicorn.pid", 
        "backups/",
        "logs/",
        "runs/"
    ]
    
    return known_targets


def get_directory_with_retention(directory: str, keep_count: int) -> Tuple[List[str], List[str]]:
    """
    Get files/directories to delete and keep based on modification time.
    
    Args:
        directory: Directory to scan
        keep_count: Number of most recent items to keep
        
    Returns:
        Tuple of (items_to_delete, items_to_keep)
    """
    if not os.path.exists(directory):
        return [], []
    
    items = []
    for item in os.listdir(directory):
        item_path = os.path.join(directory, item)
        if os.path.isfile(item_path) or os.path.isdir(item_path):
            mtime = os.path.getmtime(item_path)
            items.append((item_path, mtime))
    
    # Sort by modification time (newest first)
    items.sort(key=lambda x: x[1], reverse=True)
    
    items_to_keep = items[:keep_count]
    items_to_delete = items[keep_count:]
    
    return [item[0] for item in items_to_delete], [item[0] for item in items_to_keep]


def apply_retention_policy(targets: List[str], keep_patterns: Dict[str, int]) -> Dict[str, Dict]:
    """Apply retention policies to targets."""
    result = {
        "delete": [],
        "keep": [],
        "skip": []
    }
    
    for target in targets:
        if target.endswith('/'):
            # Directory target
            base_dir = target.rstrip('/')
            if base_dir in keep_patterns:
                to_delete, to_keep = get_directory_with_retention(base_dir, keep_patterns[base_dir])
                result["delete"].extend(to_delete)
                result["keep"].extend(to_keep)
            else:
                # Delete entire directory
                if os.path.exists(target):
                    result["delete"].append(target)
        else:
            # File target
            if os.path.exists(target):
                result["delete"].append(target)
    
    return result


def print_table(items: List[str], title: str):
    """Print a formatted table of items."""
    if not items:
        return
        
    print(f"\n{title}:")
    print("-" * 60)
    for i, item in enumerate(items, 1):
        size = "N/A"
        try:
            if os.path.isfile(item):
                size = f"{os.path.getsize(item) / 1024:.1f} KB"
            elif os.path.isdir(item):
                size = "DIR"
        except OSError:
            pass
        print(f"{i:3d}. {item:<40} {size:>10}")


def update_gitignore():
    """Update .gitignore with required entries."""
    gitignore_path = Path(".gitignore")
    
    required_entries = [
        "logs/",
        "runs/", 
        "data/dgm_registry*.jsonl",
        ".uvicorn.pid",
        ".reset_live.out"
    ]
    
    existing_lines = set()
    if gitignore_path.exists():
        with open(gitignore_path) as f:
            existing_lines = set(line.strip() for line in f if line.strip() and not line.startswith('#'))
    
    new_entries = []
    for entry in required_entries:
        if entry not in existing_lines:
            new_entries.append(entry)
    
    if new_entries:
        with open(gitignore_path, 'a') as f:
            f.write("\n# Runtime artifacts and logs\n")
            for entry in new_entries:
                f.write(f"{entry}\n")
        print(f"✅ Updated .gitignore with {len(new_entries)} new entries")
    else:
        print("✅ .gitignore already up to date")


def main():
    parser = argparse.ArgumentParser(description="Repository cleanup script")
    parser.add_argument("--dry-run", action="store_true", default=True, 
                       help="Only print what would be deleted (default)")
    parser.add_argument("--execute", action="store_true",
                       help="Actually delete files and directories")
    parser.add_argument("--keep", action="append", default=[],
                       help="Glob patterns to keep (e.g., --keep 'runs/*')")
    
    args = parser.parse_args()
    
    if args.execute:
        args.dry_run = False
    
    print("🧹 Repository Cleanup Script")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'EXECUTE'}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    
    # Parse DELETE_PLAN.md
    targets = parse_delete_plan()
    if not targets:
        print("❌ No targets found in DELETE_PLAN.md")
        return 1
    
    print(f"📋 Found {len(targets)} targets from DELETE_PLAN.md")
    
    # Apply retention policies
    retention_policies = {
        "runs": 3,    # Keep last 3 run folders
        "logs": 5     # Keep last 5 log files
    }
    
    result = apply_retention_policy(targets, retention_policies)
    
    # Apply user keep patterns
    if args.keep:
        keep_items = set()
        for pattern in args.keep:
            keep_items.update(glob.glob(pattern, recursive=True))
        
        # Remove keep items from delete list
        result["delete"] = [item for item in result["delete"] if item not in keep_items]
        result["keep"].extend(list(keep_items))
    
    # Print summary tables
    print_table(result["delete"], f"🗑️  Items to DELETE ({len(result['delete'])})")
    print_table(result["keep"], f"📦 Items to KEEP ({len(result['keep'])})")
    
    if args.dry_run:
        print(f"\n🔍 DRY RUN: Would delete {len(result['delete'])} items")
        print("Run with --execute to perform actual deletions")
        return 0
    
    # Execute deletions
    deleted_count = 0
    error_count = 0
    
    print(f"\n🚀 EXECUTING: Deleting {len(result['delete'])} items...")
    
    for item in result["delete"]:
        try:
            if os.path.isfile(item):
                os.remove(item)
                print(f"✅ Deleted file: {item}")
            elif os.path.isdir(item):
                shutil.rmtree(item)
                print(f"✅ Deleted directory: {item}")
            deleted_count += 1
        except Exception as e:
            print(f"❌ Failed to delete {item}: {e}")
            error_count += 1
    
    # Update .gitignore
    update_gitignore()
    
    print(f"\n📊 SUMMARY:")
    print(f"   ✅ Successfully deleted: {deleted_count}")
    print(f"   ❌ Failed to delete: {error_count}")
    print(f"   📦 Items kept: {len(result['keep'])}")
    
    return 0 if error_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())