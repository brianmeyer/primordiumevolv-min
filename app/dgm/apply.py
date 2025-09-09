"""
DGM Apply - Dry-run application and testing of meta-patches

This module handles the safe application of proposed patches in isolated
environments, running lint and unit tests to validate changes.
"""

import os
import tempfile
import subprocess
import shutil
import logging
import time
from pathlib import Path
from typing import Dict, Any, Optional
from app.dgm.types import MetaPatch, ApplyResult

logger = logging.getLogger(__name__)


class DryRunApplier:
    """
    Handles dry-run application of patches in temporary worktrees.
    """
    
    def __init__(self, repo_path: str = "."):
        self.repo_path = Path(repo_path).resolve()
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
                    logger.debug(f"Cleaned up temp dir: {temp_dir}")
            except Exception as e:
                logger.warning(f"Failed to clean up {temp_dir}: {e}")
        self.temp_dirs.clear()
    
    def _create_worktree(self) -> Path:
        """Create a temporary git worktree for isolated testing."""
        temp_dir = Path(tempfile.mkdtemp(prefix="dgm_apply_"))
        self.temp_dirs.append(temp_dir)
        
        try:
            # Copy current working directory to temp location
            # This avoids git worktree complexity and gives us full isolation
            shutil.copytree(
                self.repo_path,
                temp_dir / "repo",
                ignore=shutil.ignore_patterns(
                    '.git', '__pycache__', '*.pyc', 'node_modules',
                    'logs', 'runs', 'storage/*.db', '.uvicorn.pid'
                )
            )
            
            worktree_path = temp_dir / "repo"
            logger.debug(f"Created worktree at: {worktree_path}")
            return worktree_path
            
        except Exception as e:
            logger.error(f"Failed to create worktree: {e}")
            raise
    
    def _run_command(self, cmd: list, cwd: Path, timeout: int = 60) -> tuple[bool, str, str]:
        """
        Run a command in the specified directory.
        
        Args:
            cmd: Command and arguments
            cwd: Working directory
            timeout: Timeout in seconds
            
        Returns:
            (success, stdout, stderr)
        """
        try:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ, "PYTHONPATH": str(cwd)}
            )
            
            success = result.returncode == 0
            stdout = result.stdout or ""
            stderr = result.stderr or ""
            
            logger.debug(f"Command {' '.join(cmd)}: {'SUCCESS' if success else 'FAILED'}")
            
            return success, stdout, stderr
            
        except subprocess.TimeoutExpired:
            logger.warning(f"Command timed out: {' '.join(cmd)}")
            return False, "", f"Command timed out after {timeout}s"
        except Exception as e:
            logger.error(f"Command failed: {e}")
            return False, "", str(e)
    
    def _apply_patch(self, patch_content: str, worktree: Path) -> tuple[bool, str, str]:
        """
        Apply a patch using git apply.
        
        Args:
            patch_content: Unified diff content
            worktree: Path to worktree
            
        Returns:
            (success, stdout, stderr)
        """
        # Write patch to temporary file
        patch_file = worktree / ".dgm_patch.diff"
        try:
            with open(patch_file, 'w') as f:
                f.write(patch_content)
            
            # First check if patch can be applied
            success, stdout, stderr = self._run_command(
                ["git", "apply", "--check", str(patch_file)],
                worktree,
                timeout=10
            )
            
            if not success:
                logger.warning(f"Patch check failed: {stderr}")
                return False, stdout, stderr
            
            # Apply the patch
            success, stdout, stderr = self._run_command(
                ["git", "apply", str(patch_file)],
                worktree,
                timeout=10
            )
            
            return success, stdout, stderr
            
        finally:
            # Clean up patch file
            if patch_file.exists():
                patch_file.unlink()
    
    def _run_lint(self, worktree: Path) -> tuple[bool, str, str]:
        """
        Run linting on the worktree.
        
        Args:
            worktree: Path to worktree
            
        Returns:
            (success, stdout, stderr)
        """
        # Try ruff first (modern Python linter)
        success, stdout, stderr = self._run_command(
            ["ruff", "check", "--select", "E,W,F", "app/"],
            worktree,
            timeout=30
        )
        
        if success:
            return True, "Linting passed (ruff)", ""
        
        # Fall back to flake8 if ruff not available
        if "command not found" in stderr or "not found" in stderr:
            logger.debug("ruff not found, trying flake8")
            success, stdout, stderr = self._run_command(
                ["flake8", "--select", "E,W,F", "app/"],
                worktree,
                timeout=30
            )
            
            if success:
                return True, "Linting passed (flake8)", ""
        
        # If both fail, return ruff results
        return False, stdout, stderr
    
    def _run_unit_tests(self, worktree: Path) -> tuple[bool, str, str]:
        """
        Run unit tests on the worktree.
        
        Args:
            worktree: Path to worktree
            
        Returns:
            (success, stdout, stderr)
        """
        # Look for test files
        test_patterns = [
            "test_*.py",
            "*_test.py", 
            "tests/test_*.py",
            "app/test_*.py"
        ]
        
        test_files = []
        for pattern in test_patterns:
            test_files.extend(worktree.glob(pattern))
            test_files.extend(worktree.glob(f"**/{pattern}"))
        
        if not test_files:
            logger.info("No unit test files found")
            return True, "No unit tests found - skipping", ""
        
        # Run pytest with quiet mode on found test files
        test_paths = [str(f.relative_to(worktree)) for f in test_files[:5]]  # Limit to 5 files
        
        success, stdout, stderr = self._run_command(
            ["python", "-m", "pytest", "-q", "--tb=short"] + test_paths,
            worktree,
            timeout=60
        )
        
        # If pytest not available, try unittest
        if not success and ("command not found" in stderr or "No module named" in stderr):
            logger.debug("pytest not found, trying unittest")
            success, stdout, stderr = self._run_command(
                ["python", "-m", "unittest", "discover", "-s", ".", "-p", "test_*.py", "-q"],
                worktree,
                timeout=60
            )
        
        return success, stdout, stderr


