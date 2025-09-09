"""
Simple job overlap prevention for Ollama-intensive operations.
Prevents multiple evolution runs, Golden Set, and code loops from running simultaneously.
"""
import time
from typing import Optional, Set
import threading

_active_jobs: Set[str] = set()
_lock = threading.Lock()

class JobConflictError(Exception):
    """Raised when trying to start a job while a conflicting job is running."""
    pass

def start_job(job_type: str, allow_concurrent: bool = False) -> Optional[str]:
    """
    Start a new job. Returns job_id if successful, raises JobConflictError if blocked.
    
    Args:
        job_type: Type of job ("evolution", "golden", "code_loop", etc.)
        allow_concurrent: If True, allows multiple jobs of same type
        
    Returns:
        job_id: Unique identifier for this job
        
    Raises:
        JobConflictError: If a conflicting job is already running
    """
    job_id = f"{job_type}_{int(time.time() * 1000)}"
    
    with _lock:
        # Check for conflicts
        if not allow_concurrent:
            # Evolution, Golden Set, and Code Loop are mutually exclusive
            exclusive_jobs = {"evolution", "golden", "code_loop"}
            
            if job_type in exclusive_jobs:
                # Check if any exclusive job is running
                for active_job in _active_jobs:
                    active_type = active_job.split("_")[0]
                    if active_type in exclusive_jobs:
                        raise JobConflictError(f"Cannot start {job_type}: {active_type} job already running ({active_job})")
        
        _active_jobs.add(job_id)
        return job_id

def finish_job(job_id: str):
    """Mark a job as finished."""
    with _lock:
        _active_jobs.discard(job_id)

def get_active_jobs() -> Set[str]:
    """Get list of currently active jobs."""
    with _lock:
        return _active_jobs.copy()

def is_job_running(job_type: str) -> bool:
    """Check if any job of given type is currently running."""
    with _lock:
        return any(job.startswith(f"{job_type}_") for job in _active_jobs)

class JobContext:
    """Context manager for job lifecycle."""
    
    def __init__(self, job_type: str, allow_concurrent: bool = False):
        self.job_type = job_type
        self.allow_concurrent = allow_concurrent
        self.job_id = None
        
    def __enter__(self):
        self.job_id = start_job(self.job_type, self.allow_concurrent)
        return self.job_id
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.job_id:
            finish_job(self.job_id)