"""
DGM Selector - Ranking and selection of safe patches based on performance metrics

This module implements patch selection logic that filters out violations
and picks the best performing patch based on reward delta and latency.
"""

import logging
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass
from app.dgm.eval import ShadowEvalResult
from app.dgm.guards import GuardResult, violations

logger = logging.getLogger(__name__)


@dataclass
class SelectionCandidate:
    """A patch candidate for selection."""
    shadow_result: ShadowEvalResult
    guard_result: GuardResult
    rank_score: float            # Computed ranking score
    rank_position: int          # Final rank position (1 = best)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "patch_id": self.shadow_result.patch_id,
            "passed_guards": self.guard_result.passed,
            "violations": len(self.guard_result.violations),
            "rank_score": self.rank_score,
            "rank_position": self.rank_position,
            "reward_delta": self.shadow_result.reward_delta,
            "latency_p95_delta": self.shadow_result.latency_p95_delta,
            "error_rate_after": self.shadow_result.error_rate_after,
            "is_improvement": self.shadow_result.is_improvement
        }


@dataclass
class SelectionResult:
    """Results from patch selection process."""
    winner: Optional[SelectionCandidate]      # Selected winner (None if no safe candidates)
    candidates: List[SelectionCandidate]      # All candidates with rankings
    filtered_count: int                       # Number filtered out by guards
    selection_criteria: Dict[str, Any]        # Criteria used for selection
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "winner": self.winner.to_dict() if self.winner else None,
            "candidates": [c.to_dict() for c in self.candidates],
            "total_candidates": len(self.candidates),
            "safe_candidates": len([c for c in self.candidates if c.guard_result.passed]),
            "filtered_count": self.filtered_count,
            "selection_criteria": self.selection_criteria,
            "has_winner": self.winner is not None
        }


def _compute_rank_score(shadow_result: ShadowEvalResult, guard_result: GuardResult) -> float:
    """
    Compute ranking score for a patch candidate.
    
    Scoring algorithm:
    - Primary: reward_delta (higher is better)
    - Tie-breaker: latency_p95_delta (lower is better, normalized)
    - Penalty: Guard violations disqualify completely
    
    Args:
        shadow_result: Shadow evaluation results
        guard_result: Guard evaluation results
        
    Returns:
        Ranking score (higher is better, -inf if disqualified)
    """
    # Disqualify patches with guard violations
    if not guard_result.passed:
        return float('-inf')
    
    # Disqualify patches without reward metrics
    if shadow_result.reward_delta is None:
        logger.warning(f"Patch {shadow_result.patch_id} missing reward_delta, disqualified")
        return float('-inf')
    
    # Primary score: reward delta
    score = shadow_result.reward_delta
    
    # Tie-breaker: penalize latency regression (normalize to reward scale)
    if shadow_result.latency_p95_delta is not None:
        # Convert latency delta (ms) to reward penalty (negative is better)
        # Scale: 100ms regression = -0.001 reward penalty
        latency_penalty = shadow_result.latency_p95_delta * 0.00001
        score -= latency_penalty
    
    logger.debug(f"Patch {shadow_result.patch_id}: score={score:.4f} "
                f"(reward_delta={shadow_result.reward_delta:+.3f}, "
                f"latency_delta={shadow_result.latency_p95_delta}ms)")
    
    return score


def rank_and_pick(shadow_results: List[ShadowEvalResult], 
                  guard_thresholds: Optional[Dict[str, float]] = None) -> SelectionResult:
    """
    Rank patches and pick the best safe candidate.
    
    Algorithm:
    1. Run guard checks on all patches
    2. Filter out patches with violations
    3. Rank remaining patches by reward_delta (primary) and latency_p95_delta (tie-breaker)
    4. Select winner with highest rank
    
    Args:
        shadow_results: Results from shadow evaluation
        guard_thresholds: Guard thresholds (uses defaults if None)
        
    Returns:
        SelectionResult with winner and all candidates
    """
    logger.info(f"Ranking and selecting from {len(shadow_results)} shadow evaluation results")
    
    if not shadow_results:
        return SelectionResult(
            winner=None,
            candidates=[],
            filtered_count=0,
            selection_criteria={"reason": "no_candidates"}
        )
    
    # Run guard checks
    candidates = []
    filtered_count = 0
    
    for shadow_result in shadow_results:
        guard_result = violations(shadow_result, guard_thresholds)
        
        # Compute rank score
        rank_score = _compute_rank_score(shadow_result, guard_result)
        
        candidate = SelectionCandidate(
            shadow_result=shadow_result,
            guard_result=guard_result,
            rank_score=rank_score,
            rank_position=0  # Will be set after sorting
        )
        
        if rank_score == float('-inf'):
            filtered_count += 1
            logger.debug(f"Filtered patch {shadow_result.patch_id}: violations or missing metrics")
        
        candidates.append(candidate)
    
    # Sort candidates by rank score (highest first)
    candidates.sort(key=lambda c: c.rank_score, reverse=True)
    
    # Assign rank positions
    for i, candidate in enumerate(candidates):
        candidate.rank_position = i + 1
    
    # Select winner (first candidate with positive score that passed guards)
    winner = None
    safe_candidates = [c for c in candidates if c.guard_result.passed and c.rank_score > float('-inf')]
    
    if safe_candidates:
        winner = safe_candidates[0]
        logger.info(f"Selected winner: patch {winner.shadow_result.patch_id} "
                   f"(score={winner.rank_score:.4f}, "
                   f"reward_delta={winner.shadow_result.reward_delta:+.3f})")
    else:
        logger.warning("No safe candidates found - all patches filtered out by guards or missing metrics")
    
    # Build selection criteria summary
    selection_criteria = {
        "algorithm": "reward_delta_primary_latency_tiebreak",
        "primary_metric": "reward_delta",
        "tie_breaker": "latency_p95_delta",
        "guard_filtering": True,
        "total_evaluated": len(shadow_results),
        "safe_candidates": len(safe_candidates),
        "winner_criteria": {
            "min_reward_delta": "any_positive",
            "latency_penalty_factor": 0.00001
        } if winner else None
    }
    
    result = SelectionResult(
        winner=winner,
        candidates=candidates,
        filtered_count=filtered_count,
        selection_criteria=selection_criteria
    )
    
    logger.info(f"Selection complete: winner={'yes' if winner else 'no'}, "
               f"safe_candidates={len(safe_candidates)}, filtered={filtered_count}")
    
    return result


