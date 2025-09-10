"""
DGM Canary State - Manages active canary deployments

This module tracks active canary patches, their metrics, and handles
traffic routing decisions for live evaluation.
"""

import time
import threading
from typing import Dict, Optional, Any, List
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class CanaryMetrics:
    """Metrics tracked for a canary deployment."""
    total_requests: int = 0
    canary_requests: int = 0
    baseline_errors: int = 0
    canary_errors: int = 0
    baseline_latency_sum: float = 0.0
    canary_latency_sum: float = 0.0
    baseline_reward_sum: float = 0.0
    canary_reward_sum: float = 0.0
    violations: List[str] = field(default_factory=list)
    
    @property
    def canary_error_rate(self) -> float:
        """Calculate canary error rate."""
        if self.canary_requests == 0:
            return 0.0
        return self.canary_errors / self.canary_requests
    
    @property
    def baseline_error_rate(self) -> float:
        """Calculate baseline error rate."""
        baseline_requests = self.total_requests - self.canary_requests
        if baseline_requests == 0:
            return 0.0
        return self.baseline_errors / baseline_requests
    
    @property
    def canary_avg_latency(self) -> float:
        """Calculate average canary latency."""
        if self.canary_requests == 0:
            return 0.0
        return self.canary_latency_sum / self.canary_requests
    
    @property
    def baseline_avg_latency(self) -> float:
        """Calculate average baseline latency."""
        baseline_requests = self.total_requests - self.canary_requests
        if baseline_requests == 0:
            return 0.0
        return self.baseline_latency_sum / baseline_requests
    
    @property
    def canary_avg_reward(self) -> float:
        """Calculate average canary reward."""
        if self.canary_requests == 0:
            return 0.0
        return self.canary_reward_sum / self.canary_requests
    
    @property
    def baseline_avg_reward(self) -> float:
        """Calculate average baseline reward."""
        baseline_requests = self.total_requests - self.canary_requests
        if baseline_requests == 0:
            return 0.0
        return self.baseline_reward_sum / baseline_requests
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "total_requests": self.total_requests,
            "canary_requests": self.canary_requests,
            "canary_error_rate": self.canary_error_rate,
            "baseline_error_rate": self.baseline_error_rate,
            "canary_avg_latency": self.canary_avg_latency,
            "baseline_avg_latency": self.baseline_avg_latency,
            "canary_avg_reward": self.canary_avg_reward,
            "baseline_avg_reward": self.baseline_avg_reward,
            "reward_delta": self.canary_avg_reward - self.baseline_avg_reward,
            "violations": self.violations
        }


@dataclass
class CanaryDeployment:
    """Represents an active canary deployment."""
    patch_id: str
    traffic_share: float
    start_time: float
    target_runs: int
    metrics: CanaryMetrics = field(default_factory=CanaryMetrics)
    status: str = "active"  # active, completed, rolled_back
    rollback_reason: Optional[str] = None
    
    @property
    def elapsed_time(self) -> float:
        """Time since canary started."""
        return time.time() - self.start_time
    
    @property
    def progress(self) -> float:
        """Progress towards target runs."""
        return min(1.0, self.metrics.canary_requests / self.target_runs)
    
    def should_use_canary(self) -> bool:
        """Determine if next request should use canary."""
        import random
        if self.status != "active":
            return False
        if self.metrics.canary_requests >= self.target_runs:
            return False
        return random.random() < self.traffic_share
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "patch_id": self.patch_id,
            "traffic_share": self.traffic_share,
            "start_time": self.start_time,
            "elapsed_time": self.elapsed_time,
            "target_runs": self.target_runs,
            "progress": self.progress,
            "status": self.status,
            "rollback_reason": self.rollback_reason,
            "metrics": self.metrics.to_dict()
        }