def try_patch(patch: MetaPatch, dry_run: bool = True) -> ApplyResult:
    """
    Apply a patch and validate it.
    
    Args:
        patch: MetaPatch to apply
        dry_run: If True, test in isolation. If False, apply to live repo
        
    Returns:
        ApplyResult with validation results
    """
    if not dry_run:
        # Live application requires special handling
        from app.config import DGM_ALLOW_COMMITS
        if not DGM_ALLOW_COMMITS:
            raise PermissionError("Live commits disabled. Set DGM_ALLOW_COMMITS=1 to enable (dangerous!)")
    
    start_time = time.time()
    result = ApplyResult(patch_id=patch.id, success=False)
    
    logger.info(f"Dry-run applying patch {patch.id} (area: {patch.area}, origin: {patch.origin})")
    
    try:
        with DryRunApplier() as applier:
            # Create isolated worktree
            worktree = applier._create_worktree()
            
            # Apply the patch
            apply_ok, apply_stdout, apply_stderr = applier._apply_patch(patch.diff, worktree)
            result.apply_ok = apply_ok
            
            if not apply_ok:
                result.stdout = apply_stdout
                result.stderr = apply_stderr
                logger.warning(f"Patch {patch.id} failed to apply: {apply_stderr}")
                return result
            
            # Run linting
            lint_ok, lint_stdout, lint_stderr = applier._run_lint(worktree)
            result.lint_ok = lint_ok
            
            # Run unit tests
            tests_ok, test_stdout, test_stderr = applier._run_unit_tests(worktree)
            result.tests_ok = tests_ok
            
            # Combine outputs
            all_stdout = f"APPLY: {apply_stdout}\nLINT: {lint_stdout}\nTESTS: {test_stdout}"
            all_stderr = f"APPLY: {apply_stderr}\nLINT: {lint_stderr}\nTESTS: {test_stderr}"
            
            result.stdout = all_stdout
            result.stderr = all_stderr
            result.success = apply_ok and lint_ok and tests_ok
            
            # Update patch with results
            patch.apply_ok = apply_ok
            patch.lint_ok = lint_ok
            patch.tests_ok = tests_ok
            patch.stdout_snippet = result.stdout_snippet
            
            logger.info(f"Patch {patch.id} validation: apply={apply_ok}, lint={lint_ok}, tests={tests_ok}")
            
    except Exception as e:
        logger.error(f"Exception during patch application: {e}")
        result.stderr = str(e)
        result.success = False
    
    result.execution_time_ms = int((time.time() - start_time) * 1000)
    return result


