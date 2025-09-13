"""
Dead code sweep for Python modules under app/ with call-site tracking.

What it does
- Builds a module graph from AST imports across app/ and tests/.
- Resolves "from app import X" and "from app.pkg import Y" to fully-qualified modules.
- Tracks symbol definitions (funcs/classes) and call sites (file:line) per symbol.
- Treats FastAPI route handlers (decorated by app.get/post/...) as used.

Output
- Markdown to stdout by default.
- --json writes a JSON report with modules, symbols, and call_sites.
- --md writes Markdown to a file.
"""

from __future__ import annotations

import ast
import os
import sys
from collections import defaultdict
import argparse
import json as _json
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP_ROOT = os.path.join(ROOT, "app")
TEST_ROOTS = [ROOT, os.path.join(ROOT, "tests")]


@dataclass
class ModuleInfo:
    path: str
    name: str
    imports: Set[str] = field(default_factory=set)
    imported_by: Set[str] = field(default_factory=set)
    defined_funcs: Set[str] = field(default_factory=set)
    defined_classes: Set[str] = field(default_factory=set)
    used_symbols: Set[str] = field(default_factory=set)  # names used directly
    symbol_call_sites: Dict[str, List[Tuple[str, int]]] = field(default_factory=lambda: defaultdict(list))
    alias_to_mod: Dict[str, str] = field(default_factory=dict)
    fastapi_routes: Set[str] = field(default_factory=set)


def discover_modules() -> Dict[str, ModuleInfo]:
    mods: Dict[str, ModuleInfo] = {}
    for dirpath, _, files in os.walk(APP_ROOT):
        for f in files:
            if not f.endswith(".py"):
                continue
            path = os.path.join(dirpath, f)
            mod = os.path.relpath(path, APP_ROOT)[:-3].replace(os.sep, ".")
            if mod.endswith(".__init__"):
                mod = mod[: -len(".__init__")]
            fq = f"app.{mod}" if mod else "app"
            mods[fq] = ModuleInfo(path=path, name=fq)
    return mods


def parse_file(path: str) -> ast.AST | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return ast.parse(f.read(), filename=path)
    except Exception:
        return None


def collect_ast_info(mods: Dict[str, ModuleInfo]) -> None:
    # Build reverse map path->mod
    path_to_mod = {mi.path: name for name, mi in mods.items()}

    # Analyze app/ and tests/
    scan_paths: List[str] = []
    for base in [APP_ROOT] + TEST_ROOTS:
        if os.path.isdir(base):
            for dirpath, _, files in os.walk(base):
                for f in files:
                    if f.endswith(".py"):
                        scan_paths.append(os.path.join(dirpath, f))

    # Map usage by module
    for path in scan_paths:
        tree = parse_file(path)
        if tree is None:
            continue
        # Determine current module fq name if within app/
        cur_mod = path_to_mod.get(path)
        # Track imported aliases in this file
        alias_to_mod: Dict[str, str] = {}
        from_imports: Dict[str, Set[str]] = defaultdict(set)  # mod -> names
        imported_modules: Set[str] = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module and (node.module.startswith("app." ) or node.module == "app"):
                    base_mod = node.module
                    for n in node.names:
                        if n.name == "*":
                            continue
                        alias = n.asname or n.name
                        # Expand shorthand like: from app import code_loop -> app.code_loop
                        # and from app.dgm import proposer -> app.dgm.proposer
                        full_mod = base_mod
                        if base_mod == "app":
                            candidate = f"app.{n.name}"
                            if candidate in mods:
                                full_mod = candidate
                        elif base_mod.startswith("app."):
                            candidate = f"{base_mod}.{n.name}"
                            if candidate in mods:
                                full_mod = candidate
                        from_imports[full_mod].add(alias)
                        # Treat imported name as a module alias if it resolves to a module
                        alias_to_mod[alias] = full_mod
                        imported_modules.add(full_mod)
            elif isinstance(node, ast.Import):
                for n in node.names:
                    if n.name.startswith("app.") or n.name == "app":
                        alias_to_mod[n.asname or n.name] = n.name
                        imported_modules.add(n.name)

        # Symbol usage in this file
        used_names: Set[str] = set()
        used_attrs: Dict[str, Set[str]] = defaultdict(set)  # alias -> attrs used
        used_name_sites: Dict[str, List[int]] = defaultdict(list)
        used_attr_sites: Dict[Tuple[str, str], List[int]] = defaultdict(list)  # (alias, attr) -> lines
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                used_names.add(node.id)
                used_name_sites[node.id].append(getattr(node, "lineno", 0))
            elif isinstance(node, ast.Attribute):
                if isinstance(node.value, ast.Name):
                    used_attrs[node.value.id].add(node.attr)
                    used_attr_sites[(node.value.id, node.attr)].append(getattr(node, "lineno", 0))

        # Record into ModuleInfo structures
        for mname in imported_modules:
            if mname in mods:
                mods[mname].imported_by.add(cur_mod or os.path.relpath(path, ROOT))
        if cur_mod and cur_mod in mods:
            mi = mods[cur_mod]
            mi.imports |= imported_modules
            mi.alias_to_mod = alias_to_mod
            # Defined symbols + FastAPI route detection
            for node in tree.body:
                if isinstance(node, ast.FunctionDef):
                    mi.defined_funcs.add(node.name)
                    # route detection: any decorator with .get/.post/.put/.delete on name 'app'
                    for dec in node.decorator_list:
                        if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                            if isinstance(dec.func.value, ast.Name) and dec.func.value.id == "app":
                                if dec.func.attr in {"get", "post", "put", "delete", "patch"}:
                                    mi.fastapi_routes.add(node.name)
                        elif isinstance(dec, ast.Attribute):
                            if isinstance(dec.value, ast.Name) and dec.value.id == "app":
                                if dec.attr in {"get", "post", "put", "delete", "patch"}:
                                    mi.fastapi_routes.add(node.name)
                elif isinstance(node, ast.ClassDef):
                    mi.defined_classes.add(node.name)

        # Symbol usage mapping for direct from-imports (apply regardless of cur_mod)
        for modname, names in from_imports.items():
            for alias in names:
                if alias in used_names:
                    if modname in mods:
                        mods[modname].used_symbols.add(alias)
                        # Record call sites for this symbol
                        for ln in used_name_sites.get(alias, []):
                            mods[modname].symbol_call_sites[alias].append((os.path.relpath(path, ROOT), ln))
        # Symbol usage mapping for module alias usage (alias.attr)
        for alias, modname in alias_to_mod.items():
            attrs = used_attrs.get(alias, set())
            if modname in mods:
                for a in attrs:
                    mods[modname].used_symbols.add(a)
                    for ln in used_attr_sites.get((alias, a), []):
                        mods[modname].symbol_call_sites[a].append((os.path.relpath(path, ROOT), ln))


