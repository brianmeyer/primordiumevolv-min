#!/usr/bin/env python3
"""
Patcher smoke test CLI - Exercise the edit-based patcher without LLM loop

Usage:
    python scripts/patcher_smoke.py --path app/config.py --match "X=1\n" --replace "X=2\n" --goal smoke --model dev/test
"""

import argparse
import json
import sys
import os
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(
        description="Smoke test the edit-based patcher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Simple parameter change
  python scripts/patcher_smoke.py --path app/config.py --match "X=1" --replace "X=2" --goal smoke --model dev/test

  # With newlines
  python scripts/patcher_smoke.py --path app/config.py --match "eps = 0.6\\n" --replace "eps = 0.7\\n" --goal tune --model test

  # Regex pattern
  python scripts/patcher_smoke.py --path app/config.py --match-re "eps\\s*=\\s*(\\d+\\.\\d+)" --replace-re "eps = \\g<1>5" --goal regex_test --model dev
        """
    )

    parser.add_argument("--path", required=True,
                       help="Relative path to file from repo root")
    parser.add_argument("--match",
                       help="Exact string to find and replace")
    parser.add_argument("--replace",
                       help="Replacement text")
    parser.add_argument("--match-re",
                       help="Regex pattern to find (use with --replace-re)")
    parser.add_argument("--replace-re",
                       help="Regex replacement with backrefs (use with --match-re)")
    parser.add_argument("--goal", required=True,
                       help="Goal tag for commit message")
    parser.add_argument("--model", required=True,
                       help="Model name for commit attribution")
    parser.add_argument("--area", default="test",
                       help="Area for the change (default: test)")
    parser.add_argument("--rationale", default="smoke test change",
                       help="Brief rationale for the change")

    args = parser.parse_args()

    # Validate arguments
    if args.match and args.match_re:
        print("Error: Cannot specify both --match and --match-re", file=sys.stderr)
        return 1

    if not args.match and not args.match_re:
        print("Error: Must specify either --match or --match-re", file=sys.stderr)
        return 1

    if args.match and not args.replace:
        print("Error: --match requires --replace", file=sys.stderr)
        return 1

    if args.match_re and not args.replace_re:
        print("Error: --match-re requires --replace-re", file=sys.stderr)
        return 1

    # Change to repo root if we're in scripts/
    if Path.cwd().name == "scripts":
        os.chdir("..")

    # Verify we're in repo root
    if not Path("app").exists():
        print("Error: Must run from repository root (app/ directory not found)", file=sys.stderr)
        return 1

    # Build edits package
    edit = {"path": args.path}

    if args.match:
        edit["match"] = args.match
        edit["replace"] = args.replace
    else:
        edit["match_re"] = args.match_re
        edit["group_replacement"] = args.replace_re

    edits_package = {
        "area": args.area,
        "goal_tag": args.goal,
        "rationale": args.rationale,
        "edits": [edit]
    }

    print("=== Patcher Smoke Test ===")
    print(f"File: {args.path}")
    print(f"Goal: {args.goal}")
    print(f"Model: {args.model}")

    if args.match:
        print(f"Match: {repr(args.match)}")
        print(f"Replace: {repr(args.replace)}")
    else:
        print(f"Match regex: {args.match_re}")
        print(f"Replace regex: {args.replace_re}")

    print(f"Package: {json.dumps(edits_package, indent=2)}")
    print()

    # Import and call patcher
    try:
        from app.dgm.patcher import apply_edits_package
    except ImportError as e:
        print(f"Error importing patcher: {e}", file=sys.stderr)
        print("Make sure you're in the repository root and the app module is available", file=sys.stderr)
        return 1

    # Apply the edit
    print("=== Applying Edit ===")
    try:
        result = apply_edits_package(
            json.dumps(edits_package),
            model_name=args.model,
            goal_tag=args.goal
        )

        # Print result
        print("=== Patcher Result ===")
        print(json.dumps(result, indent=2))

        # Return appropriate exit code
        if result.get("ok"):
            print("\n✓ Smoke test PASSED")
            return 0
        else:
            print(f"\n✗ Smoke test FAILED: {result.get('error', 'Unknown error')}")
            return 1

    except Exception as e:
        print(f"Error calling patcher: {e}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())