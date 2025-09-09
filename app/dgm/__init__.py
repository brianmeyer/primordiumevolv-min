"""
Darwin Gödel Machine (DGM) - Phase 5 Self-Modification Scaffold

The DGM system provides a framework for systematic self-modification of the 
PrimordiumEvolv system through proposal-based evolution and canary testing.

This is a scaffold implementation with minimal functionality to establish
the architecture without affecting existing system behavior.
"""

from app.config import FF_DGM

# DGM components - only imported when feature flag is enabled
if FF_DGM:
    from .core import DGMCore
    from .proposals import ProposalSystem
    from .canary import CanaryTester
    
    __all__ = ["DGMCore", "ProposalSystem", "CanaryTester"]
else:
    __all__ = []

def is_enabled() -> bool:
    """Check if DGM system is enabled."""
    return FF_DGM