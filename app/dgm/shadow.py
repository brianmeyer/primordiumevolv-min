"""
DGM Shadow Evaluation - Stage-2 evaluation without live mutations

Runs baseline vs patched code on a Golden subset to measure performance
differences safely without affecting live task execution.
"""

import logging
import time
import json
import tempfile
import os
import shutil
import subprocess
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from app.dgm.types import MetaPatch
from app.config import DGM_GOLDEN_SUBSET_SIZE, DGM_SHADOW_TIMEOUT

logger = logging.getLogger(__name__)


class ShadowResult:
    """Result of shadow evaluation for a single patch."""
    
    def __init__(self, patch_id: str):
        self.patch_id = patch_id
        self.baseline_score: Optional[float] = None
        self.patched_score: Optional[float] = None
        self.baseline_latency_ms: Optional[int] = None
        self.patched_latency_ms: Optional[int] = None
        self.baseline_error: Optional[str] = None
        self.patched_error: Optional[str] = None
        self.improvement_score: Optional[float] = None
        self.latency_delta_ms: Optional[int] = None
        self.execution_time_ms: Optional[int] = None
        
    def is_valid(self) -> bool:
        """Check if evaluation completed successfully."""
        return (
            self.baseline_score is not None and 
            self.patched_score is not None and
            self.baseline_error is None and
            self.patched_error is None
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "patch_id": self.patch_id,
            "baseline_score": self.baseline_score,
            "patched_score": self.patched_score,
            "baseline_latency_ms": self.baseline_latency_ms,
            "patched_latency_ms": self.patched_latency_ms,
            "baseline_error": self.baseline_error,
            "patched_error": self.patched_error,
            "improvement_score": self.improvement_score,
            "latency_delta_ms": self.latency_delta_ms,
            "execution_time_ms": self.execution_time_ms,
            "is_valid": self.is_valid()
        }


def _get_golden_subset(size: int = None) -> List[Dict[str, Any]]:
    """
    Get Golden subset of tasks for shadow evaluation.
    
    Args:
        size: Number of items to return (default from config)
        
    Returns:
        List of task dictionaries for evaluation
    """
    target_size = size or DGM_GOLDEN_SUBSET_SIZE
    
    # Create a deterministic golden subset for consistent evaluation
    golden_tasks = [
        {
            "id": f"golden_task_{i+1}",
            "prompt": f"Analyze the following data and provide insights: Dataset {i+1}",
            "expected_quality": 0.7 + (i * 0.05),  # Varying difficulty
            "timeout_ms": 5000
        }
        for i in range(min(target_size, 25))  # Cap at 25 for M1 safety
    ]
    
    logger.info(f"Generated {len(golden_tasks)} golden tasks for shadow evaluation")
    return golden_tasks


