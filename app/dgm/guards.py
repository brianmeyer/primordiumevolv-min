"""
DGM Guards - Safety checks and violation detection for shadow evaluation results

This module implements guard checks to identify patches that violate safety
thresholds for error rates, latency regressions, and reward degradations.
"""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from app.dgm.eval import ShadowEvalResult
from app.config import DGM_FAIL_GUARDS

logger = logging.getLogger(__name__)


@dataclass
class GuardViolation:
    """Represents a guard violation."""
    guard_name: str          # Name of violated guard
    threshold: float         # Threshold that was exceeded
    actual_value: float      # Actual measured value
    severity: str           # "critical", "warning", "info"
    description: str        # Human-readable description


@dataclass 
class GuardResult:
    """Results from guard evaluation."""
    patch_id: str
    passed: bool                           # Overall pass/fail
    violations: List[GuardViolation]       # List of violations
    metrics_available: bool                # Whether all required metrics were available
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "patch_id": self.patch_id,
            "passed": self.passed,
            "violations": [
                {
                    "guard_name": v.guard_name,
                    "threshold": v.threshold,
                    "actual_value": v.actual_value,
                    "severity": v.severity,
                    "description": v.description
                }
                for v in self.violations
            ],
            "metrics_available": self.metrics_available,
            "violation_count": len(self.violations)
        }


def violations(shadow_result: ShadowEvalResult, thresholds: Optional[Dict[str, float]] = None) -> GuardResult:
    """
    Check shadow evaluation results against safety guard thresholds.
    
    Args:
        shadow_result: Results from shadow evaluation
        thresholds: Guard thresholds (uses DGM_FAIL_GUARDS if None)
        
    Returns:
        GuardResult with violations and overall pass/fail status
    """
    if thresholds is None:
        thresholds = DGM_FAIL_GUARDS
    
    violations_list = []
    metrics_available = True
    
    logger.debug(f"Evaluating guards for patch {shadow_result.patch_id}")
    
    # Check error rate
    if shadow_result.error_rate_after is not None:
        error_rate_max = thresholds.get("error_rate_max", 0.15)
        if shadow_result.error_rate_after > error_rate_max:
            violations_list.append(GuardViolation(
                guard_name="error_rate_max",
                threshold=error_rate_max,
                actual_value=shadow_result.error_rate_after,
                severity="critical",
                description=f"Error rate {shadow_result.error_rate_after:.1%} exceeds maximum {error_rate_max:.1%}"
            ))
    else:
        metrics_available = False
        logger.warning(f"Error rate metrics not available for patch {shadow_result.patch_id}")
    
    # Check latency regression
    if shadow_result.latency_p95_delta is not None:
        latency_regression_max = thresholds.get("latency_p95_regression", 500.0)
        if shadow_result.latency_p95_delta > latency_regression_max:
            violations_list.append(GuardViolation(
                guard_name="latency_p95_regression",
                threshold=latency_regression_max,
                actual_value=shadow_result.latency_p95_delta,
                severity="warning",
                description=f"P95 latency regression {shadow_result.latency_p95_delta:.0f}ms exceeds threshold {latency_regression_max:.0f}ms"
            ))
    else:
        metrics_available = False
        logger.warning(f"Latency metrics not available for patch {shadow_result.patch_id}")
    
    # Check reward delta minimum
    if shadow_result.reward_delta is not None:
        reward_delta_min = thresholds.get("reward_delta_min", -0.05)
        if shadow_result.reward_delta < reward_delta_min:
            violations_list.append(GuardViolation(
                guard_name="reward_delta_min",
                threshold=reward_delta_min,
                actual_value=shadow_result.reward_delta,
                severity="critical",
                description=f"Reward delta {shadow_result.reward_delta:+.3f} below minimum {reward_delta_min:+.3f}"
            ))
    else:
        metrics_available = False
        logger.warning(f"Reward delta not available for patch {shadow_result.patch_id}")
    
    # Determine overall pass/fail
    passed = len(violations_list) == 0 and metrics_available
    
    result = GuardResult(
        patch_id=shadow_result.patch_id,
        passed=passed,
        violations=violations_list,
        metrics_available=metrics_available
    )
    
    # Log results
    if passed:
        logger.info(f"Guard check PASSED for patch {shadow_result.patch_id}")
    else:
        severity_counts = {}
        for v in violations_list:
            severity_counts[v.severity] = severity_counts.get(v.severity, 0) + 1
        
        logger.warning(f"Guard check FAILED for patch {shadow_result.patch_id}: {severity_counts}")
        for violation in violations_list:
            logger.warning(f"  {violation.guard_name}: {violation.description}")
    
    return result


def batch_guard_check(shadow_results: List[ShadowEvalResult], thresholds: Optional[Dict[str, float]] = None) -> List[GuardResult]:
    """
    Run guard checks on multiple shadow evaluation results.
    
    Args:
        shadow_results: List of shadow evaluation results
        thresholds: Guard thresholds (uses DGM_FAIL_GUARDS if None)
        
    Returns:
        List of GuardResult objects
    """
    logger.info(f"Running batch guard checks on {len(shadow_results)} patches")
    
    guard_results = []
    for shadow_result in shadow_results:
        guard_result = violations(shadow_result, thresholds)
        guard_results.append(guard_result)
    
    # Summary statistics
    passed_count = sum(1 for r in guard_results if r.passed)
    total_violations = sum(len(r.violations) for r in guard_results)
    
    logger.info(f"Guard batch complete: {passed_count}/{len(guard_results)} passed, {total_violations} total violations")
    
    return guard_results