def classify(mods: Dict[str, ModuleInfo]) -> Tuple[List[str], List[str], Dict[str, List[str]], Dict[str, Dict[str, List[Tuple[str, int]]]], List[str]]:
    # Whitelist entrypoint-like modules (used indirectly)
    entry_whitelist = {
        "app.main",  # uvicorn entry
        "app.server.sse",  # runtime SSE
        "app.utils.__init__",
        "app.server.__init__",
    }
    unused_modules: List[str] = []
    weak_modules: List[str] = []
    unused_symbols: Dict[str, List[str]] = {}
    symbol_sites: Dict[str, Dict[str, List[Tuple[str, int]]]] = {}
    test_only: List[str] = []

    for name, mi in mods.items():
        if name in entry_whitelist:
            continue
        # module never imported by other modules/tests
        if not mi.imported_by:
            # If module defines FastAPI routes, keep
            if mi.fastapi_routes:
                weak_modules.append(name)
            else:
                unused_modules.append(name)
            continue
        # Classify test-only usage
        non_test_users = [u for u in mi.imported_by if not (str(u).startswith("tests/") or str(u).startswith("test") or "/test_" in str(u))]
        if not non_test_users:
            test_only.append(name)
        # Module imported, but check if defined symbols are referenced
        defined = mi.defined_funcs | mi.defined_classes
        # Consider FastAPI route functions as used
        defined -= mi.fastapi_routes
        missing = sorted(s for s in defined if s not in mi.used_symbols)
        if missing:
            unused_symbols[name] = missing
        # Capture sites for used symbols
        if mi.symbol_call_sites:
            symbol_sites[name] = {k: v for k, v in mi.symbol_call_sites.items()}
    return unused_modules, weak_modules, unused_symbols, symbol_sites, test_only


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", dest="json_out", help="Write JSON report to path")
    ap.add_argument("--md", dest="md_out", help="Write Markdown report to path")
    args = ap.parse_args()
    mods = discover_modules()
    collect_ast_info(mods)
    unused_modules, weak_modules, unused_symbols, symbol_sites, test_only = classify(mods)

    report_md = []
    report_md.append("# Dead Code Sweep Report\n")
    report_md.append("## Potentially Unused Modules (no imports found)")
    if not unused_modules:
        report_md.append("- None")
    else:
        for m in sorted(unused_modules):
            report_md.append(f"- {m} ({mods[m].path})")
    report_md.append("\n## Modules Imported Only In Tests")
    if not test_only:
        report_md.append("- None")
    else:
        for m in sorted(test_only):
            report_md.append(f"- {m}")
    report_md.append("\n## Modules with Weak Signals (indirect use or only routes)")
    if not weak_modules:
        report_md.append("- None")
    else:
        for m in sorted(weak_modules):
            report_md.append(f"- {m} ({mods[m].path})")
    report_md.append("\n## Potentially Unused Symbols (module imported but symbols not referenced)")
    if not unused_symbols:
        report_md.append("- None")
    else:
        for m, syms in sorted(unused_symbols.items()):
            report_md.append(f"- {m}:")
            for s in syms[:100]:
                report_md.append(f"  - {s}")
            if len(syms) > 100:
                report_md.append(f"  ... and {len(syms)-100} more")
    report_md.append("\n## Symbol Call Sites (for referenced symbols)")
    if not symbol_sites:
        report_md.append("- None")
    else:
        # Limit to a few per module to keep readable
        for m in sorted(symbol_sites.keys()):
            report_md.append(f"- {m}:")
            items = list(symbol_sites[m].items())[:20]
            for sym, sites in items:
                sample = ", ".join([f"{f}:{ln}" for f, ln in sites[:5]])
                report_md.append(f"  - {sym}: {sample}")
    report_md.append("\n## Notes")
    report_md.append("- This is heuristic. Double-check before deletion.")
    report_md.append("- FastAPI routes are treated as used regardless of references.")
    report_md.append("- Test-only imports are considered valid usage.")

    # Print MD to stdout unless --md is specified
    md_text = "\n".join(report_md)
    if not args.md_out:
        print(md_text)
    else:
        with open(args.md_out, "w", encoding="utf-8") as f:
            f.write(md_text)

    if args.json_out:
        obj = {
            "unused_modules": sorted(unused_modules),
            "test_only_modules": sorted(test_only),
            "weak_modules": sorted(weak_modules),
            "unused_symbols": {k: v for k, v in sorted(unused_symbols.items())},
            "symbol_call_sites": symbol_sites,
        }
        with open(args.json_out, "w", encoding="utf-8") as f:
            _json.dump(obj, f, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
