"""
DGM Resource Monitoring - M1 Stability Guards

Implements resource monitoring and fail-fast mechanisms to ensure
system stability on Apple Silicon by checking CPU load, memory usage,
and other resource constraints before starting DGM operations.
"""

import psutil
import logging
import time
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
from app.config import (
    DGM_CPU_THRESHOLD, 
    DGM_MEMORY_THRESHOLD_MB, 
    DGM_RESOURCE_CHECK_ENABLED,
    DGM_OPERATION_TIMEOUT
)

logger = logging.getLogger(__name__)


@dataclass
class ResourceStatus:
    """System resource status snapshot."""
    cpu_percent: float
    memory_mb: float
    memory_percent: float
    available_memory_mb: float
    disk_usage_percent: float
    load_avg_1m: Optional[float]
    timestamp: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "cpu_percent": self.cpu_percent,
            "memory_mb": self.memory_mb,
            "memory_percent": self.memory_percent,
            "available_memory_mb": self.available_memory_mb,
            "disk_usage_percent": self.disk_usage_percent,
            "load_avg_1m": self.load_avg_1m,
            "timestamp": self.timestamp
        }


@dataclass
class ResourceGuard:
    """Resource constraint violation."""
    resource: str
    threshold: float
    current: float
    violated: bool
    reason: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "resource": self.resource,
            "threshold": self.threshold,
            "current": self.current,
            "violated": self.violated,
            "reason": self.reason
        }


def get_resource_status() -> ResourceStatus:
    """Get current system resource usage."""
    try:
        # CPU usage (1-second average)
        cpu_percent = psutil.cpu_percent(interval=1)
        
        # Memory usage
        memory = psutil.virtual_memory()
        memory_mb = memory.used / (1024 * 1024)
        memory_percent = memory.percent
        available_memory_mb = memory.available / (1024 * 1024)
        
        # Disk usage for current directory
        disk_usage = psutil.disk_usage('.')
        disk_usage_percent = (disk_usage.used / disk_usage.total) * 100
        
        # Load average (Unix-like systems)
        load_avg_1m = None
        try:
            if hasattr(psutil, 'getloadavg'):
                load_avg_1m = psutil.getloadavg()[0]
        except (AttributeError, OSError):
            # Not available on all platforms
            pass
        
        return ResourceStatus(
            cpu_percent=cpu_percent,
            memory_mb=memory_mb,
            memory_percent=memory_percent,
            available_memory_mb=available_memory_mb,
            disk_usage_percent=disk_usage_percent,
            load_avg_1m=load_avg_1m,
            timestamp=time.time()
        )
        
    except Exception as e:
        logger.warning(f"Failed to get resource status: {e}")
        # Return safe defaults that won't block operations
        return ResourceStatus(
            cpu_percent=0.0,
            memory_mb=0.0,
            memory_percent=0.0,
            available_memory_mb=4096.0,  # Assume 4GB available
            disk_usage_percent=0.0,
            load_avg_1m=None,
            timestamp=time.time()
        )


def check_resource_guards() -> Tuple[bool, list[ResourceGuard], ResourceStatus]:
    """
    Check if system resources are within acceptable limits for DGM operations.
    
    Returns:
        (can_proceed: bool, violations: List[ResourceGuard], status: ResourceStatus)
    """
    if not DGM_RESOURCE_CHECK_ENABLED:
        # Resource checking disabled, always allow
        status = get_resource_status()
        return True, [], status
    
    status = get_resource_status()
    violations = []
    
    # Check CPU usage
    if status.cpu_percent > (DGM_CPU_THRESHOLD * 100):
        violations.append(ResourceGuard(
            resource="cpu",
            threshold=DGM_CPU_THRESHOLD * 100,
            current=status.cpu_percent,
            violated=True,
            reason=f"CPU usage {status.cpu_percent:.1f}% exceeds {DGM_CPU_THRESHOLD * 100:.1f}% threshold"
        ))
    
    # Check memory usage
    if status.memory_mb > DGM_MEMORY_THRESHOLD_MB:
        violations.append(ResourceGuard(
            resource="memory",
            threshold=DGM_MEMORY_THRESHOLD_MB,
            current=status.memory_mb,
            violated=True,
            reason=f"Memory usage {status.memory_mb:.0f}MB exceeds {DGM_MEMORY_THRESHOLD_MB}MB threshold"
        ))
    
    # Check available memory (ensure we have at least 512MB free)
    min_available_mb = 512
    if status.available_memory_mb < min_available_mb:
        violations.append(ResourceGuard(
            resource="available_memory",
            threshold=min_available_mb,
            current=status.available_memory_mb,
            violated=True,
            reason=f"Available memory {status.available_memory_mb:.0f}MB below {min_available_mb}MB minimum"
        ))
    
    # Check disk usage (warn if > 90%)
    if status.disk_usage_percent > 90.0:
        violations.append(ResourceGuard(
            resource="disk",
            threshold=90.0,
            current=status.disk_usage_percent,
            violated=True,
            reason=f"Disk usage {status.disk_usage_percent:.1f}% exceeds 90% threshold"
        ))
    
    # Check load average (if available) - warn if > number of CPUs
    if status.load_avg_1m is not None:
        cpu_count = psutil.cpu_count()
        if cpu_count and status.load_avg_1m > cpu_count * 1.5:
            violations.append(ResourceGuard(
                resource="load_avg",
                threshold=cpu_count * 1.5,
                current=status.load_avg_1m,
                violated=True,
                reason=f"Load average {status.load_avg_1m:.2f} exceeds {cpu_count * 1.5:.1f} threshold"
            ))
    
    can_proceed = len(violations) == 0
    
    if violations:
        logger.warning(f"Resource guard violations: {len(violations)} constraints exceeded")
        for violation in violations:
            logger.warning(f"  - {violation.reason}")
    else:
        logger.debug(f"Resource guards passed: CPU {status.cpu_percent:.1f}%, Memory {status.memory_mb:.0f}MB")
    
    return can_proceed, violations, status