def revert():
    """Revert changes (no-op in dry-run mode)."""
    logger.debug("Revert called - no-op in dry-run mode")
    pass


def commit():
    """Commit changes (no-op in dry-run mode).""" 
    logger.debug("Commit called - no-op in dry-run mode")
    pass


def batch_try_patches(patches: list[MetaPatch], dry_run: bool = True) -> list[ApplyResult]:
    """
    Apply multiple patches sequentially in dry-run mode.
    
    Args:
        patches: List of patches to apply
        dry_run: Must be True for Stage-1
        
    Returns:
        List of ApplyResults
    """
    logger.info(f"Batch applying {len(patches)} patches in dry-run mode")
    
    results = []
    for i, patch in enumerate(patches):
        logger.info(f"Processing patch {i+1}/{len(patches)}: {patch.id}")
        result = try_patch(patch, dry_run=dry_run)
        results.append(result)
        
        # Log progress
        if result.success:
            logger.info(f"Patch {patch.id}: ✓ SUCCESS")
        else:
            logger.warning(f"Patch {patch.id}: ✗ FAILED")
    
    # Summary
    successful = sum(1 for r in results if r.success)
    logger.info(f"Batch complete: {successful}/{len(patches)} patches successful")
    
    return results


# Global applier instance for reuse
_global_applier: Optional[DryRunApplier] = None


def get_applier() -> DryRunApplier:
    """Get global applier instance."""
    global _global_applier
    if _global_applier is None:
        _global_applier = DryRunApplier()
    return _global_applier


def cleanup_applier():
    """Clean up global applier."""
    global _global_applier
    if _global_applier:
        _global_applier.cleanup()
        _global_applier = None


def commit_patch(patch: MetaPatch, shadow_result: Optional[Any] = None) -> Dict[str, Any]:
    """
    Commit a patch to the live repository.
    
    This function:
    1. Creates a temporary branch
    2. Applies the patch
    3. Runs tests (if configured)
    4. Commits with descriptive message
    5. Saves artifacts
    
    Args:
        patch: MetaPatch to commit
        shadow_result: Optional shadow evaluation results
        
    Returns:
        Dict with commit results including SHA and status
    """
    from app.config import DGM_ALLOW_COMMITS, DGM_TEST_BEFORE_COMMIT
    from app.dgm.storage import save_commit_artifact
    import subprocess
    
    if not DGM_ALLOW_COMMITS:
        raise PermissionError("Live commits disabled. Set DGM_ALLOW_COMMITS=1 to enable")
    
    logger.info(f"Committing patch {patch.id} to live repository")
    
    # Create result structure
    result = {
        "patch_id": patch.id,
        "status": "pending",
        "commit_sha": None,
        "branch": None,
        "test_results": None,
        "error": None,
        "artifact_path": None
    }
    
    try:
        # Get current branch
        current_branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, check=True
        ).stdout.strip()
        
        # Create temporary branch
        branch_name = f"dgm-patch-{patch.id[:8]}-{int(time.time())}"
        subprocess.run(["git", "checkout", "-b", branch_name], check=True)
        result["branch"] = branch_name
        
        logger.info(f"Created branch {branch_name}")
        
        # Apply the patch
        patch_file = Path(f"/tmp/dgm_commit_{patch.id}.diff")
        with open(patch_file, 'w') as f:
            f.write(patch.diff)
        
        apply_result = subprocess.run(
            ["git", "apply", str(patch_file)],
            capture_output=True, text=True
        )
        
        if apply_result.returncode != 0:
            raise Exception(f"Patch application failed: {apply_result.stderr}")
        
        # Run tests if configured
        if DGM_TEST_BEFORE_COMMIT:
            logger.info("Running tests before commit...")
            test_result = subprocess.run(
                ["python", "-m", "pytest", "-q", "--tb=short"],
                capture_output=True, text=True, timeout=60
            )
            
            result["test_results"] = {
                "passed": test_result.returncode == 0,
                "output": test_result.stdout[:500],  # Truncate output
                "return_code": test_result.returncode
            }
            
            if test_result.returncode != 0:
                raise Exception(f"Tests failed: {test_result.stdout}")
        
        # Stage changes
        subprocess.run(["git", "add", "-A"], check=True)
        
        # Create commit message
        reward_str = f"reward_delta={shadow_result.reward_delta:+.3f}" if shadow_result and shadow_result.reward_delta else ""
        commit_message = f"[DGM] {patch.id[:8]} {patch.area} {reward_str}\n\n{patch.notes}\n\nAutomatically committed by DGM system"
        
        # Commit
        commit_result = subprocess.run(
            ["git", "commit", "-m", commit_message],
            capture_output=True, text=True, check=True
        )
        
        # Get commit SHA
        commit_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True
        ).stdout.strip()
        
        result["commit_sha"] = commit_sha
        result["status"] = "committed"
        
        logger.info(f"Committed patch {patch.id} as {commit_sha[:8]}")
        
        # Merge back to original branch (fast-forward if possible)
        subprocess.run(["git", "checkout", current_branch], check=True)
        merge_result = subprocess.run(
            ["git", "merge", "--ff-only", branch_name],
            capture_output=True, text=True
        )
        
        if merge_result.returncode != 0:
            # Try regular merge if fast-forward fails
            subprocess.run(["git", "merge", branch_name], check=True)
        
        # Clean up branch
        subprocess.run(["git", "branch", "-d", branch_name], check=True)
        
        # Save artifact
        artifact_path = save_commit_artifact(
            patch=patch,
            shadow_result=shadow_result,
            commit_sha=commit_sha,
            test_results=result["test_results"]
        )
        result["artifact_path"] = artifact_path
        
    except Exception as e:
        logger.error(f"Commit failed for patch {patch.id}: {e}")
        result["status"] = "failed"
        result["error"] = str(e)
        
        # Try to clean up
        try:
            subprocess.run(["git", "checkout", current_branch], check=False)
            subprocess.run(["git", "branch", "-D", branch_name], check=False)
        except:
            pass
    
    finally:
        # Clean up patch file
        if patch_file.exists():
            patch_file.unlink()
    
    return result


