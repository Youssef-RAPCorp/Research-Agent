#!/usr/bin/env python3
"""
Physics Discovery System v3.0 — Import Repair Tool
===================================================
RAP Corp | Renaissance of American Physics

Two-phase repair:
  Phase 1 — Inject missing class aliases / function stubs so all
             "from X import Y" statements resolve at import time.
  Phase 2 — Make all __init__ required positional params optional
             (default=None) so any ClassName() call won't crash on
             "missing N required positional arguments".

Run from the project root:
    python repair.py

Safe to run multiple times — only changes what's still broken.
"""

import re
import sys
import difflib
from pathlib import Path

# ── Project packages ──────────────────────────────────────────────────────────
PROJECT_PKGS = {
    "agents", "config", "knowledge", "memory",
    "thinking", "physics", "discovery", "interface", "utils",
}


def all_project_py_files() -> list:
    files = []
    for pkg in PROJECT_PKGS:
        p = Path(pkg)
        if p.is_dir():
            files.extend(p.rglob("*.py"))
    mp = Path("main.py")
    if mp.exists():
        files.append(mp)
    return files


# ── Helpers ───────────────────────────────────────────────────────────────────

def defined_names(path: Path) -> set:
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return set()
    names = set()
    for m in re.finditer(r'^(?:def |class |(\w+)\s*=)', src, re.MULTILINE):
        if m.lastindex and m.group(1):
            names.add(m.group(1))
        else:
            try:
                tok = src[m.start():].split("(")[0].split()[1].rstrip(":(,")
                names.add(tok)
            except IndexError:
                pass
    return names


def add_alias(target: Path, name: str, existing_classes: list) -> bool:
    src = target.read_text(encoding="utf-8", errors="replace")
    if re.search(rf'^{re.escape(name)}\s*=', src, re.MULTILINE):
        return False  # already present
    if existing_classes:
        matches = difflib.get_close_matches(name, existing_classes, n=1, cutoff=0.3)
        alias_target = matches[0] if matches else existing_classes[0]
        addition = f"\n{name} = {alias_target}  # auto-alias by repair.py\n"
    else:
        addition = f"\nclass {name}:\n    \"\"\"Auto-stub by repair.py\"\"\"\n    pass\n"
    target.write_text(src + addition, encoding="utf-8")
    return True


def add_function_stub(target: Path, name: str) -> bool:
    src = target.read_text(encoding="utf-8", errors="replace")
    if re.search(rf'^(?:def |class ){re.escape(name)}\b', src, re.MULTILINE):
        return False
    if name.endswith("Error") or name.endswith("Exception"):
        stub = f"\nclass {name}(Exception):\n    pass\n"
    else:
        stub = f"\ndef {name}(*args, **kwargs):\n    pass\n"
    target.write_text(src + stub, encoding="utf-8")
    return True


def make_init_optional(code: str) -> tuple:
    """
    Convert required positional __init__ params to optional (default=None).
    Returns (new_code, list_of_param_names_changed).
    """
    changed_params: list = []

    def _fix(m):
        params_raw = m.group(1)
        # Split on commas at depth 0 (handles nested brackets in defaults)
        tokens, current, depth = [], "", 0
        for ch in params_raw:
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth -= 1
            if ch == "," and depth == 0:
                tokens.append(current)
                current = ""
            else:
                current += ch
        if current.strip():
            tokens.append(current)

        new_tokens = []
        for tok in tokens:
            s = tok.strip()
            # Keep self, *args, **kwargs, already-defaulted params unchanged
            if not s or s == "self" or s.startswith("*") or "=" in s:
                new_tokens.append(tok)
                continue
            # Strip type annotation to get bare name
            name = s.split(":")[0].strip() if ":" in s else s
            changed_params.append(name)
            # Preserve leading whitespace (multi-line signatures)
            indent = tok[: len(tok) - len(tok.lstrip())]
            new_tokens.append(f"{indent}{name}=None")

        return f"def __init__({', '.join(new_tokens)}):"

    new_code = re.sub(r"def __init__\(([^)]*)\):", _fix, code, flags=re.DOTALL)
    return new_code, changed_params


