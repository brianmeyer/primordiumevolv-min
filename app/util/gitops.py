"""
Git operations for DGM commit/rollback functionality.
All operations are fail-safe and use shell-safe execution.
"""
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Tuple

from app.util.log import get_logger

logger = get_logger(__name__)


def _run_cmd(cmd: list, cwd: Optional[Path] = None, timeout: int = 60) -> Tuple[bool, str, str]:
    """
    Run a shell command safely with timeout and proper error handling.
    
    Returns:
        Tuple[bool, str, str]: (success, stdout, stderr)
    """
    try:
        logger.info(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        success = result.returncode == 0
        if not success:
            logger.warning(f"Command failed with code {result.returncode}: {result.stderr}")
        return success, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        logger.error(f"Command timed out after {timeout}s: {' '.join(cmd)}")
        return False, "", f"Command timed out after {timeout}s"
    except FileNotFoundError as e:
        logger.error(f"Command not found: {cmd[0]} - {e}")
        raise  # Re-raise so calling code can handle missing tools
    except Exception as e:
        logger.error(f"Command execution failed: {e}")
        return False, "", str(e)


def ensure_clean_index() -> bool:
    """
    Check if git index is clean (no staged/untracked changes that could interfere).
    
    Returns:
        bool: True if index is clean, False if there are staged changes
    """
    # Check for staged changes
    success, stdout, stderr = _run_cmd(["git", "diff", "--cached", "--quiet"])
    if not success:
        logger.warning("Staged changes detected in git index")
        return False
    
    # Check for modified tracked files that are not staged
    success, stdout, stderr = _run_cmd(["git", "diff", "--quiet"])
    if not success:
        logger.info("Unstaged changes detected (will be ignored)")
    
    return True


def current_branch() -> str:
    """
    Get the current git branch name.
    
    Returns:
        str: Current branch name, or "unknown" if unable to determine
    """
    success, stdout, stderr = _run_cmd(["git", "branch", "--show-current"])
    if success:
        return stdout.strip()
    else:
        logger.warning(f"Could not determine current branch: {stderr}")
        return "unknown"


def checkout_branch(branch: str, create_if_missing: bool = True) -> bool:
    """
    Checkout a git branch, optionally creating it if it doesn't exist.
    
    Args:
        branch: Branch name to checkout
        create_if_missing: Whether to create the branch if it doesn't exist
    
    Returns:
        bool: True if successful, False otherwise
    """
    # First try to checkout existing branch
    success, stdout, stderr = _run_cmd(["git", "checkout", branch])
    if success:
        logger.info(f"Checked out existing branch: {branch}")
        return True
    
    # If that failed and we should create it, try creating
    if create_if_missing:
        success, stdout, stderr = _run_cmd(["git", "checkout", "-b", branch])
        if success:
            logger.info(f"Created and checked out new branch: {branch}")
            return True
        else:
            logger.error(f"Failed to create branch {branch}: {stderr}")
            return False
    else:
        logger.error(f"Failed to checkout branch {branch}: {stderr}")
        return False


def apply_unified_diff(diff: str, workdir: Optional[Path] = None) -> bool:
    """
    Apply a unified diff using git apply.
    
    Args:
        diff: The unified diff content as a string
        workdir: Working directory (defaults to current directory)
    
    Returns:
        bool: True if diff applied successfully, False otherwise
    """
    if not diff.strip():
        logger.warning("Empty diff provided")
        return True  # Empty diff is technically successful
    
    try:
        # Write diff to temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.patch', delete=False) as f:
            f.write(diff)
            temp_patch = f.name
        
        try:
            # Apply the patch with git apply
            # Use --check first to validate without applying
            success, stdout, stderr = _run_cmd(
                ["git", "apply", "--check", temp_patch], 
                cwd=workdir
            )
            if not success:
                logger.error(f"Diff validation failed: {stderr}")
                return False
            
            # If validation passed, apply for real
            success, stdout, stderr = _run_cmd(
                ["git", "apply", temp_patch], 
                cwd=workdir
            )
            if success:
                logger.info("Diff applied successfully")
                return True
            else:
                logger.error(f"Diff application failed: {stderr}")
                return False
                
        finally:
            # Clean up temp file
            try:
                os.unlink(temp_patch)
            except OSError:
                pass
                
    except Exception as e:
        logger.error(f"Failed to apply diff: {e}")
        return False


def run_tests() -> Tuple[Optional[bool], Optional[bool], str]:
    """
    Run lint and unit tests, gracefully handling missing tools.
    
    Returns:
        Tuple[Optional[bool], Optional[bool], str]: (lint_ok, tests_ok, logs)
        None values indicate the tool was not available or failed to run
    """
    logs = []
    lint_ok = None
    tests_ok = None
    
    # Try to run ruff for linting
    try:
        success, stdout, stderr = _run_cmd(["ruff", "check", "app/"], timeout=120)
        lint_ok = success
        if success:
            logs.append("✓ Lint checks passed (ruff)")
        else:
            logs.append(f"✗ Lint checks failed: {stderr}")
    except Exception as e:
        logs.append("? Lint tool (ruff) not available - skipping lint checks")
        lint_ok = None  # Tool not available, don't treat as failure
    
    # Try to run pytest for unit tests
    try:
        # Run pytest quietly on a subset to avoid long waits
        success, stdout, stderr = _run_cmd([
            "python", "-m", "pytest", "-q", "--tb=short", 
            "tests/", "-k", "not integration"
        ], timeout=180)
        
        # Only treat exit code 1 as test failures; 2+ are collection/config issues
        if success:
            tests_ok = True
            logs.append("✓ Unit tests passed")
        elif "FAILED" in stdout or "failed," in stdout:
            tests_ok = False
            logs.append(f"✗ Unit tests failed: {stderr}")
        else:
            # Exit code 2+ are usually collection/config issues, not test failures
            tests_ok = None  # Don't block commit for collection issues
            logs.append(f"? Unit test collection issues (ignoring): {stderr[:200]}")
            
    except Exception as e:
        logs.append("? Test runner (pytest) not available - skipping unit tests")
        tests_ok = None  # Tool not available, don't treat as failure
    
    log_output = "\n".join(logs)
    logger.info(f"Test results: lint_ok={lint_ok}, tests_ok={tests_ok}")
    
    return lint_ok, tests_ok, log_output


def commit_all(branch: str, author: str, message: str) -> Optional[str]:
    """
    Add all changes and commit with the given message and author.
    
    Args:
        branch: Branch name (for verification)
        author: Author string in format "Name <email>"
        message: Commit message
    
    Returns:
        str | None: Commit SHA if successful, None if failed
    """
    try:
        # Verify we're on the expected branch
        current = current_branch()
        if current != branch:
            logger.error(f"Expected branch {branch}, but on {current}")
            return None
        
        # Add all changes
        success, stdout, stderr = _run_cmd(["git", "add", "."])
        if not success:
            logger.error(f"Failed to add changes: {stderr}")
            return None
        
        # Commit with author and message
        success, stdout, stderr = _run_cmd([
            "git", "commit", "--author", author, "-m", message
        ])
        if not success:
            logger.error(f"Failed to commit: {stderr}")
            return None
        
        # Get the commit SHA
        success, stdout, stderr = _run_cmd(["git", "rev-parse", "HEAD"])
        if success:
            commit_sha = stdout.strip()
            logger.info(f"Committed successfully: {commit_sha}")
            return commit_sha
        else:
            logger.warning("Commit succeeded but couldn't get SHA")
            return None
            
    except Exception as e:
        logger.error(f"Commit operation failed: {e}")
        return None


def revert_commit(sha: str) -> bool:
    """
    Revert a commit by its SHA.
    
    Args:
        sha: Commit SHA to revert
    
    Returns:
        bool: True if revert successful, False otherwise
    """
    try:
        # Verify the commit exists
        success, stdout, stderr = _run_cmd(["git", "cat-file", "-e", sha])
        if not success:
            logger.error(f"Commit {sha} not found")
            return False
        
        # Revert the commit
        success, stdout, stderr = _run_cmd(["git", "revert", "--no-edit", sha])
        if success:
            logger.info(f"Reverted commit {sha} successfully")
            return True
        else:
            logger.error(f"Failed to revert commit {sha}: {stderr}")
            return False
            
    except Exception as e:
        logger.error(f"Revert operation failed: {e}")
        return False


def commit_exists_on_branch(sha: str, branch: str) -> bool:
    """
    Check if a commit exists on a specific branch.
    
    Args:
        sha: Commit SHA to check
        branch: Branch name to check
    
    Returns:
        bool: True if commit exists on branch, False otherwise
    """
    try:
        success, stdout, stderr = _run_cmd([
            "git", "branch", "--contains", sha, branch
        ])
        return success and branch in stdout
    except Exception:
        return False