def rollback_commit(commit_sha: str) -> Dict[str, Any]:
    """
    Rollback a previously committed patch.
    
    Args:
        commit_sha: Git commit SHA to revert
        
    Returns:
        Dict with rollback results
    """
    from app.config import DGM_ALLOW_COMMITS
    from app.dgm.storage import get_patch_storage
    import subprocess
    
    if not DGM_ALLOW_COMMITS:
        raise PermissionError("Rollback disabled. Set DGM_ALLOW_COMMITS=1 to enable")
    
    logger.info(f"Rolling back commit {commit_sha}")
    
    result = {
        "commit_sha": commit_sha,
        "rollback_sha": None,
        "status": "pending",
        "error": None
    }
    
    try:
        # Verify commit exists
        verify_result = subprocess.run(
            ["git", "rev-parse", commit_sha],
            capture_output=True, text=True
        )
        
        if verify_result.returncode != 0:
            raise Exception(f"Commit {commit_sha} not found")
        
        # Create revert commit
        revert_result = subprocess.run(
            ["git", "revert", "--no-edit", commit_sha],
            capture_output=True, text=True
        )
        
        if revert_result.returncode != 0:
            raise Exception(f"Revert failed: {revert_result.stderr}")
        
        # Get rollback commit SHA
        rollback_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True
        ).stdout.strip()
        
        result["rollback_sha"] = rollback_sha
        result["status"] = "rolled_back"
        
        logger.info(f"Rolled back {commit_sha[:8]} with {rollback_sha[:8]}")
        
        # Update storage if we can find the patch
        storage = get_patch_storage()
        artifacts = storage.list_artifacts()
        for artifact in artifacts:
            if artifact.commit_sha == commit_sha:
                storage.update_artifact_status(
                    artifact.patch_id, 
                    "rolled_back",
                    rollback_sha=rollback_sha
                )
                break
        
    except Exception as e:
        logger.error(f"Rollback failed for {commit_sha}: {e}")
        result["status"] = "failed"
        result["error"] = str(e)
    
    return result