def monitor_operation_timeout(start_time: float, operation_name: str = "DGM operation") -> bool:
    """
    Check if operation has exceeded timeout limit.
    
    Args:
        start_time: Operation start timestamp
        operation_name: Name of operation for logging
        
    Returns:
        True if operation should continue, False if timeout exceeded
    """
    elapsed = time.time() - start_time
    
    if elapsed > DGM_OPERATION_TIMEOUT:
        logger.error(f"{operation_name} timeout: {elapsed:.1f}s exceeds {DGM_OPERATION_TIMEOUT}s limit")
        return False
    
    if elapsed > (DGM_OPERATION_TIMEOUT * 0.8):
        logger.warning(f"{operation_name} approaching timeout: {elapsed:.1f}s of {DGM_OPERATION_TIMEOUT}s")
    
    return True


def get_system_info() -> Dict[str, Any]:
    """Get general system information for diagnostics."""
    try:
        return {
            "platform": psutil.WINDOWS if hasattr(psutil, 'WINDOWS') else 'unix',
            "cpu_count": psutil.cpu_count(),
            "cpu_count_logical": psutil.cpu_count(logical=True),
            "memory_total_mb": psutil.virtual_memory().total / (1024 * 1024),
            "disk_total_gb": psutil.disk_usage('.').total / (1024 * 1024 * 1024),
            "boot_time": psutil.boot_time(),
            "python_memory_mb": psutil.Process().memory_info().rss / (1024 * 1024)
        }
    except Exception as e:
        logger.warning(f"Failed to get system info: {e}")
        return {"error": str(e)}


class ResourceMonitor:
    """Context manager for monitoring resources during DGM operations."""
    
    def __init__(self, operation_name: str = "DGM operation"):
        self.operation_name = operation_name
        self.start_time = None
        self.start_status = None
        
    def __enter__(self):
        self.start_time = time.time()
        can_proceed, violations, self.start_status = check_resource_guards()
        
        if not can_proceed:
            violation_reasons = [v.reason for v in violations]
            raise ResourceError(f"Resource guards failed: {'; '.join(violation_reasons)}")
        
        logger.info(f"Starting {self.operation_name} - Resource check passed")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time:
            elapsed = time.time() - self.start_time
            logger.info(f"Completed {self.operation_name} in {elapsed:.1f}s")
        
    def check_timeout(self) -> bool:
        """Check if operation should continue."""
        if not self.start_time:
            return True
        return monitor_operation_timeout(self.start_time, self.operation_name)


class ResourceError(Exception):
    """Exception raised when resource constraints are violated."""
    pass


def create_resource_guard_sse_event(violations: list[ResourceGuard], status: ResourceStatus) -> Dict[str, Any]:
    """Create SSE event for resource guard violations."""
    return {
        "event": "dgm.rollback",
        "data": {
            "reason": "resource_guard",
            "violations": [v.to_dict() for v in violations],
            "resource_status": status.to_dict(),
            "timestamp": time.time()
        }
    }


# Global resource monitoring state
_last_check_time = 0
_last_check_result = None
_check_cache_duration = 5.0  # Cache results for 5 seconds


def get_cached_resource_status() -> Tuple[bool, list[ResourceGuard], ResourceStatus]:
    """Get cached resource status to avoid excessive system calls."""
    global _last_check_time, _last_check_result
    
    current_time = time.time()
    if (_last_check_result is None or 
        current_time - _last_check_time > _check_cache_duration):
        
        _last_check_result = check_resource_guards()
        _last_check_time = current_time
    
    return _last_check_result