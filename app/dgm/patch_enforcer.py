"""
Patch format enforcer to handle various model output formats and salvage malformed responses.
"""
import json
import re
import base64
from typing import Dict, List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)

DIFF_HEADER_RE = re.compile(r"^@@ -(\d+),(\d+) \+(\d+),(\d+) @@$")

class PatchFormatError(Exception):
    """Raised when a patch cannot be salvaged."""
    pass

def _json_loads_loose(raw: str) -> Dict:
    """
    Try to parse JSON, fixing common issues like unescaped newlines in diff strings.
    """
    # First try strict JSON
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        # Try to fix truncated JSON
        if "Unterminated string" in str(e) or "Expecting" in str(e):
            # Find the last complete element in diff_lines if present
            if '"diff_lines":[' in raw:
                # Find where diff_lines starts
                start_idx = raw.index('"diff_lines":[')
                array_start = start_idx + len('"diff_lines":[')
                
                # Find complete strings within the array
                lines = []
                i = array_start
                while i < len(raw):
                    if raw[i] == '"':
                        # Found start of string
                        j = i + 1
                        while j < len(raw):
                            if raw[j] == '"' and raw[j-1] != '\\':
                                # Found end of string
                                lines.append(raw[i:j+1])
                                i = j + 1
                                break
                            j += 1
                        else:
                            # String not terminated
                            break
                    elif raw[i] in ' ,\n\t':
                        i += 1
                    else:
                        break
                
                # Reconstruct with complete lines only
                if lines:
                    prefix = raw[:start_idx]
                    reconstructed = prefix + '"diff_lines":[' + ','.join(lines) + ']}'
                    try:
                        return json.loads(reconstructed)
                    except:
                        pass
        
        # Heuristic salvage: if there's a "diff":"...<raw newlines>..." block, re-escape newlines
        m = re.search(r'"diff"\s*:\s*"', raw)
        if not m:
            raise
        
        # Find the start of the diff value
        start = m.end()
        out, i, esc = [], start, False
        
        while i < len(raw):
            ch = raw[i]
            if esc:
                out.append(ch)
                esc = False
            else:
                if ch == '\\':
                    out.append(ch)
                    esc = True
                elif ch == '"':
                    # Check if this quote closes the string (not escaped)
                    bs = 0
                    j = i - 1
                    while j >= 0 and raw[j] == '\\':
                        bs += 1
                        j -= 1
                    if bs % 2 == 0:  # Even number of backslashes = not escaped
                        break
                    out.append(ch)
                elif ch == '\n':
                    # Replace literal newline with escaped version
                    out.append('\\n')
                elif ch == '\r':
                    # Skip carriage returns
                    pass
                elif ch == '\t':
                    # Replace literal tab with escaped version
                    out.append('\\t')
                else:
                    out.append(ch)
            i += 1
        
        # Reconstruct the JSON with fixed escaping
        fixed = raw[:start] + "".join(out) + raw[i:]
        return json.loads(fixed)

def _to_diff_lines(obj: Dict) -> List[str]:
    """
    Extract diff lines from various formats: diff_lines, diff_b64, or diff string.
    """
    # Preferred format: diff_lines array
    if "diff_lines" in obj and isinstance(obj["diff_lines"], list):
        return obj["diff_lines"]
    
    # Base64 encoded diff
    if "diff_b64" in obj and isinstance(obj["diff_b64"], str):
        try:
            decoded = base64.b64decode(obj["diff_b64"]).decode("utf-8")
            return decoded.splitlines()
        except Exception as e:
            logger.warning(f"Failed to decode diff_b64: {e}")
    
    # Legacy string format
    if "diff" in obj and isinstance(obj["diff"], str):
        text = obj["diff"]
        # Clean up common issues
        text = text.replace("\r\n", "\n")  # Normalize line endings
        text = text.replace('\\"', '"')    # Unescape quotes
        # Split into lines
        lines = text.split("\n")
        # Remove empty trailing lines but keep one if the diff ended with newline
        while len(lines) > 1 and lines[-1] == "":
            lines.pop()
        return lines
    
    raise PatchFormatError("No diff payload found (expected diff_lines, diff_b64, or diff)")

def _validate_headers(lines: List[str], path: str):
    """
    Validate that diff headers are correct.
    """
    if len(lines) < 3:
        raise PatchFormatError(f"Diff too short: only {len(lines)} lines")
    
    expected_minus = f"--- a/{path}"
    expected_plus = f"+++ b/{path}"
    
    # Allow some flexibility in headers (model might have spaces or different prefixes)
    if not (lines[0].endswith(path) and "---" in lines[0]):
        raise PatchFormatError(f"Bad '---' header: expected '{expected_minus}', got '{lines[0]}'")
    
    if not (lines[1].endswith(path) and "+++" in lines[1]):
        raise PatchFormatError(f"Bad '+++' header: expected '{expected_plus}', got '{lines[1]}'")
    
    if not DIFF_HEADER_RE.match(lines[2]):
        # Try to be lenient with hunk header
        if not lines[2].startswith("@@"):
            raise PatchFormatError(f"Bad @@ hunk header: '{lines[2]}'")

