"""
DGM Types - Data structures for Darwin Gödel Machine operations

This module defines the core data types used throughout the DGM system,
particularly for Stage-1 proposer and apply operations.
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any
import uuid


@dataclass
class MetaPatch:
    """
    Represents a proposed meta-modification to the system.
    
    Each patch contains:
    - Identification: id, area, origin (model that proposed it)
    - Content: diff (unified diff), notes (rationale)
    - Metadata: loc_delta (lines changed), validation results
    """
    id: str                    # Unique identifier
    area: str                  # Modification area (prompts, bandit, etc.)
    origin: str                # Model ID that proposed this patch
    notes: str                 # One-line rationale/description
    diff: str                  # Unified diff content
    loc_delta: int             # Lines of code delta (additions + deletions)
    
    # Validation results (populated during dry-run)
    lint_ok: Optional[bool] = None      # Linting passed
    tests_ok: Optional[bool] = None     # Unit tests passed
    apply_ok: Optional[bool] = None     # Patch applied cleanly
    stdout_snippet: str = ""            # Truncated output from validation
    
    @classmethod
    def create(cls, area: str, origin: str, notes: str, diff: str, loc_delta: int) -> 'MetaPatch':
        """Create a new MetaPatch with generated UUID."""
        return cls(
            id=str(uuid.uuid4()),
            area=area,
            origin=origin,
            notes=notes,
            diff=diff,
            loc_delta=loc_delta
        )
    
    def to_summary_dict(self) -> Dict[str, Any]:
        """Convert to dict suitable for SSE/API responses."""
        return {
            "id": self.id,
            "area": self.area,
            "origin": self.origin,
            "notes": self.notes,
            "loc_delta": self.loc_delta,
            "lint_ok": self.lint_ok,
            "tests_ok": self.tests_ok,
            "apply_ok": self.apply_ok
        }
    
    def is_valid(self) -> bool:
        """Check if patch passed all validation checks."""
        return all([
            self.apply_ok is True,
            self.lint_ok is True, 
            self.tests_ok is True
        ])


@dataclass 
class ProposalRequest:
    """
    Request for generating DGM proposals.
    """
    count: int = 6                      # Number of proposals to generate
    allowed_areas: Optional[list] = None # Allowed modification areas
    max_loc_delta: int = 50             # Maximum lines of code change
    dry_run: bool = True                # Apply patches in dry-run mode
    

@dataclass
class ProposalResponse:
    """
    Response from DGM proposal generation.
    """
    patches: list[MetaPatch]            # Successfully generated patches
    rejected: list[Dict[str, Any]]      # Rejected proposals with reasons
    total_generated: int                # Total proposals attempted
    execution_time_ms: int              # Time taken to generate
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "patches": [p.to_summary_dict() for p in self.patches],
            "rejected": self.rejected,
            "total_generated": self.total_generated,
            "execution_time_ms": self.execution_time_ms,
            "count": len(self.patches)
        }


@dataclass
class ApplyResult:
    """
    Result from applying a patch (dry-run or live).
    """
    patch_id: str                       # ID of applied patch
    success: bool                       # Overall success
    lint_ok: bool = False               # Linting passed
    tests_ok: bool = False              # Tests passed  
    apply_ok: bool = False              # Patch applied cleanly
    stdout: str = ""                    # Command output
    stderr: str = ""                    # Error output
    execution_time_ms: int = 0          # Time taken
    
    @property
    def stdout_snippet(self) -> str:
        """Return truncated stdout for summary."""
        if len(self.stdout) <= 200:
            return self.stdout
        return self.stdout[:200] + "..."


# Allowed modification areas with descriptions
DGM_AREA_DESCRIPTIONS = {
    "prompts": "System prompts and prompt templates",
    "bandit": "Multi-armed bandit algorithms and parameters", 
    "asi_lite": "Lightweight ASI safety mechanisms",
    "rag": "RAG (Retrieval Augmented Generation) configuration",
    "memory_policy": "Memory system policies and weights",
    "ui_metrics": "UI metrics tiles and dashboard elements"
}


def validate_area(area: str) -> bool:
    """Check if modification area is allowed."""
    from app.config import DGM_ALLOWED_AREAS
    return area in DGM_ALLOWED_AREAS


def calculate_loc_delta(diff: str) -> int:
    """
    Calculate lines of code delta from a unified diff.
    
    Counts additions (+) and deletions (-) to get total change magnitude.
    """
    if not diff:
        return 0
    
    additions = 0
    deletions = 0
    
    for line in diff.split('\n'):
        if line.startswith('+') and not line.startswith('+++'):
            additions += 1
        elif line.startswith('-') and not line.startswith('---'):
            deletions += 1
    
    return additions + deletions


def is_safe_diff(diff: str) -> tuple[bool, str]:
    """
    Check if diff is safe (no restricted areas).
    
    Returns:
        (is_safe: bool, reason: str)
    """
    # Forbidden patterns in diffs
    forbidden_patterns = [
        'auth', 'secret', 'password', 'token', 'key', 'billing',
        'schema', 'migration', 'model_weights', 'external_client',
        'security', 'crypto', 'payment', 'user_data', 'admin'
    ]
    
    # Forbidden file paths
    forbidden_paths = [
        '.env', 'config/secrets', 'auth/', 'billing/', 'admin/',
        'migrations/', 'schema/', 'weights/', 'keys/'
    ]
    
    diff_lower = diff.lower()
    
    # Check for forbidden patterns
    for pattern in forbidden_patterns:
        if pattern in diff_lower:
            return False, f"Contains forbidden pattern: {pattern}"
    
    # Check for forbidden file paths
    for path in forbidden_paths:
        if path in diff_lower:
            return False, f"Modifies restricted path: {path}"
    
    # Check diff size isn't too large
    if len(diff.split('\n')) > 500:
        return False, "Diff too large (>500 lines)"
    
    return True, "Safe"