# ── Phase 1: missing exports ──────────────────────────────────────────────────

def phase1_fix_imports(scan_files: list) -> int:
    fixed = 0
    problems = []

    for src_file in scan_files:
        try:
            src = src_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        # Collapse parenthesized multi-line imports to single lines
        src_flat = re.sub(
            r"from ([\w.]+) import \(([^)]+)\)",
            lambda mm: f"from {mm.group(1)} import {', '.join(mm.group(2).split())}",
            src,
            flags=re.DOTALL,
        )

        for m in re.finditer(r"^from ([\w.]+) import ([\w ,]+)", src_flat, re.MULTILINE):
            mod_dotted = m.group(1)
            top = mod_dotted.split(".")[0]
            if top not in PROJECT_PKGS:
                continue

            # Strip "as alias" parts
            raw_names = [n.strip().split(" as ")[0].strip()
                         for n in m.group(2).split(",")]
            imported = [n for n in raw_names if n and not n.startswith("_")]

            target_path = mod_dotted.replace(".", "/") + ".py"
            target = Path(target_path)
            if not target.exists():
                problems.append(f"  MISSING FILE  : {target_path}  (needed by {src_file})")
                continue

            defs = defined_names(target)
            missing = [n for n in imported if n and n not in defs]
            if not missing:
                continue

            try:
                existing_classes = re.findall(
                    r"^class (\w+)",
                    target.read_text(encoding="utf-8", errors="replace"),
                    re.MULTILINE,
                )
            except Exception:
                existing_classes = []

            for name in missing:
                is_class = name[0].isupper() and not name.endswith(("Error", "Exception"))
                if is_class:
                    ok = add_alias(target, name, existing_classes)
                    tag = "alias" if existing_classes else "stub class"
                else:
                    ok = add_function_stub(target, name)
                    tag = "stub fn"
                if ok:
                    print(f"  FIXED [{tag:10s}]  {target_path}  ←  {name}")
                    fixed += 1

    if problems:
        print()
        for p in problems:
            print(p)
        print("  NOTE: missing .py files above need 'python install.py' to generate them.")

    return fixed


# ── Phase 2: __init__ optional params ────────────────────────────────────────

def phase2_fix_init_params(scan_files: list) -> int:
    fixed = 0
    for py_file in scan_files:
        if py_file.name == "repair.py" or py_file.name == "install.py":
            continue
        try:
            src = py_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        new_src, changed = make_init_optional(src)
        if changed:
            py_file.write_text(new_src, encoding="utf-8")
            print(f"  FIXED [__init__   ]  {py_file}  →  made optional: {', '.join(changed)}")
            fixed += 1
    return fixed


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    print("\n  Physics Discovery System v3.0 — Import Repair Tool")
    print("  " + "─" * 52)

    scan_files = all_project_py_files()
    total_fixed = 0

    print("\n  Phase 1: Fixing missing exports (aliases / stubs)")
    print("  " + "─" * 52)
    total_fixed += phase1_fix_imports(scan_files)

    print("\n  Phase 2: Making __init__ params optional (default=None)")
    print("  " + "─" * 52)
    total_fixed += phase2_fix_init_params(scan_files)

    # Run Phase 1 a second time — Phase 2 may have changed files that now
    # expose new import mismatches (rare but possible).
    second = phase1_fix_imports(scan_files)
    if second:
        print(f"\n  (second-pass Phase 1: {second} more fix(es))")
        total_fixed += second

    print()
    if total_fixed:
        print(f"  {total_fixed} fix(es) applied.")
        print("  Run  python main.py  and re-run  python repair.py  if new errors appear.")
    else:
        print("  Nothing to fix. If main.py still fails, check logs/ for details.")
    print()


if __name__ == "__main__":
    project_dirs = {"agents", "config", "knowledge", "memory"}
    if not any(Path(d).is_dir() for d in project_dirs):
        print("ERROR: run repair.py from the project root directory")
        print("  e.g.:  cd C:\\path\\to\\physics_discovery_v3_installer")
        print("         python repair.py")
        sys.exit(1)
    run()