def _ensure_final_newline(lines: List[str]) -> List[str]:
    """
    Ensure the diff ends with an empty line for proper formatting.
    """
    if lines and lines[-1] != "":
        return lines + [""]
    return lines

def _count_changes(lines: List[str]) -> Tuple[int, int]:
    """
    Count the number of addition and deletion lines in the diff.
    """
    minus = sum(1 for l in lines[3:] if l.startswith("-") and not l.startswith("---"))
    plus = sum(1 for l in lines[3:] if l.startswith("+") and not l.startswith("+++"))
    return minus, plus

def _fix_headers(lines: List[str], file_path: str) -> List[str]:
    """
    Fix malformed headers to match expected format.
    """
    if len(lines) < 3:
        return lines
    
    # Fix --- header
    if not lines[0].startswith("--- a/"):
        if "---" in lines[0] and file_path in lines[0]:
            lines[0] = f"--- a/{file_path}"
    
    # Fix +++ header
    if not lines[1].startswith("+++ b/"):
        if "+++" in lines[1] and file_path in lines[1]:
            lines[1] = f"+++ b/{file_path}"
    
    return lines

def _reanchor_hunk(lines: List[str], file_text: str) -> List[str]:
    """
    Recompute @@ -old,count +new,count @@ using the actual file context.
    """
    if len(lines) < 4:
        return lines
    
    body = lines[3:]
    
    # Extract context lines (lines starting with space)
    ctx = []
    for l in body:
        if l.startswith(" "):
            ctx.append(l[1:])  # Remove leading space
    
    if len(ctx) < 2:
        # Not enough context to reanchor
        return lines
    
    # Split file into lines
    file_lines = file_text.splitlines()
    
    # Find where the context matches in the file
    anchor_idx = None
    for i in range(len(file_lines) - len(ctx) + 1):
        if file_lines[i:i+len(ctx[:2])] == ctx[:2]:
            anchor_idx = i
            break
    
    if anchor_idx is None:
        # Could not find context in file
        return lines
    
    # Count old and new line counts
    old_count = sum(1 for l in body if l.startswith((" ", "-")))
    new_count = sum(1 for l in body if l.startswith((" ", "+")))
    
    # Generate new hunk header
    new_header = f"@@ -{anchor_idx+1},{old_count} +{anchor_idx+1},{new_count} @@"
    
    return [lines[0], lines[1], new_header] + body

def enforce_and_sanitize(raw_response: str, file_path: str, file_text: str = "") -> List[str]:
    """
    Accepts any of: diff_lines | diff_b64 | diff (string).
    Returns sanitized diff_lines ready for git apply.
    
    Args:
        raw_response: Raw JSON response from model
        file_path: Path to the file being patched
        file_text: Original file content for context matching
        
    Returns:
        List of diff lines ready for git apply
        
    Raises:
        PatchFormatError: If the patch cannot be salvaged
    """
    try:
        # Parse JSON with loose parsing to handle unescaped newlines
        obj = _json_loads_loose(raw_response)
    except Exception as e:
        raise PatchFormatError(f"Failed to parse JSON: {e}")
    
    # Extract diff lines from whatever format was used
    try:
        lines = _to_diff_lines(obj)
    except Exception as e:
        raise PatchFormatError(f"Failed to extract diff lines: {e}")
    
    # Trim accidental leading/trailing blank lines
    while lines and lines[0] == "":
        lines.pop(0)
    
    # Fix headers if needed
    lines = _fix_headers(lines, file_path)
    
    # Validate headers
    try:
        _validate_headers(lines, file_path)
    except PatchFormatError:
        # Try to fix and revalidate
        if file_text:
            lines = _reanchor_hunk(lines, file_text)
            _validate_headers(lines, file_path)
        else:
            raise
    
    # Fix over-escaped quotes in diff body (but not in headers)
    for i in range(3, len(lines)):
        lines[i] = lines[i].replace('\\"', '"')
    
    # Validate change counts (must have exactly one '-' and one '+')
    minus, plus = _count_changes(lines)
    if minus != 1 or plus != 1:
        logger.warning(f"Expected exactly one '-' and one '+', got -:{minus} +:{plus}")
        # Don't fail here, the repair_diff_on_apply_fail might fix it
    
    # Ensure final newline
    lines = _ensure_final_newline(lines)
    
    return lines