#!/usr/bin/env python3
"""
E2E Single Edit Test - Run one end-to-end edit cycle for testing

Usage:
    python scripts/e2e_single_edit.py --path app/config.py --match "X=1\n" --replace "X=2\n" --goal smoke --model dev/test --run-id 0001
"""

import argparse
import json
import sys
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="Run a single end-to-end edit cycle",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic edit test
  python scripts/e2e_single_edit.py --path app/config.py --match "X=1\\n" --replace "X=2\\n" --goal smoke --model dev/test --run-id 0001

  # Config parameter change
  python scripts/e2e_single_edit.py --path app/config.py --match "eps = 0.6" --replace "eps = 0.7" --goal tune_epsilon --model llama3.1 --run-id E2E001

  # Multi-line edit
  python scripts/e2e_single_edit.py --path app/config.py --match "DEBUG = False\\nLOG_LEVEL = \\"INFO\\"" --replace "DEBUG = True\\nLOG_LEVEL = \\"DEBUG\\"" --goal debug_mode --model gpt-4 --run-id DEBUG01
        """,
    )

    parser.add_argument(
        "--path", required=True, help="Relative path to file from repo root"
    )
    parser.add_argument(
        "--match", required=True, help="Exact string to find and replace"
    )
    parser.add_argument("--replace", required=True, help="Replacement text")
    parser.add_argument(
        "--goal", required=True, help="Goal tag for commit message and analytics"
    )
    parser.add_argument(
        "--model", required=True, help="Model name for commit attribution and analytics"
    )
    parser.add_argument(
        "--run-id", required=True, help="Unique run identifier for analytics"
    )
    parser.add_argument(
        "--area", default="test", help="Area for the change (default: test)"
    )
    parser.add_argument(
        "--rationale",
        default="end-to-end test change",
        help="Brief rationale for the change",
    )

    args = parser.parse_args()

    # Change to repo root if we're in scripts/
    if Path.cwd().name == "scripts":
        os.chdir("..")

    # Verify we're in repo root
    if not Path("app").exists():
        print(
            "Error: Must run from repository root (app/ directory not found)",
            file=sys.stderr,
        )
        return 1

    # Normalize path - if it starts with ../ and we changed directories, remove the ../
    target_path = args.path
    if target_path.startswith("../") and Path.cwd().name != "scripts":
        target_path = target_path[3:]

    # Process escape sequences in match/replace strings
    # Handle \\n -> \n and \\t -> \t, but preserve \\\\ -> \\
    match_str = (
        args.match.replace("\\\\", "\x00")
        .replace("\\n", "\n")
        .replace("\\t", "\t")
        .replace("\x00", "\\")
    )
    replace_str = (
        args.replace.replace("\\\\", "\x00")
        .replace("\\n", "\n")
        .replace("\\t", "\t")
        .replace("\x00", "\\")
    )

    # Build edits package
    edits_package = {
        "area": args.area,
        "goal_tag": args.goal,
        "rationale": args.rationale,
        "edits": [{"path": target_path, "match": match_str, "replace": replace_str}],
    }

    print("=== E2E Single Edit Test ===")
    print(f"Run ID: {args.run_id}")
    print(f"File: {target_path}")
    print(f"Goal: {args.goal}")
    print(f"Model: {args.model}")
    print(f"Match: {repr(match_str)}")
    print(f"Replace: {repr(replace_str)}")
    print(f"Package: {json.dumps(edits_package, indent=2)}")
    print()

    # Import required modules
    try:
        # Add current directory to Python path if needed
        current_dir = os.getcwd()
        if current_dir not in sys.path:
            sys.path.insert(0, current_dir)

        from app.dgm.patcher import apply_edits_package
        from app.dgm.analytics import record_edits_apply
    except ImportError as e:
        print(f"Error importing modules: {e}", file=sys.stderr)
        print(
            "Make sure you're in the repository root and the app module is available",
            file=sys.stderr,
        )
        return 1

    # Apply the edit
    print("=== Applying Edit ===")
    try:
        result = apply_edits_package(
            json.dumps(edits_package), model_name=args.model, goal_tag=args.goal
        )

        # Record analytics
        print("=== Recording Analytics ===")
        record_edits_apply(args.run_id, result)

        # Print result
        print("=== Patcher Result ===")
        print(json.dumps(result, indent=2))

        # Print analytics summary
        if result.get("ok"):
            print("\n=== E2E Success Summary ===")
            print(f"✓ Applied {len(result.get('diffs', []))} edits")
            print(
                f"✓ Modified {len(result.get('touched', []))} files: {result.get('touched', [])}"
            )
            print(f"✓ File SHAs recorded: {len(result.get('file_shas', []))} entries")
            print(f"✓ Analytics recorded for run: {args.run_id}")
            return 0
        else:
            print(f"\n✗ E2E test FAILED: {result.get('error', 'Unknown error')}")
            return 1

    except Exception as e:
        print(f"Error during E2E test: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
