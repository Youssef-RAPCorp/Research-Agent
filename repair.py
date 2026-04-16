#!/usr/bin/env python3
"""
Physics Discovery System v3.0 — Import Repair Tool
===================================================
RAP Corp | Renaissance of American Physics

Scans every project .py file for "from X import Y" where Y is missing
from X, then injects class aliases or function stubs so imports don't fail.

Run from the project root:
    python repair.py

Safe to run multiple times — only appends what's missing.
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

# ── All .py files in the project tree ─────────────────────────────────────────
def all_project_py_files() -> list[Path]:
    files = []
    for pkg in PROJECT_PKGS:
        p = Path(pkg)
        if p.is_dir():
            files.extend(p.rglob("*.py"))
    files.append(Path("main.py"))
    return [f for f in files if f.exists()]


# ── Extract top-level defined names from a file ───────────────────────────────
def defined_names(path: Path) -> set[str]:
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return set()
    names: set[str] = set()
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


def add_alias(target: Path, name: str, existing_classes: list[str]):
    """Append an alias for *name* using the closest existing class."""
    src = target.read_text(encoding="utf-8", errors="replace")
    # Don't double-add
    if re.search(rf'^{re.escape(name)}\s*=', src, re.MULTILINE):
        return False
    if existing_classes:
        matches = difflib.get_close_matches(name, existing_classes, n=1, cutoff=0.3)
        alias_target = matches[0] if matches else existing_classes[0]
        addition = f"\n{name} = {alias_target}  # auto-alias by repair.py\n"
    else:
        addition = f"\nclass {name}:\n    \"\"\"Auto-stub by repair.py\"\"\"\n    pass\n"
    target.write_text(src + addition, encoding="utf-8")
    return True


def add_function_stub(target: Path, name: str):
    src = target.read_text(encoding="utf-8", errors="replace")
    if re.search(rf'^(?:def |class ){re.escape(name)}', src, re.MULTILINE):
        return False
    if name.endswith("Error") or name.endswith("Exception"):
        stub = f"\nclass {name}(Exception):\n    pass\n"
    else:
        stub = f"\ndef {name}(*args, **kwargs):\n    pass\n"
    target.write_text(src + stub, encoding="utf-8")
    return True


# ── Main scan ─────────────────────────────────────────────────────────────────
def run():
    print("\n  Physics Discovery System v3.0 — Import Repair Tool")
    print("  " + "─" * 50)

    scan_files = all_project_py_files()
    fixed_total = 0
    problems: list[str] = []

    for src_file in scan_files:
        try:
            src = src_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        # Collapse parenthesized multi-line imports to single lines
        src_flat = re.sub(
            r'from ([\w.]+) import \(([^)]+)\)',
            lambda m: f"from {m.group(1)} import {', '.join(m.group(2).split())}",
            src,
            flags=re.DOTALL,
        )

        for m in re.finditer(r'^from ([\w.]+) import ([\w ,]+)', src_flat, re.MULTILINE):
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
                problems.append(f"  MISSING FILE  : {target_path}  (imported by {src_file})")
                continue

            defs = defined_names(target)
            missing = [n for n in imported if n and n not in defs]
            if not missing:
                continue

            existing_classes = re.findall(
                r'^class (\w+)', target.read_text(encoding="utf-8", errors="replace"),
                re.MULTILINE,
            )

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
                    fixed_total += 1

    if problems:
        print()
        for p in problems:
            print(p)
        print()
        print("  NOTE: missing .py files above cannot be fixed by repair.py.")
        print("  Re-run python install.py to generate them.")

    print()
    if fixed_total:
        print(f"  {fixed_total} name(s) patched — try  python main.py  again.")
    else:
        print("  No missing exports detected. If main.py still fails, check logs/.")
    print()


if __name__ == "__main__":
    # Must run from project root
    project_dirs = {"agents", "config", "knowledge", "memory"}
    if not any(Path(d).is_dir() for d in project_dirs):
        print("ERROR: run repair.py from the project root directory")
        print("  e.g.:  cd C:\\path\\to\\physics_discovery_v3_installer")
        print("         python repair.py")
        sys.exit(1)
    run()
