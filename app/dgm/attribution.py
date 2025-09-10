"""
DGM Attribution - Track which improvements come from DGM patches

This module handles attribution logic to determine if performance improvements
come from DGM patches, memory, SEAL operators, ASI, or combinations.
"""

import os
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path

logger = logging.getLogger(__name__)


def get_active_dgm_patches() -> List[str]:
    """
    Check which DGM patches are currently active in the codebase.
    
    Returns:
        List of active patch IDs based on git commits
    """
    try:
        import subprocess
        
        # Check recent commits for DGM patches
        result = subprocess.run(
            ["git", "log", "--oneline", "--grep=\\[DGM\\]", "-10"],
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode != 0:
            return []
        
        # Extract patch IDs from commit messages
        # Format: "[DGM] <patch_id> <area> ..."
        active_patches = []
        for line in result.stdout.strip().split('\n'):
            if '[DGM]' in line:
                parts = line.split('[DGM]')[1].strip().split()
                if parts:
                    patch_id = parts[0]
                    active_patches.append(patch_id)
        
        return active_patches
        
    except Exception as e:
        logger.warning(f"Failed to check active DGM patches: {e}")
        return []


def check_dgm_file_modified(file_path: str) -> Optional[str]:
    """
    Check if a file has been modified by a DGM patch.
    
    Args:
        file_path: Path to check
        
    Returns:
        Patch ID if modified by DGM, None otherwise
    """
    try:
        import subprocess
        
        # Check git blame for DGM commits
        result = subprocess.run(
            ["git", "log", "--oneline", "--grep=\\[DGM\\]", "--", file_path],
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode == 0 and result.stdout.strip():
            # Extract most recent DGM patch ID
            for line in result.stdout.strip().split('\n'):
                if '[DGM]' in line:
                    parts = line.split('[DGM]')[1].strip().split()
                    if parts:
                        return parts[0]
        
    except Exception:
        pass
    
    return None


def determine_lift_source(variant_data: Dict[str, Any], 
                         run_data: Dict[str, Any],
                         baseline_reward: Optional[float] = None) -> str:
    """
    Determine the source of performance lift for a variant.
    
    Attribution rules:
    - If DGM patch active and reward increased -> 'dgm'
    - If memory used and reward increased -> 'memory'
    - If SEAL operator used -> 'seal'
    - If ASI features used -> 'asi'
    - If multiple sources -> 'combo'
    - Otherwise -> 'none'
    
    Args:
        variant_data: Variant execution data
        run_data: Run configuration data
        baseline_reward: Baseline reward for comparison
        
    Returns:
        Lift source: 'memory'|'seal'|'asi'|'dgm'|'none'|'combo'
    """
    sources = []
    
    # Check for DGM patches
    active_patches = get_active_dgm_patches()
    if active_patches:
        # Check if this variant's files were modified by DGM
        dgm_active = False
        
        # Check key files that affect execution
        key_files = [
            "app/meta/operators.py",
            "app/meta/runner.py",
            "app/meta/rewards.py",
            "app/engines.py",
            "app/quality_judge.py"
        ]
        
        for file_path in key_files:
            patch_id = check_dgm_file_modified(file_path)
            if patch_id:
                dgm_active = True
                # Store patch ID in variant data for tracking
                variant_data['dgm_patch_id'] = patch_id
                break
        
        if dgm_active:
            # Check if reward actually improved
            current_reward = variant_data.get('total_reward') or variant_data.get('score', 0)
            if baseline_reward is not None and current_reward > baseline_reward:
                sources.append('dgm')
    
    # Check for memory usage
    if variant_data.get('use_memory') or run_data.get('use_memory'):
        sources.append('memory')
    
    # Check for SEAL operators
    operator_name = variant_data.get('operator_name', '')
    seal_operators = ['change_system', 'change_nudge', 'raise_temp', 'lower_temp', 
                     'add_fewshot', 'inject_memory', 'inject_rag']
    if operator_name in seal_operators:
        sources.append('seal')
    
    # Check for ASI features (web, advanced models)
    if variant_data.get('use_web') or run_data.get('use_web'):
        sources.append('asi')
    
    if variant_data.get('engine') == 'groq' or variant_data.get('model_id', '').startswith('llama-3'):
        sources.append('asi')
    
    # Determine final attribution
    if not sources:
        return 'none'
    elif len(sources) == 1:
        return sources[0]
    else:
        return 'combo'


def update_run_attribution(conn, run_id: int, variant_data: Dict[str, Any],
                          run_data: Dict[str, Any]) -> None:
    """
    Update run record with DGM attribution.
    
    Args:
        conn: Database connection
        run_id: Run ID to update
        variant_data: Best variant data
        run_data: Run configuration
    """
    try:
        # Determine if DGM variant was used
        used_dgm = bool(variant_data.get('dgm_patch_id'))
        
        # Get baseline reward for comparison
        c = conn.cursor()
        c.execute("""
            SELECT AVG(best_score) 
            FROM runs 
            WHERE task_class = ? 
            AND id < ?
            LIMIT 10
        """, (run_data.get('task_class'), run_id))
        
        baseline_result = c.fetchone()
        baseline_reward = baseline_result[0] if baseline_result and baseline_result[0] else None
        
        # Determine lift source
        lift_source = determine_lift_source(variant_data, run_data, baseline_reward)
        
        # Update run record
        c.execute("""
            UPDATE runs 
            SET used_dgm_variant = ?,
                lift_source = ?
            WHERE id = ?
        """, (1 if used_dgm else 0, lift_source, run_id))
        
        conn.commit()
        
        logger.info(f"Updated run {run_id} attribution: dgm={used_dgm}, source={lift_source}")
        
    except Exception as e:
        logger.error(f"Failed to update run attribution: {e}")


def get_dgm_statistics(conn) -> Dict[str, Any]:
    """
    Get DGM usage and performance statistics.
    
    Args:
        conn: Database connection
        
    Returns:
        Dictionary with DGM statistics
    """
    try:
        c = conn.cursor()
        
        # Total runs with DGM
        c.execute("SELECT COUNT(*) FROM runs WHERE used_dgm_variant = 1")
        dgm_runs = c.fetchone()[0]
        
        # Total runs
        c.execute("SELECT COUNT(*) FROM runs")
        total_runs = c.fetchone()[0]
        
        # Lift source breakdown
        c.execute("""
            SELECT lift_source, COUNT(*) as count, AVG(best_score) as avg_score
            FROM runs
            WHERE lift_source IS NOT NULL
            GROUP BY lift_source
        """)
        
        lift_breakdown = {}
        for row in c.fetchall():
            lift_breakdown[row[0]] = {
                'count': row[1],
                'avg_score': row[2]
            }
        
        # DGM patch usage
        c.execute("""
            SELECT dgm_patch_id, COUNT(*) as usage_count, AVG(score) as avg_score
            FROM variants
            WHERE dgm_patch_id IS NOT NULL
            GROUP BY dgm_patch_id
        """)
        
        patch_usage = {}
        for row in c.fetchall():
            patch_usage[row[0]] = {
                'usage_count': row[1],
                'avg_score': row[2]
            }
        
        return {
            'dgm_runs': dgm_runs,
            'total_runs': total_runs,
            'dgm_usage_rate': dgm_runs / total_runs if total_runs > 0 else 0,
            'lift_source_breakdown': lift_breakdown,
            'patch_usage': patch_usage
        }
        
    except Exception as e:
        logger.error(f"Failed to get DGM statistics: {e}")
        return {
            'dgm_runs': 0,
            'total_runs': 0,
            'dgm_usage_rate': 0,
            'lift_source_breakdown': {},
            'patch_usage': {}
        }