def _apply_patch_to_temp(patch: MetaPatch, base_dir: str) -> str:
    """
    Apply patch to temporary directory for shadow testing.
    
    Args:
        patch: MetaPatch to apply
        base_dir: Base directory to copy from
        
    Returns:
        Path to temporary directory with patch applied
    """
    # Create temporary directory
    temp_dir = tempfile.mkdtemp(prefix=f"shadow_{patch.id}_")
    
    try:
        # Copy base directory to temp
        shutil.copytree(base_dir, temp_dir, dirs_exist_ok=True)
        
        # Apply patch using git apply
        patch_file = os.path.join(temp_dir, f"{patch.id}.patch")
        with open(patch_file, 'w') as f:
            f.write(patch.diff)
        
        # Apply patch
        result = subprocess.run(
            ['git', 'apply', '--ignore-whitespace', patch_file],
            cwd=temp_dir,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            logger.error(f"Failed to apply patch {patch.id}: {result.stderr}")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return None
        
        # Remove patch file
        os.remove(patch_file)
        return temp_dir
        
    except Exception as e:
        logger.error(f"Error applying patch {patch.id}: {e}")
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        return None


def _evaluate_task_performance(task: Dict[str, Any], cwd: str, timeout_ms: int) -> Tuple[Optional[float], Optional[int], Optional[str]]:
    """
    Evaluate performance of a single task in given directory.
    
    Args:
        task: Task to evaluate
        cwd: Working directory to run evaluation in
        timeout_ms: Timeout in milliseconds
        
    Returns:
        Tuple of (score, latency_ms, error_msg)
    """
    start_time = time.time()
    
    try:
        # Mock evaluation - in real implementation this would:
        # 1. Set up environment with the code in cwd
        # 2. Run the task using the meta-learning system
        # 3. Measure quality score and latency
        
        # For now, simulate with simple task processing
        prompt = task.get("prompt", "")
        expected_quality = task.get("expected_quality", 0.5)
        
        # Simulate processing time proportional to prompt length
        processing_time = min(len(prompt) * 0.01, timeout_ms / 1000.0)
        time.sleep(processing_time)
        
        # Simulate quality score with some variance
        import random
        base_score = expected_quality
        variance = random.uniform(-0.1, 0.1)
        score = max(0.0, min(1.0, base_score + variance))
        
        latency_ms = int((time.time() - start_time) * 1000)
        
        return score, latency_ms, None
        
    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        return None, latency_ms, str(e)


def evaluate_patch_shadow(patch: MetaPatch, golden_tasks: List[Dict[str, Any]] = None) -> ShadowResult:
    """
    Evaluate a single patch using shadow evaluation.
    
    Args:
        patch: MetaPatch to evaluate
        golden_tasks: Optional list of tasks (uses default golden subset if None)
        
    Returns:
        ShadowResult with evaluation metrics
    """
    result = ShadowResult(patch.id)
    start_time = time.time()
    
    try:
        # Get golden tasks
        tasks = golden_tasks or _get_golden_subset()
        logger.info(f"Shadow evaluating patch {patch.id} on {len(tasks)} golden tasks")
        
        # Get current working directory as baseline
        baseline_dir = os.getcwd()
        
        # Apply patch to temporary directory
        patched_dir = _apply_patch_to_temp(patch, baseline_dir)
        if not patched_dir:
            result.patched_error = "Failed to apply patch"
            return result
        
        try:
            baseline_scores = []
            patched_scores = []
            baseline_latencies = []
            patched_latencies = []
            
            # Evaluate each task on baseline and patched versions
            for task in tasks:
                timeout_ms = task.get("timeout_ms", DGM_SHADOW_TIMEOUT * 1000)  # Convert seconds to ms
                
                # Baseline evaluation
                base_score, base_latency, base_error = _evaluate_task_performance(
                    task, baseline_dir, timeout_ms
                )
                
                if base_error:
                    logger.warning(f"Baseline error for task {task['id']}: {base_error}")
                    continue
                
                # Patched evaluation
                patch_score, patch_latency, patch_error = _evaluate_task_performance(
                    task, patched_dir, timeout_ms
                )
                
                if patch_error:
                    logger.warning(f"Patched error for task {task['id']}: {patch_error}")
                    continue
                
                # Collect valid results
                baseline_scores.append(base_score)
                patched_scores.append(patch_score)
                baseline_latencies.append(base_latency)
                patched_latencies.append(patch_latency)
            
            # Calculate aggregate metrics
            if baseline_scores and patched_scores:
                result.baseline_score = sum(baseline_scores) / len(baseline_scores)
                result.patched_score = sum(patched_scores) / len(patched_scores)
                result.baseline_latency_ms = int(sum(baseline_latencies) / len(baseline_latencies))
                result.patched_latency_ms = int(sum(patched_latencies) / len(patched_latencies))
                
                # Calculate deltas
                result.improvement_score = result.patched_score - result.baseline_score
                result.latency_delta_ms = result.patched_latency_ms - result.baseline_latency_ms
                
                logger.info(f"Shadow evaluation completed: score_delta={result.improvement_score:.3f}, "
                           f"latency_delta={result.latency_delta_ms}ms")
            else:
                result.baseline_error = "No valid task evaluations"
                
        finally:
            # Clean up temporary directory
            if os.path.exists(patched_dir):
                shutil.rmtree(patched_dir, ignore_errors=True)
        
    except Exception as e:
        logger.error(f"Shadow evaluation failed for patch {patch.id}: {e}")
        result.baseline_error = f"Evaluation exception: {str(e)}"
    
    finally:
        result.execution_time_ms = int((time.time() - start_time) * 1000)
    
    return result


def evaluate_patches_shadow(patches: List[MetaPatch]) -> List[ShadowResult]:
    """
    Evaluate multiple patches using shadow evaluation.
    
    Args:
        patches: List of MetaPatch objects to evaluate
        
    Returns:
        List of ShadowResult objects
    """
    logger.info(f"Starting shadow evaluation of {len(patches)} patches")
    
    # Get shared golden tasks for consistent comparison
    golden_tasks = _get_golden_subset()
    
    results = []
    for patch in patches:
        try:
            result = evaluate_patch_shadow(patch, golden_tasks)
            results.append(result)
        except Exception as e:
            logger.error(f"Failed to evaluate patch {patch.id}: {e}")
            error_result = ShadowResult(patch.id)
            error_result.baseline_error = f"Evaluation failed: {str(e)}"
            results.append(error_result)
    
    # Log summary
    valid_results = [r for r in results if r.is_valid()]
    logger.info(f"Shadow evaluation completed: {len(valid_results)}/{len(results)} patches evaluated successfully")
    
    return results


# Statistics and monitoring
_shadow_stats = {
    "total_evaluations": 0,
    "successful_evaluations": 0,
    "failed_evaluations": 0,
    "avg_execution_time_ms": 0,
    "last_golden_size": 0
}


def get_shadow_stats() -> Dict[str, Any]:
    """Get shadow evaluation statistics."""
    return _shadow_stats.copy()


def reset_shadow_stats():
    """Reset shadow evaluation statistics."""
    global _shadow_stats
    _shadow_stats = {
        "total_evaluations": 0,
        "successful_evaluations": 0,
        "failed_evaluations": 0,
        "avg_execution_time_ms": 0,
        "last_golden_size": 0
    }