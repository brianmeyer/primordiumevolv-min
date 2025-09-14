"""
DGM Prompts - Centralized prompt templates and contracts for DGM system
"""

EDITS_CONTRACT_SYSTEM = """Return ONLY a JSON object with keys: area, goal_tag, rationale, edits.
Each edits[i] MUST include:
  - "path": relative file path from repository root
  - EITHER ("match" AND "replace") for exact string replacement
    OR ("match_re" AND "group_replacement") for regex replacement
Rules:
- No unified diffs, no patch headers, no base64, no code fences.
- No commentary outside the JSON object.
- Keep edits minimal and precise; first occurrence only.
- Do not include line numbers except optional 'line_number_hint'.
- Assume UTF-8, LF newlines, exactly one trailing newline per file."""


def make_edits_prompt(allowed_areas, max_loc, snapshots=None):
    """Create a prompt that instructs models to return edits package JSON"""

    if not snapshots or len(snapshots) == 0:
        return "ERROR: No file snapshot provided."

    file_path = snapshots[0]["path"]
    file_content = snapshots[0].get("content", "")

    if not file_content:
        return "ERROR: No file content provided."

    # Choose a random area from allowed areas
    import random

    area = random.choice(allowed_areas) if allowed_areas else "operators"

    # Show file context (first 50 lines)
    lines = file_content.split("\n")
    context_lines = lines[: min(50, len(lines))]
    context = "\n".join(f"{i+1:3d}: {line}" for i, line in enumerate(context_lines))

    prompt = f"""Modify {file_path} to improve the {area} area.

Current file content (first 50 lines):
{context}

Task: Make a small, focused improvement to the {area} configuration or implementation.

Return ONLY a JSON object with this exact structure:
{{
  "area": "{area}",
  "goal_tag": "improve_{area}",
  "rationale": "brief explanation of the change (max 15 words)",
  "edits": [
    {{
      "path": "{file_path}",
      "match": "exact text to find and replace",
      "replace": "new text to replace it with"
    }}
  ]
}}

Example for changing a parameter value:
{{
  "area": "bandit",
  "goal_tag": "improve_bandit",
  "rationale": "increase exploration rate for better operator discovery",
  "edits": [
    {{
      "path": "app/config.py",
      "match": "eps = 0.6",
      "replace": "eps = 0.7"
    }}
  ]
}}

Requirements:
- Make only ONE small change
- Use exact string matching ("match" and "replace")
- Ensure the change is valid for the {area} area
- Keep changes under {max_loc} lines
- No markdown, no code blocks, just the JSON object"""

    return prompt
