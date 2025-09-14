"""
DGM Patcher - Edit-based patching system for models to apply code changes

This module provides functionality for models to apply structured edits to files
instead of generating unified diffs directly. It handles exact string matching,
regex-based replacements, diff synthesis, and git integration.
"""

import json
import re
import subprocess
import tempfile
import hashlib
from typing import Dict, Any, Tuple
import difflib
import os


def _normalize_text(text: str) -> str:
    """
    Normalize text to LF line endings and ensure single trailing newline.

    Args:
        text: Input text

    Returns:
        Normalized text
    """
    # Convert CRLF and CR to LF
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Ensure single trailing newline
    text = text.rstrip("\n") + "\n"

    return text


def _read_text_norm(path: str) -> str:
    """
    Read text file with UTF-8 encoding and normalization.

    Args:
        path: File path to read

    Returns:
        Normalized text content
    """
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    return _normalize_text(content)


def _write_text_norm(path: str, content: str) -> None:
    """
    Write text file with UTF-8 encoding and normalization.

    Args:
        path: File path to write
        content: Text content to write
    """
    normalized = _normalize_text(content)
    with open(path, "w", encoding="utf-8") as f:
        f.write(normalized)


def _get_file_sha(path: str) -> str:
    """
    Get git blob SHA for a file.

    Args:
        path: File path

    Returns:
        40-character hex SHA, or "0"*40 if file doesn't exist
    """
    if not os.path.exists(path):
        return "0" * 40

    try:
        result = subprocess.run(
            ["git", "hash-object", path], capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        # Fallback to manual hash calculation
        content = _read_text_norm(path)
        blob_content = f"blob {len(content.encode('utf-8'))}\0{content}"
        return hashlib.sha1(blob_content.encode("utf-8")).hexdigest()


def _write_temp_patch(diff_text: str) -> str:
    """
    Write diff content to a temporary patch file.

    Args:
        diff_text: Unified diff content

    Returns:
        Path to temporary patch file
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".patch", delete=False) as f:
        f.write(diff_text)
        return f.name


def apply_one_edit(content: str, edit: Dict[str, Any]) -> str:
    """
    Apply a single edit to content.

    Args:
        content: Original file content
        edit: Edit specification with 'match'/'match_re' and 'replace'/'group_replacement'

    Returns:
        Modified content

    Raises:
        ValueError: If match not found or edit specification invalid
    """
    if "match" in edit:
        # Exact string matching
        match_str = edit["match"]
        replace_str = edit["replace"]

        if match_str not in content:
            raise ValueError(f"Exact match not found: {repr(match_str)}")

        # Replace first occurrence only
        return content.replace(match_str, replace_str, 1)

    elif "match_re" in edit:
        # Regex matching
        pattern = edit["match_re"]
        replacement = edit["group_replacement"]

        # Use MULTILINE flag for regex
        regex = re.compile(pattern, re.MULTILINE)
        match = regex.search(content)

        if not match:
            raise ValueError(f"Regex pattern not found: {pattern}")

        # Replace first match only
        return regex.sub(replacement, content, count=1)

    else:
        raise ValueError("Edit must contain either 'match' or 'match_re'")


def synth_unified_diff(path: str, before: str, after: str, context: int = 3) -> str:
    """
    Generate a unified diff between before and after content.

    Args:
        path: File path for diff headers
        before: Original content
        after: Modified content
        context: Number of context lines

    Returns:
        Unified diff string with trailing newline
    """
    before_lines = before.splitlines(keepends=True)
    after_lines = after.splitlines(keepends=True)

    diff_lines = list(
        difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            n=context,
        )
    )

    diff_text = "".join(diff_lines)

    # Ensure diff ends with newline
    if diff_text and not diff_text.endswith("\n"):
        diff_text += "\n"

    return diff_text


def git_apply_check(diff_text: str) -> Tuple[bool, str]:
    """
    Check if a diff can be applied using git apply.

    Args:
        diff_text: Unified diff content

    Returns:
        (success, error_message)
    """
    try:
        # Write diff to temporary file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".patch", delete=False) as f:
            f.write(diff_text)
            temp_path = f.name

        try:
            # Run git apply --check --whitespace=nowarn
            result = subprocess.run(
                ["git", "apply", "--check", "--whitespace=nowarn", temp_path],
                capture_output=True,
                text=True,
            )

            success = result.returncode == 0
            error_msg = result.stderr.strip() if not success else ""

            return success, error_msg

        finally:
            # Clean up temp file
            os.unlink(temp_path)

    except Exception as e:
        return False, f"git apply check failed: {str(e)}"


def commit_path(path: str, message: str) -> None:
    """
    Stage and commit a single file path.

    Args:
        path: File path to commit
        message: Commit message

    Raises:
        subprocess.CalledProcessError: If git commands fail
    """
    # Stage the file
    subprocess.run(["git", "add", path], check=True)

    # Commit with message
    subprocess.run(["git", "commit", "-m", message], check=True)


def apply_edits_package(
    edits_pkg_json: str, model_name: str, goal_tag: str
) -> Dict[str, Any]:
    """
    Apply a package of edits to multiple files.

    Args:
        edits_pkg_json: JSON string containing edit package
        model_name: Name of the model applying edits
        goal_tag: Goal tag for commit message

    Returns:
        Result dictionary with success status and details
    """
    try:
        # Parse the edit package
        pkg = json.loads(edits_pkg_json)

        # Validate required fields
        required_fields = ["area", "goal_tag", "rationale", "edits"]
        for field in required_fields:
            if field not in pkg:
                return {"ok": False, "error": f"Missing required field: {field}"}

        edits = pkg["edits"]
        if not isinstance(edits, list):
            return {"ok": False, "error": "edits must be a list"}

        # Track results
        touched_files = []
        all_diffs = []
        file_shas = []
        fallback_occurred = False

        # Apply each edit
        for i, edit in enumerate(edits):
            try:
                # Validate edit structure
                if "path" not in edit:
                    return {"ok": False, "error": f"Edit {i}: missing 'path' field"}

                if "replace" not in edit and "group_replacement" not in edit:
                    return {
                        "ok": False,
                        "error": f"Edit {i}: missing 'replace' or 'group_replacement' field",
                    }

                if "match" not in edit and "match_re" not in edit:
                    return {
                        "ok": False,
                        "error": f"Edit {i}: must have 'match' or 'match_re'",
                    }

                path = edit["path"]

                # Record before SHA
                before_sha = _get_file_sha(path)

                # Read current content
                if os.path.exists(path):
                    before_content = _read_text_norm(path)
                else:
                    before_content = ""

                # Apply edit
                try:
                    after_content = apply_one_edit(before_content, edit)
                except ValueError as e:
                    return {
                        "ok": False,
                        "error": f"Edit {i} failed: {str(e)}",
                        "path": path,
                    }

                # Generate diff
                diff_text = synth_unified_diff(path, before_content, after_content)
                all_diffs.append(diff_text)

                # Try git apply first
                can_apply, apply_error = git_apply_check(diff_text)

                if can_apply:
                    # Use git apply
                    patch_path = _write_temp_patch(diff_text)
                    try:
                        subprocess.run(
                            ["git", "apply", "--whitespace=nowarn", patch_path],
                            check=True,
                            text=True,
                            capture_output=True,
                        )
                    finally:
                        os.unlink(patch_path)
                else:
                    # Fallback to direct write
                    fallback_occurred = True
                    # Ensure directory exists (only if path has a directory component)
                    dir_path = os.path.dirname(path)
                    if dir_path:
                        os.makedirs(dir_path, exist_ok=True)
                    _write_text_norm(path, after_content)

                # Record after SHA and track file
                after_sha = _get_file_sha(path)
                file_shas.append(
                    {"path": path, "before": before_sha, "after": after_sha}
                )
                if path not in touched_files:
                    touched_files.append(path)

            except Exception as e:
                return {
                    "ok": False,
                    "error": f"Edit {i} failed: {str(e)}",
                    "path": edit.get("path", "unknown"),
                }

        # Stage all touched files and make single commit
        if touched_files:
            subprocess.run(["git", "add", "--"] + touched_files, check=True)

            # Build commit message
            if fallback_occurred:
                commit_msg = (
                    f"meta({goal_tag}): direct write by {model_name} (fallback)"
                )
            else:
                commit_msg = f"meta({goal_tag}): apply by {model_name}"

            subprocess.run(["git", "commit", "-m", commit_msg], check=True)

        return {
            "ok": True,
            "touched": touched_files,
            "diffs": all_diffs,
            "file_shas": file_shas,
        }

    except json.JSONDecodeError as e:
        return {"ok": False, "error": f"Invalid JSON: {str(e)}"}
    except subprocess.CalledProcessError as e:
        return {"ok": False, "error": f"Git command failed: {str(e)}"}
    except Exception as e:
        return {"ok": False, "error": f"Unexpected error: {str(e)}"}
