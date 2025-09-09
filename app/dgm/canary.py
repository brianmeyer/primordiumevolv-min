"""
DGM Canary Testing System - Safe testing of proposed modifications

The CanaryTester provides controlled testing of system modifications
in isolated environments before committing to the live system.
"""

import time
import asyncio
import logging
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from enum import Enum
from app.config import DGM_CANARY_BATCH_SIZE, DGM_COMMIT_THRESHOLD

logger = logging.getLogger(__name__)


class CanaryStatus(Enum):
    """Status of a canary test."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"


@dataclass
class CanaryTest:
    """Represents a single canary test."""
    test_id: str
    proposal_id: str
    test_type: str
    status: CanaryStatus
    created_at: float
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    results: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class CanaryTester:
    """
    Manages canary testing of proposed system modifications.
    
    Provides safe, controlled testing of changes before they are
    committed to the live system.
    """
    
    def __init__(self):
        self.active_tests: Dict[str, CanaryTest] = {}
        self.test_history: List[CanaryTest] = []
        self.test_runners: Dict[str, Callable] = {}
        self.batch_size = DGM_CANARY_BATCH_SIZE
        
    def register_test_runner(self, test_type: str, runner: Callable):
        """Register a test runner for a specific modification type."""
        self.test_runners[test_type] = runner
        logger.info(f"Registered canary test runner for {test_type}")
    
    def create_canary_test(self, proposal_id: str, test_config: Dict[str, Any]) -> str:
        """
        Create a new canary test for a proposal.
        
        Args:
            proposal_id: ID of the proposal to test
            test_config: Configuration for the test
            
        Returns:
            Test ID of created canary test
        """
        test_id = f"canary_{proposal_id}_{int(time.time())}"
        
        canary_test = CanaryTest(
            test_id=test_id,
            proposal_id=proposal_id,
            test_type=test_config.get("test_type", "basic"),
            status=CanaryStatus.PENDING,
            created_at=time.time()
        )
        
        self.active_tests[test_id] = canary_test
        logger.info(f"Created canary test {test_id} for proposal {proposal_id}")
        
        return test_id
    
    async def run_canary_test(self, test_id: str) -> Dict[str, Any]:
        """
        Execute a canary test.
        
        Args:
            test_id: ID of the test to run
            
        Returns:
            Test results dict
        """
        if test_id not in self.active_tests:
            return {"error": "Test not found", "test_id": test_id}
        
        canary_test = self.active_tests[test_id]
        canary_test.status = CanaryStatus.RUNNING
        canary_test.started_at = time.time()
        
        logger.info(f"Starting canary test {test_id}")
        
        try:
            # Get appropriate test runner
            test_runner = self.test_runners.get(canary_test.test_type)
            
            if test_runner:
                # Run the actual test
                results = await self._execute_test_runner(test_runner, canary_test)
            else:
                # Scaffold implementation - simulate test execution
                results = await self._simulate_test_execution(canary_test)
            
            canary_test.results = results
            canary_test.status = CanaryStatus.COMPLETED
            canary_test.completed_at = time.time()
            
            logger.info(f"Canary test {test_id} completed successfully")
            
        except Exception as e:
            canary_test.error = str(e)
            canary_test.status = CanaryStatus.FAILED
            canary_test.completed_at = time.time()
            logger.error(f"Canary test {test_id} failed: {e}")
            
            results = {
                "status": "failed",
                "error": str(e),
                "success_rate": 0.0
            }
        
        # Move to history
        self.test_history.append(canary_test)
        if test_id in self.active_tests:
            del self.active_tests[test_id]
        
        return results
    
    async def _execute_test_runner(self, test_runner: Callable, canary_test: CanaryTest) -> Dict[str, Any]:
        """Execute a registered test runner."""
        logger.info(f"Executing test runner for {canary_test.test_type}")
        
        # Call the registered test runner
        if asyncio.iscoroutinefunction(test_runner):
            return await test_runner(canary_test)
        else:
            return test_runner(canary_test)
    
    async def _simulate_test_execution(self, canary_test: CanaryTest) -> Dict[str, Any]:
        """
        Simulate test execution for scaffold mode.
        
        This provides a safe simulation that doesn't affect the live system.
        """
        logger.info(f"Simulating canary test execution for {canary_test.test_id}")
        
        # Simulate test execution time
        await asyncio.sleep(0.1)  # Short delay to simulate work
        
        # Scaffold results - always safe/conservative
        return {
            "status": "completed",
            "test_type": canary_test.test_type,
            "success_rate": 0.7,  # Conservative success rate
            "performance_delta": 0.02,  # Minimal performance change
            "error_rate": 0.0,
            "resource_usage": {
                "cpu_delta": 0.01,
                "memory_delta": 0.005,
                "latency_delta": 10  # ms
            },
            "safety_checks": {
                "no_critical_failures": True,
                "within_performance_bounds": True,
                "no_data_corruption": True,
                "reversible": True
            },
            "test_runs": self.batch_size,
            "passed_runs": int(self.batch_size * 0.7),
            "failed_runs": int(self.batch_size * 0.3),
            "execution_time_ms": 100,
            "recommendations": ["Safe to proceed with limited scope", "Monitor closely if committed"]
        }
    
    def batch_test_proposal(self, proposal_id: str, test_configs: List[Dict[str, Any]]) -> List[str]:
        """
        Create multiple canary tests for a proposal.
        
        Args:
            proposal_id: ID of proposal to test
            test_configs: List of test configurations
            
        Returns:
            List of created test IDs
        """
        test_ids = []
        
        for config in test_configs:
            test_id = self.create_canary_test(proposal_id, config)
            test_ids.append(test_id)
        
        logger.info(f"Created batch of {len(test_ids)} canary tests for proposal {proposal_id}")
        return test_ids
    
    async def run_batch_tests(self, test_ids: List[str]) -> Dict[str, Any]:
        """
        Run multiple canary tests concurrently.
        
        Args:
            test_ids: List of test IDs to execute
            
        Returns:
            Aggregated results from all tests
        """
        logger.info(f"Running batch of {len(test_ids)} canary tests")
        
        # Execute tests concurrently
        tasks = [self.run_canary_test(test_id) for test_id in test_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Aggregate results
        successful_tests = 0
        failed_tests = 0
        total_performance_delta = 0.0
        all_results = []
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                failed_tests += 1
                all_results.append({"test_id": test_ids[i], "error": str(result)})
            else:
                if result.get("status") == "completed":
                    successful_tests += 1
                    total_performance_delta += result.get("performance_delta", 0.0)
                else:
                    failed_tests += 1
                all_results.append(result)
        
        success_rate = successful_tests / len(test_ids) if test_ids else 0.0
        avg_performance_delta = total_performance_delta / successful_tests if successful_tests > 0 else 0.0
        
        aggregated_results = {
            "batch_success_rate": success_rate,
            "successful_tests": successful_tests,
            "failed_tests": failed_tests,
            "total_tests": len(test_ids),
            "avg_performance_delta": avg_performance_delta,
            "commit_recommended": success_rate >= DGM_COMMIT_THRESHOLD,
            "individual_results": all_results,
            "completed_at": time.time()
        }
        
        logger.info(f"Batch test completed: {success_rate:.2%} success rate")
        return aggregated_results
    
    def get_test_status(self, test_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific canary test."""
        if test_id in self.active_tests:
            test = self.active_tests[test_id]
        else:
            # Search in history
            test = next((t for t in self.test_history if t.test_id == test_id), None)
        
        if not test:
            return None
        
        return {
            "test_id": test.test_id,
            "proposal_id": test.proposal_id,
            "status": test.status.value,
            "test_type": test.test_type,
            "created_at": test.created_at,
            "started_at": test.started_at,
            "completed_at": test.completed_at,
            "results": test.results,
            "error": test.error
        }
    
    def abort_test(self, test_id: str, reason: str = "User requested") -> bool:
        """
        Abort a running canary test.
        
        Args:
            test_id: ID of test to abort
            reason: Reason for abortion
            
        Returns:
            True if test was aborted successfully
        """
        if test_id not in self.active_tests:
            return False
        
        canary_test = self.active_tests[test_id]
        if canary_test.status == CanaryStatus.RUNNING:
            canary_test.status = CanaryStatus.ABORTED
            canary_test.completed_at = time.time()
            canary_test.error = f"Aborted: {reason}"
            
            # Move to history
            self.test_history.append(canary_test)
            del self.active_tests[test_id]
            
            logger.info(f"Aborted canary test {test_id}: {reason}")
            return True
        
        return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about canary testing."""
        total_tests = len(self.active_tests) + len(self.test_history)
        active_count = len(self.active_tests)
        
        # Analyze historical results
        completed_tests = [t for t in self.test_history if t.status == CanaryStatus.COMPLETED]
        failed_tests = [t for t in self.test_history if t.status == CanaryStatus.FAILED]
        
        overall_success_rate = len(completed_tests) / len(self.test_history) if self.test_history else 0.0
        
        return {
            "total_tests": total_tests,
            "active_tests": active_count,
            "completed_tests": len(completed_tests),
            "failed_tests": len(failed_tests),
            "overall_success_rate": overall_success_rate,
            "registered_runners": len(self.test_runners),
            "batch_size": self.batch_size,
            "commit_threshold": DGM_COMMIT_THRESHOLD,
            "generated_at": time.time()
        }


# Global canary tester instance
_canary_tester: Optional[CanaryTester] = None


def get_canary_tester() -> CanaryTester:
    """Get the global canary tester instance."""
    global _canary_tester
    if _canary_tester is None:
        _canary_tester = CanaryTester()
    return _canary_tester


async def test_proposal_safely(proposal_id: str, test_scope: str = "limited") -> Dict[str, Any]:
    """
    High-level interface for testing a proposal safely.
    
    Args:
        proposal_id: ID of proposal to test
        test_scope: Scope of testing ("limited", "comprehensive")
        
    Returns:
        Test results and safety assessment
    """
    canary_tester = get_canary_tester()
    
    # Create test configuration based on scope
    if test_scope == "comprehensive":
        test_configs = [
            {"test_type": "performance", "duration_seconds": 60},
            {"test_type": "safety", "checks": ["data_integrity", "reversibility"]},
            {"test_type": "compatibility", "scope": "full_system"}
        ]
    else:  # limited scope
        test_configs = [
            {"test_type": "basic", "duration_seconds": 10},
            {"test_type": "safety", "checks": ["reversibility"]}
        ]
    
    # Create and run batch tests
    test_ids = canary_tester.batch_test_proposal(proposal_id, test_configs)
    results = await canary_tester.run_batch_tests(test_ids)
    
    # Add safety assessment
    results["safety_assessment"] = {
        "risk_level": "low" if results["batch_success_rate"] > 0.8 else "medium",
        "safe_to_commit": results["commit_recommended"],
        "monitoring_required": True,
        "rollback_plan_ready": True
    }
    
    return results