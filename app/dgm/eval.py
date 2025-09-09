"""
DGM Shadow Evaluation - Test patches against Golden Set without affecting live outputs

This module implements shadow evaluation that runs proposed patches against
a subset of the Golden Set to measure performance impact before deployment.
"""

import os
import json
import time
import logging
import tempfile
import shutil
import statistics
from glob import glob
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from app.dgm.types import MetaPatch
from app.config import DGM_CANARY_RUNS, DGM_SHADOW_TIMEOUT, DGM_BASELINE_SAMPLES, DGM_MIN_REWARD_DELTA

logger = logging.getLogger(__name__)


@dataclass
class ShadowEvalResult:
    """Results from shadow evaluation of a patch."""
    patch_id: str
    status: str                          # "completed", "failed", "timeout"
    
    # Baseline metrics (before patch)
    avg_reward_before: Optional[float] = None
    error_rate_before: Optional[float] = None
    latency_p95_before: Optional[float] = None
    
    # Patched metrics (after patch)
    avg_reward_after: Optional[float] = None
    error_rate_after: Optional[float] = None
    latency_p95_after: Optional[float] = None
    
    # Deltas
    reward_delta: Optional[float] = None
    error_rate_delta: Optional[float] = None
    latency_p95_delta: Optional[float] = None
    
    # Metadata
    tests_run: int = 0
    baseline_samples: int = 0
    execution_time_ms: int = 0
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "patch_id": self.patch_id,
            "status": self.status,
            "avg_reward_before": self.avg_reward_before,
            "avg_reward_after": self.avg_reward_after,
            "reward_delta": self.reward_delta,
            "error_rate_before": self.error_rate_before,
            "error_rate_after": self.error_rate_after,
            "error_rate_delta": self.error_rate_delta,
            "latency_p95_before": self.latency_p95_before,
            "latency_p95_after": self.latency_p95_after,
            "latency_p95_delta": self.latency_p95_delta,
            "tests_run": self.tests_run,
            "baseline_samples": self.baseline_samples,
            "execution_time_ms": self.execution_time_ms,
            "error_message": self.error_message
        }
    
    @property
    def is_improvement(self) -> bool:
        """Check if patch shows improvement."""
        if self.reward_delta is None:
            return False
        return self.reward_delta >= DGM_MIN_REWARD_DELTA
    
    @property
    def is_significant(self) -> bool:
        """Check if results show significant change."""
        if self.reward_delta is None:
            return False
        return abs(self.reward_delta) >= DGM_MIN_REWARD_DELTA