def get_violation_summary(guard_results: List[GuardResult]) -> Dict[str, Any]:
    """
    Generate summary statistics from guard results.
    
    Args:
        guard_results: List of guard evaluation results
        
    Returns:
        Summary statistics dict
    """
    if not guard_results:
        return {"total_patches": 0}
    
    total_patches = len(guard_results)
    passed_patches = sum(1 for r in guard_results if r.passed)
    failed_patches = total_patches - passed_patches
    
    # Violation breakdown by guard
    violation_breakdown = {}
    severity_breakdown = {}
    
    for result in guard_results:
        for violation in result.violations:
            # Count by guard name
            guard_name = violation.guard_name
            violation_breakdown[guard_name] = violation_breakdown.get(guard_name, 0) + 1
            
            # Count by severity
            severity = violation.severity
            severity_breakdown[severity] = severity_breakdown.get(severity, 0) + 1
    
    return {
        "total_patches": total_patches,
        "passed_patches": passed_patches,
        "failed_patches": failed_patches,
        "pass_rate": passed_patches / total_patches,
        "violation_breakdown": violation_breakdown,
        "severity_breakdown": severity_breakdown,
        "metrics_available_count": sum(1 for r in guard_results if r.metrics_available)
    }


def is_guard_enabled(guard_name: str, thresholds: Optional[Dict[str, float]] = None) -> bool:
    """
    Check if a specific guard is enabled.
    
    Args:
        guard_name: Name of guard to check
        thresholds: Guard thresholds (uses DGM_FAIL_GUARDS if None)
        
    Returns:
        True if guard is enabled (has threshold configured)
    """
    if thresholds is None:
        thresholds = DGM_FAIL_GUARDS
    
    return guard_name in thresholds and thresholds[guard_name] is not None


def get_guard_thresholds() -> Dict[str, float]:
    """Get current guard thresholds."""
    return DGM_FAIL_GUARDS.copy()


def validate_thresholds(thresholds: Dict[str, float]) -> List[str]:
    """
    Validate guard threshold values.
    
    Args:
        thresholds: Threshold configuration to validate
        
    Returns:
        List of validation errors (empty if valid)
    """
    errors = []
    
    # Error rate should be between 0 and 1
    if "error_rate_max" in thresholds:
        error_rate_max = thresholds["error_rate_max"]
        if not (0.0 <= error_rate_max <= 1.0):
            errors.append(f"error_rate_max must be between 0.0 and 1.0, got {error_rate_max}")
    
    # Latency regression should be positive
    if "latency_p95_regression" in thresholds:
        latency_regression = thresholds["latency_p95_regression"]
        if latency_regression < 0:
            errors.append(f"latency_p95_regression must be positive, got {latency_regression}")
    
    # Reward delta min should be reasonable (typically negative or small positive)
    if "reward_delta_min" in thresholds:
        reward_delta_min = thresholds["reward_delta_min"]
        if reward_delta_min > 0.1:  # More than 10% improvement required seems excessive
            errors.append(f"reward_delta_min seems too high: {reward_delta_min} (>0.1)")
        if reward_delta_min < -0.5:  # More than 50% degradation allowed seems too permissive
            errors.append(f"reward_delta_min seems too low: {reward_delta_min} (<-0.5)")
    
    return errors


# Predefined threshold sets for different risk tolerances
CONSERVATIVE_GUARDS = {
    "error_rate_max": 0.05,        # Max 5% error rate
    "latency_p95_regression": 200, # Max 200ms p95 regression
    "reward_delta_min": -0.01      # Max 1% reward degradation
}

MODERATE_GUARDS = {
    "error_rate_max": 0.10,        # Max 10% error rate
    "latency_p95_regression": 350, # Max 350ms p95 regression  
    "reward_delta_min": -0.03      # Max 3% reward degradation
}

PERMISSIVE_GUARDS = {
    "error_rate_max": 0.20,        # Max 20% error rate
    "latency_p95_regression": 800, # Max 800ms p95 regression
    "reward_delta_min": -0.10      # Max 10% reward degradation
}

GUARD_PRESETS = {
    "conservative": CONSERVATIVE_GUARDS,
    "moderate": MODERATE_GUARDS,
    "permissive": PERMISSIVE_GUARDS,
    "default": DGM_FAIL_GUARDS
}


def get_guard_preset(preset_name: str) -> Dict[str, float]:
    """
    Get a predefined guard threshold preset.
    
    Args:
        preset_name: Name of preset ("conservative", "moderate", "permissive", "default")
        
    Returns:
        Guard threshold configuration
    """
    if preset_name not in GUARD_PRESETS:
        logger.warning(f"Unknown guard preset '{preset_name}', using default")
        return DGM_FAIL_GUARDS.copy()
    
    return GUARD_PRESETS[preset_name].copy()