def get_selection_summary(selection_result: SelectionResult) -> Dict[str, Any]:
    """
    Generate a summary of the selection process.
    
    Args:
        selection_result: Results from rank_and_pick
        
    Returns:
        Summary dictionary
    """
    candidates = selection_result.candidates
    safe_candidates = [c for c in candidates if c.guard_result.passed]
    
    # Reward delta distribution
    reward_deltas = [c.shadow_result.reward_delta for c in safe_candidates 
                    if c.shadow_result.reward_delta is not None]
    
    summary = {
        "total_candidates": len(candidates),
        "safe_candidates": len(safe_candidates),
        "filtered_candidates": selection_result.filtered_count,
        "has_winner": selection_result.winner is not None,
        "winner_patch_id": selection_result.winner.shadow_result.patch_id if selection_result.winner else None,
        "reward_delta_stats": {
            "min": min(reward_deltas) if reward_deltas else None,
            "max": max(reward_deltas) if reward_deltas else None,
            "avg": sum(reward_deltas) / len(reward_deltas) if reward_deltas else None,
            "count": len(reward_deltas)
        },
        "guard_violations": sum(len(c.guard_result.violations) for c in candidates),
        "selection_algorithm": selection_result.selection_criteria.get("algorithm", "unknown")
    }
    
    return summary


def compare_patches(patch1: ShadowEvalResult, patch2: ShadowEvalResult, 
                   guard_thresholds: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    """
    Compare two patches and determine which is better.
    
    Args:
        patch1: First patch to compare
        patch2: Second patch to compare  
        guard_thresholds: Guard thresholds for safety checks
        
    Returns:
        Comparison results with winner and reasoning
    """
    logger.debug(f"Comparing patches {patch1.patch_id} vs {patch2.patch_id}")
    
    # Run guard checks
    guard1 = violations(patch1, guard_thresholds)
    guard2 = violations(patch2, guard_thresholds)
    
    # Compute scores
    score1 = _compute_rank_score(patch1, guard1)
    score2 = _compute_rank_score(patch2, guard2)
    
    # Determine winner
    if score1 > score2:
        winner = patch1
        winner_score = score1
        reason = "higher_rank_score"
    elif score2 > score1:
        winner = patch2
        winner_score = score2
        reason = "higher_rank_score"
    else:
        # Tie - use patch ID as deterministic tie-breaker
        if patch1.patch_id < patch2.patch_id:
            winner = patch1
            winner_score = score1
            reason = "tie_broken_by_patch_id"
        else:
            winner = patch2
            winner_score = score2
            reason = "tie_broken_by_patch_id"
    
    return {
        "winner": winner.patch_id,
        "winner_score": winner_score,
        "reason": reason,
        "scores": {
            patch1.patch_id: score1,
            patch2.patch_id: score2
        },
        "guard_results": {
            patch1.patch_id: guard1.passed,
            patch2.patch_id: guard2.passed
        }
    }


def filter_safe_patches(shadow_results: List[ShadowEvalResult],
                       guard_thresholds: Optional[Dict[str, float]] = None) -> List[ShadowEvalResult]:
    """
    Filter shadow results to only include patches that pass guard checks.
    
    Args:
        shadow_results: Shadow evaluation results to filter
        guard_thresholds: Guard thresholds (uses defaults if None)
        
    Returns:
        List of safe patches that passed all guards
    """
    safe_patches = []
    
    for shadow_result in shadow_results:
        guard_result = violations(shadow_result, guard_thresholds)
        if guard_result.passed:
            safe_patches.append(shadow_result)
        else:
            logger.debug(f"Filtered unsafe patch {shadow_result.patch_id}: "
                        f"{len(guard_result.violations)} violations")
    
    logger.info(f"Filtered {len(shadow_results)} patches → {len(safe_patches)} safe patches")
    return safe_patches


def get_top_k_patches(shadow_results: List[ShadowEvalResult], 
                     k: int = 3,
                     guard_thresholds: Optional[Dict[str, float]] = None) -> List[SelectionCandidate]:
    """
    Get top K patches after ranking and filtering.
    
    Args:
        shadow_results: Shadow evaluation results
        k: Number of top patches to return
        guard_thresholds: Guard thresholds for safety filtering
        
    Returns:
        List of top K selection candidates
    """
    selection_result = rank_and_pick(shadow_results, guard_thresholds)
    
    # Return top K safe candidates
    safe_candidates = [c for c in selection_result.candidates 
                      if c.guard_result.passed and c.rank_score > float('-inf')]
    
    return safe_candidates[:k]