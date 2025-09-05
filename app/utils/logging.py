"""
ISO8601 logging utilities for PrimordiumEvolv.
"""

import json
import os
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional

def iso8601_now() -> str:
    """Get current timestamp in ISO8601 format."""
    return datetime.now(timezone.utc).isoformat()

def log_artifact(artifact_type: str, data: Dict[str, Any], 
                artifacts_dir: str = "logs", 
                filename: Optional[str] = None) -> str:
    """
    Log structured artifact with ISO8601 timestamp.
    
    Args:
        artifact_type: Type of artifact (e.g., "meta_run", "operator_selection")
        data: Artifact data to log
        artifacts_dir: Directory to store logs
        filename: Optional custom filename (defaults to timestamped name)
        
    Returns:
        Path to written log file
    """
    os.makedirs(artifacts_dir, exist_ok=True)
    
    if filename is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:-3]  # ms precision
        filename = f"{artifact_type}_{timestamp}.json"
    
    filepath = os.path.join(artifacts_dir, filename)
    
    # Wrap data with metadata
    log_entry = {
        "artifact_type": artifact_type,
        "timestamp": iso8601_now(),
        "unix_timestamp": time.time(),
        "data": data
    }
    
    with open(filepath, "w") as f:
        json.dump(log_entry, f, indent=2, ensure_ascii=False)
    
    return filepath

def log_meta_run_start(run_id: int, task_class: str, task: str, 
                      config: Dict[str, Any], artifacts_dir: str = "logs") -> str:
    """Log meta-evolution run start."""
    return log_artifact("meta_run_start", {
        "run_id": run_id,
        "task_class": task_class,
        "task": task,
        "config": config
    }, artifacts_dir)

def log_meta_run_finish(run_id: int, best_score: float, 
                       total_iterations: int, artifacts_dir: str = "logs") -> str:
    """Log meta-evolution run completion.""" 
    return log_artifact("meta_run_finish", {
        "run_id": run_id,
        "best_score": best_score,
        "total_iterations": total_iterations
    }, artifacts_dir)

def log_operator_selection(run_id: int, iteration: int, operator: str,
                          selection_method: str, artifacts_dir: str = "logs") -> str:
    """Log operator selection event."""
    return log_artifact("operator_selection", {
        "run_id": run_id,
        "iteration": iteration,
        "operator": operator,
        "selection_method": selection_method
    }, artifacts_dir)

def log_generation_timing(run_id: int, iteration: int, operator: str,
                         duration_ms: int, artifacts_dir: str = "logs") -> str:
    """Log generation timing event."""
    return log_artifact("generation_timing", {
        "run_id": run_id,
        "iteration": iteration,
        "operator": operator,
        "duration_ms": duration_ms
    }, artifacts_dir)

def log_error(error_type: str, error_detail: str, context: Dict[str, Any],
              artifacts_dir: str = "logs") -> str:
    """Log structured error event."""
    return log_artifact("error", {
        "error_type": error_type,
        "error_detail": error_detail,
        "context": context
    }, artifacts_dir)