class CanaryManager:
    """Manages active canary deployments."""
    
    def __init__(self):
        self._canaries: Dict[str, CanaryDeployment] = {}
        self._lock = threading.Lock()
    
    def start_canary(self, patch_id: str, traffic_share: float = 0.05, 
                     target_runs: int = 25) -> CanaryDeployment:
        """
        Start a new canary deployment.
        
        Args:
            patch_id: ID of patch to canary
            traffic_share: Fraction of traffic to route to canary
            target_runs: Number of canary runs to complete
            
        Returns:
            CanaryDeployment instance
        """
        with self._lock:
            # Stop any existing canary for this patch
            if patch_id in self._canaries:
                self._canaries[patch_id].status = "superseded"
            
            canary = CanaryDeployment(
                patch_id=patch_id,
                traffic_share=traffic_share,
                start_time=time.time(),
                target_runs=target_runs
            )
            
            self._canaries[patch_id] = canary
            logger.info(f"Started canary for patch {patch_id}: {traffic_share*100}% traffic, {target_runs} runs")
            
            return canary
    
    def get_canary(self, patch_id: str) -> Optional[CanaryDeployment]:
        """Get canary deployment by patch ID."""
        with self._lock:
            return self._canaries.get(patch_id)
    
    def get_active_canary(self) -> Optional[CanaryDeployment]:
        """Get the currently active canary (if any)."""
        with self._lock:
            for canary in self._canaries.values():
                if canary.status == "active":
                    return canary
            return None
    
    def should_use_canary(self) -> tuple[bool, Optional[str]]:
        """
        Check if current request should use canary.
        
        Returns:
            (should_use, patch_id) tuple
        """
        canary = self.get_active_canary()
        if canary and canary.should_use_canary():
            return True, canary.patch_id
        return False, None
    
    def record_request(self, patch_id: Optional[str], error: bool, 
                      latency_ms: float, reward: float):
        """
        Record metrics for a request.
        
        Args:
            patch_id: Patch ID if canary was used, None for baseline
            error: Whether request had an error
            latency_ms: Request latency in milliseconds
            reward: Request reward/score
        """
        with self._lock:
            # Find active canary
            canary = self.get_active_canary()
            if not canary:
                return
            
            metrics = canary.metrics
            metrics.total_requests += 1
            
            if patch_id == canary.patch_id:
                # Canary request
                metrics.canary_requests += 1
                if error:
                    metrics.canary_errors += 1
                metrics.canary_latency_sum += latency_ms
                metrics.canary_reward_sum += reward
            else:
                # Baseline request
                if error:
                    metrics.baseline_errors += 1
                metrics.baseline_latency_sum += latency_ms
                metrics.baseline_reward_sum += reward
            
            # Check if canary is complete
            if metrics.canary_requests >= canary.target_runs:
                canary.status = "completed"
                logger.info(f"Canary {canary.patch_id} completed: {metrics.canary_requests} runs")
    
    def check_guards(self, patch_id: str, guard_thresholds: Dict[str, float]) -> Optional[str]:
        """
        Check if canary violates guard thresholds.
        
        Args:
            patch_id: Patch ID to check
            guard_thresholds: Threshold values for guards
            
        Returns:
            Violation reason if guards tripped, None otherwise
        """
        with self._lock:
            canary = self._canaries.get(patch_id)
            if not canary or canary.status != "active":
                return None
            
            metrics = canary.metrics
            
            # Need minimum samples before checking
            if metrics.canary_requests < 5:
                return None
            
            # Check error rate
            max_error_rate = guard_thresholds.get("error_rate_max", 0.15)
            if metrics.canary_error_rate > max_error_rate:
                violation = f"Error rate {metrics.canary_error_rate:.2%} > {max_error_rate:.2%}"
                metrics.violations.append(violation)
                return violation
            
            # Check latency regression
            max_latency_delta = guard_thresholds.get("latency_p95_regression", 500)
            latency_delta = metrics.canary_avg_latency - metrics.baseline_avg_latency
            if latency_delta > max_latency_delta:
                violation = f"Latency regression {latency_delta:.0f}ms > {max_latency_delta}ms"
                metrics.violations.append(violation)
                return violation
            
            # Check reward regression
            min_reward_delta = guard_thresholds.get("reward_delta_min", -0.05)
            reward_delta = metrics.canary_avg_reward - metrics.baseline_avg_reward
            if reward_delta < min_reward_delta:
                violation = f"Reward delta {reward_delta:.3f} < {min_reward_delta}"
                metrics.violations.append(violation)
                return violation
            
            return None
    
    def rollback_canary(self, patch_id: str, reason: str):
        """
        Mark canary as rolled back.
        
        Args:
            patch_id: Patch ID to rollback
            reason: Reason for rollback
        """
        with self._lock:
            canary = self._canaries.get(patch_id)
            if canary:
                canary.status = "rolled_back"
                canary.rollback_reason = reason
                logger.warning(f"Rolled back canary {patch_id}: {reason}")
    
    def get_all_canaries(self) -> List[CanaryDeployment]:
        """Get all canary deployments."""
        with self._lock:
            return list(self._canaries.values())
    
    def cleanup_old_canaries(self, max_age_hours: int = 24):
        """Remove old canary records."""
        with self._lock:
            cutoff = time.time() - (max_age_hours * 3600)
            to_remove = []
            
            for patch_id, canary in self._canaries.items():
                if canary.start_time < cutoff and canary.status != "active":
                    to_remove.append(patch_id)
            
            for patch_id in to_remove:
                del self._canaries[patch_id]
            
            if to_remove:
                logger.info(f"Cleaned up {len(to_remove)} old canary records")


# Global canary manager instance
_canary_manager: Optional[CanaryManager] = None


def get_canary_manager() -> CanaryManager:
    """Get the global canary manager instance."""
    global _canary_manager
    if _canary_manager is None:
        _canary_manager = CanaryManager()
    return _canary_manager