class ShadowEvaluator:
    """
    Evaluates patches in shadow mode against Golden Set subset.
    """
    
    def __init__(self, repo_path: str = "."):
        self.repo_path = Path(repo_path).resolve()
        self.golden_path = self.repo_path / "storage" / "golden"
        self.temp_dirs = []
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
    
    def cleanup(self):
        """Clean up temporary directories."""
        for temp_dir in self.temp_dirs:
            try:
                if temp_dir.exists():
                    shutil.rmtree(temp_dir)
                    logger.debug(f"Cleaned up shadow eval temp dir: {temp_dir}")
            except Exception as e:
                logger.warning(f"Failed to clean up {temp_dir}: {e}")
        self.temp_dirs.clear()
    
    def _get_golden_subset(self, max_items: int = None) -> List[Dict[str, Any]]:
        """
        Get a subset of Golden Set items for evaluation.
        
        Args:
            max_items: Maximum items to return (uses DGM_CANARY_RUNS if None)
            
        Returns:
            List of golden set test items
        """
        if max_items is None:
            max_items = DGM_CANARY_RUNS
        
        if not self.golden_path.exists():
            logger.warning(f"Golden path not found: {self.golden_path}")
            return []
        
        # Get all golden set files
        pattern = str(self.golden_path / "*.json")
        files = sorted(glob(pattern))
        
        if not files:
            logger.warning(f"No golden set files found in: {self.golden_path}")
            return []
        
        # Load and return subset
        items = []
        for i, path in enumerate(files[:max_items]):
            try:
                with open(path, 'r') as f:
                    item = json.load(f)
                item['_file_path'] = path
                item['_file_name'] = os.path.basename(path)
                items.append(item)
            except Exception as e:
                logger.warning(f"Failed to load golden item {path}: {e}")
        
        logger.info(f"Loaded {len(items)} golden set items for shadow evaluation")
        return items
    
    def _create_shadow_environment(self, patch: MetaPatch) -> Path:
        """
        Create a shadow environment with the patch applied.
        
        Args:
            patch: Patch to apply in shadow environment
            
        Returns:
            Path to shadow environment
        """
        # Create temporary directory for shadow environment
        temp_dir = Path(tempfile.mkdtemp(prefix="dgm_shadow_"))
        self.temp_dirs.append(temp_dir)
        
        try:
            # Copy repository to shadow location
            shadow_repo = temp_dir / "shadow_repo"
            shutil.copytree(
                self.repo_path,
                shadow_repo,
                ignore=shutil.ignore_patterns(
                    '.git', '__pycache__', '*.pyc', 'node_modules',
                    'logs', 'runs', '.uvicorn.pid'
                )
            )
            
            # Apply patch in shadow environment
            patch_file = shadow_repo / ".shadow_patch.diff"
            with open(patch_file, 'w') as f:
                f.write(patch.diff)
            
            # Apply using git (if available) or manual application
            import subprocess
            try:
                result = subprocess.run(
                    ["git", "apply", str(patch_file)],
                    cwd=shadow_repo,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if result.returncode != 0:
                    raise Exception(f"Git apply failed: {result.stderr}")
            except (subprocess.TimeoutExpired, FileNotFoundError):
                logger.warning("Git not available, skipping patch application in shadow eval")
            
            # Clean up patch file
            if patch_file.exists():
                patch_file.unlink()
            
            logger.debug(f"Created shadow environment: {shadow_repo}")
            return shadow_repo
            
        except Exception as e:
            logger.error(f"Failed to create shadow environment: {e}")
            raise
    
    def _run_shadow_pipeline(self, golden_items: List[Dict], shadow_repo: Optional[Path] = None) -> Tuple[List[float], List[float], List[float]]:
        """
        Run golden set items through shadow pipeline.
        
        Args:
            golden_items: Golden set test items
            shadow_repo: Path to shadow repo (None for baseline)
            
        Returns:
            (rewards, error_rates, latencies) tuple
        """
        rewards = []
        error_rates = []
        latencies = []
        
        # Import required modules with shadow environment in path
        import sys
        original_path = sys.path.copy()
        
        try:
            if shadow_repo:
                # Add shadow repo to Python path
                sys.path.insert(0, str(shadow_repo))
            
            # Import the meta_run function
            from app.meta.runner import meta_run
            
            for item in golden_items:
                try:
                    start_time = time.time()
                    
                    # Extract test parameters
                    task_class = item.get("task_class", "code")
                    task = item.get("task", "")
                    assertions = item.get("assertions", [])
                    flags = item.get("flags", {})
                    seed = int(item.get("seed", 123))
                    
                    # Run meta evaluation (shadow - no output to user)
                    result = meta_run(
                        task_class=task_class,
                        task=task,
                        assertions=assertions,
                        session_id=None,  # No session = no user output
                        n=2,  # Reduced iterations for speed
                        memory_k=int(flags.get("memory_k", 0)),
                        rag_k=int(flags.get("rag_k", 0)),
                        operators=None,
                        framework_mask=["SEAL", "SAMPLING"] + (["WEB"] if flags.get("web") else []),
                        use_bandit=True,
                        test_cmd=None,
                        test_weight=0.0,
                        force_engine="ollama",
                        compare_with_groq=False,
                        judge_mode="off",
                        judge_include_rationale=False  # Skip rationale for speed
                    )
                    
                    # Extract metrics
                    total_reward = result.get("best_total_reward")
                    if isinstance(total_reward, (int, float)):
                        rewards.append(total_reward)
                    
                    # Error rate (if any variants failed)
                    variants = result.get("variants", [])
                    if variants:
                        errors = sum(1 for v in variants if v.get("error") is not None)
                        error_rate = errors / len(variants)
                        error_rates.append(error_rate)
                    else:
                        error_rates.append(0.0)
                    
                    # Latency (execution time)
                    latency_ms = int((time.time() - start_time) * 1000)
                    latencies.append(latency_ms)
                    
                except Exception as e:
                    logger.warning(f"Shadow pipeline failed for item {item.get('id', 'unknown')}: {e}")
                    # Record failure metrics
                    error_rates.append(1.0)  # 100% error rate
                    # Skip reward and latency for failed items
        
        finally:
            # Restore original Python path
            sys.path = original_path
        
        return rewards, error_rates, latencies
    
    def _calculate_metrics(self, rewards: List[float], error_rates: List[float], latencies: List[float]) -> Dict[str, Optional[float]]:
        """Calculate aggregate metrics from raw results."""
        result = {
            "avg_reward": None,
            "error_rate": None,
            "latency_p95": None
        }
        
        if rewards:
            result["avg_reward"] = statistics.mean(rewards)
        
        if error_rates:
            result["error_rate"] = statistics.mean(error_rates)
        
        if latencies:
            result["latency_p95"] = statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else max(latencies)
        
        return result


def shadow_eval(patch: MetaPatch, runs: int = None, timeout: int = None) -> ShadowEvalResult:
    """
    Perform shadow evaluation of a patch against Golden Set subset.
    
    Args:
        patch: MetaPatch to evaluate
        runs: Number of Golden Set items to test (uses DGM_CANARY_RUNS if None)
        timeout: Timeout in seconds (uses DGM_SHADOW_TIMEOUT if None)
        
    Returns:
        ShadowEvalResult with performance metrics
    """
    if runs is None:
        runs = DGM_CANARY_RUNS
    if timeout is None:
        timeout = DGM_SHADOW_TIMEOUT
    
    start_time = time.time()
    result = ShadowEvalResult(patch_id=patch.id, status="running")
    
    logger.info(f"Starting shadow evaluation for patch {patch.id} (area: {patch.area})")
    
    try:
        with ShadowEvaluator() as evaluator:
            # Get Golden Set subset
            golden_items = evaluator._get_golden_subset(runs)
            if not golden_items:
                result.status = "failed"
                result.error_message = "No Golden Set items available"
                return result
            
            result.tests_run = len(golden_items)
            
            # Measure baseline performance (multiple samples for stability)
            baseline_rewards = []
            baseline_errors = []
            baseline_latencies = []
            
            for sample in range(DGM_BASELINE_SAMPLES):
                logger.debug(f"Running baseline sample {sample + 1}/{DGM_BASELINE_SAMPLES}")
                rewards, errors, latencies = evaluator._run_shadow_pipeline(golden_items)
                baseline_rewards.extend(rewards)
                baseline_errors.extend(errors)
                baseline_latencies.extend(latencies)
            
            result.baseline_samples = DGM_BASELINE_SAMPLES
            
            # Calculate baseline metrics
            baseline_metrics = evaluator._calculate_metrics(baseline_rewards, baseline_errors, baseline_latencies)
            result.avg_reward_before = baseline_metrics["avg_reward"]
            result.error_rate_before = baseline_metrics["error_rate"]
            result.latency_p95_before = baseline_metrics["latency_p95"]
            
            # Create shadow environment with patch
            logger.debug(f"Applying patch {patch.id} in shadow environment")
            shadow_repo = evaluator._create_shadow_environment(patch)
            
            # Measure patched performance
            logger.debug("Running shadow evaluation with patch applied")
            patched_rewards, patched_errors, patched_latencies = evaluator._run_shadow_pipeline(golden_items, shadow_repo)
            
            # Calculate patched metrics
            patched_metrics = evaluator._calculate_metrics(patched_rewards, patched_errors, patched_latencies)
            result.avg_reward_after = patched_metrics["avg_reward"]
            result.error_rate_after = patched_metrics["error_rate"] 
            result.latency_p95_after = patched_metrics["latency_p95"]
            
            # Calculate deltas
            if result.avg_reward_before is not None and result.avg_reward_after is not None:
                result.reward_delta = result.avg_reward_after - result.avg_reward_before
            
            if result.error_rate_before is not None and result.error_rate_after is not None:
                result.error_rate_delta = result.error_rate_after - result.error_rate_before
            
            if result.latency_p95_before is not None and result.latency_p95_after is not None:
                result.latency_p95_delta = result.latency_p95_after - result.latency_p95_before
            
            result.status = "completed"
            logger.info(f"Shadow eval complete for {patch.id}: reward_delta={result.reward_delta:.3f}")
    
    except Exception as e:
        result.status = "failed"
        result.error_message = str(e)
        logger.error(f"Shadow evaluation failed for {patch.id}: {e}")
    
    result.execution_time_ms = int((time.time() - start_time) * 1000)
    
    # Timeout check
    if result.execution_time_ms > timeout * 1000:
        result.status = "timeout"
        result.error_message = f"Shadow evaluation timed out after {timeout}s"
    
    return result


def batch_shadow_eval(patches: List[MetaPatch], runs: int = None) -> List[ShadowEvalResult]:
    """
    Perform shadow evaluation on multiple patches sequentially.
    
    Args:
        patches: List of patches to evaluate
        runs: Number of Golden Set items per patch
        
    Returns:
        List of ShadowEvalResult objects
    """
    logger.info(f"Starting batch shadow evaluation of {len(patches)} patches")
    
    results = []
    for i, patch in enumerate(patches):
        logger.info(f"Shadow evaluating patch {i+1}/{len(patches)}: {patch.id}")
        result = shadow_eval(patch, runs)
        results.append(result)
        
        # Log progress
        status_symbol = "✓" if result.status == "completed" else "✗"
        logger.info(f"Patch {patch.id}: {status_symbol} {result.status}")
        
        if result.reward_delta is not None:
            logger.info(f"  Reward delta: {result.reward_delta:+.3f}")
    
    # Summary
    completed = sum(1 for r in results if r.status == "completed")
    improvements = sum(1 for r in results if r.is_improvement)
    
    logger.info(f"Batch shadow eval complete: {completed}/{len(patches)} completed, {improvements} show improvement")
    
    return results


# Shadow evaluation registry for storing results
_shadow_eval_registry: Dict[str, ShadowEvalResult] = {}


def register_shadow_eval(result: ShadowEvalResult):
    """Register shadow evaluation result."""
    _shadow_eval_registry[result.patch_id] = result
    logger.debug(f"Registered shadow eval result for {result.patch_id}")


def get_shadow_eval(patch_id: str) -> Optional[ShadowEvalResult]:
    """Get shadow evaluation result by patch ID."""
    return _shadow_eval_registry.get(patch_id)


def get_all_shadow_evals() -> Dict[str, ShadowEvalResult]:
    """Get all shadow evaluation results."""
    return _shadow_eval_registry.copy()


def clear_shadow_eval_registry():
    """Clear shadow evaluation registry."""
    global _shadow_eval_registry
    _shadow_eval_registry.clear()
    logger.info("Shadow evaluation registry cleared")


def get_registry_stats() -> Dict[str, Any]:
    """Get statistics about shadow evaluation registry."""
    results = list(_shadow_eval_registry.values())
    
    if not results:
        return {"total": 0}
    
    completed = [r for r in results if r.status == "completed"]
    improvements = [r for r in completed if r.is_improvement]
    
    avg_reward_delta = None
    if completed:
        reward_deltas = [r.reward_delta for r in completed if r.reward_delta is not None]
        if reward_deltas:
            avg_reward_delta = statistics.mean(reward_deltas)
    
    return {
        "total": len(results),
        "completed": len(completed),
        "improvements": len(improvements),
        "improvement_rate": len(improvements) / len(completed) if completed else 0.0,
        "avg_reward_delta": avg_reward_delta,
        "avg_execution_time_ms": statistics.mean([r.execution_time_ms for r in results]) if results else 0
    }