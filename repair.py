#!/usr/bin/env python3
"""
Physics Discovery System v3.0 — Import Repair Tool
===================================================
RAP Corp | Renaissance of American Physics

Three-phase repair — run from the project root:
    python repair.py

  Phase 1 — Remove function stubs that shadow real class definitions.
             e.g. def ArXivSearchAgent(*args, **kwargs): raise NotImplementedError
             that appears after class ArXivSearchAgent in the same file.

  Phase 2 — Inject missing class aliases / function stubs so all
             "from X import Y" statements resolve at import time.

  Phase 3 — Make all __init__ required positional params optional
             (default=None) so ClassName() calls don't crash.

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
    names: set = set()
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
        return False
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
    """Convert required positional __init__ params to optional (default=None)."""
    changed_params: list = []

    def _fix(m):
        params_raw = m.group(1)
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
            if not s or s == "self" or s.startswith("*") or "=" in s:
                new_tokens.append(tok)
                continue
            name = s.split(":")[0].strip() if ":" in s else s
            changed_params.append(name)
            indent = tok[: len(tok) - len(tok.lstrip())]
            new_tokens.append(f"{indent}{name}=None")

        return f"def __init__({', '.join(new_tokens)}):"

    new_code = re.sub(r"def __init__\(([^)]*)\):", _fix, code, flags=re.DOTALL)
    return new_code, changed_params


# ── Phase 1: Remove shadowing stubs ──────────────────────────────────────────

def phase1_remove_shadowing_stubs(scan_files: list) -> int:
    """
    Remove function/lambda stubs that shadow real class definitions.

    Two known patterns injected by older installer versions:
      def ClassName(*args, **kwargs):
          raise NotImplementedError('ClassName not yet implemented')

      def ClassName(*args, **kwargs):
          pass

    These appear AFTER the real class definition and overwrite the class
    name in the module namespace when Python executes the file.
    """
    fixed = 0
    for py_file in scan_files:
        if py_file.name in ("repair.py", "install.py"):
            continue
        try:
            src = py_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        real_classes = set(re.findall(r'^class (\w+)', src, re.MULTILINE))
        if not real_classes:
            continue

        # Match the stub function only when it appears AFTER the real class.
        # The body is a single-line raise or pass (both patterns used historically).
        pat = (
            r'\n+def ('
            + '|'.join(re.escape(c) for c in real_classes)
            + r')\([^)]*\):\s*\n[ \t]+(?:raise NotImplementedError\([^)]*\)|pass)\s*\n?'
        )
        new_src = re.sub(pat, '', src)

        if new_src != src:
            # Identify which stub names were removed
            before = set(re.findall(
                r'def (' + '|'.join(re.escape(c) for c in real_classes) + r')\(',
                src,
            ))
            after = set(re.findall(
                r'def (' + '|'.join(re.escape(c) for c in real_classes) + r')\(',
                new_src,
            ))
            removed = before - after
            py_file.write_text(new_src, encoding="utf-8")
            print(f"  FIXED [shadow stub]  {py_file}  →  removed def(s): {', '.join(sorted(removed))}")
            fixed += 1

    return fixed


# ── Phase 1b: Break circular imports ─────────────────────────────────────────

def _build_import_graph(scan_files: list) -> dict:
    """Return {module: {imported_module: [names]}} for all project .py files."""
    module_imports: dict = {}
    for py_file in scan_files:
        if not py_file.exists() or py_file.name in ("repair.py", "install.py", "__init__.py"):
            continue
        pkg = py_file.parent.name
        if pkg not in PROJECT_PKGS:
            continue
        module = f"{pkg}.{py_file.stem}"
        try:
            src = py_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        flat = re.sub(
            r"from ([\w.]+) import \(([^)]+)\)",
            lambda m: f"from {m.group(1)} import {', '.join(m.group(2).split())}",
            src, flags=re.DOTALL,
        )
        imports: dict = {}
        for m in re.finditer(r"^from ([\w.]+) import ([\w ,]+)", flat, re.MULTILINE):
            mod = m.group(1)
            if mod.split(".")[0] not in PROJECT_PKGS:
                continue
            names = [n.strip().split(" as ")[0].strip() for n in m.group(2).split(",")]
            names = [n for n in names if n and not n.startswith("_")]
            if names:
                imports.setdefault(mod, set()).update(names)
        module_imports[module] = {k: list(v) for k, v in imports.items()}
    return module_imports


def _fix_old_getattr_cycles(scan_files: list) -> int:
    """
    Convert __getattr__ lazy-import blocks written by an older version of
    install.py/_break_import_cycles into try/except ImportError guards.

    Trigger: file contains both '_CIRCULAR_' and 'def __getattr__(name):'.
    That combination is the fingerprint of the old lazy-loader pattern.

    Locates the _CIRCULAR_XXX dict, extracts {name: source_mod} entries,
    removes the entire block (comment + dict + __getattr__ function), and
    injects a try/except guard after the last top-level import line.
    """
    # Loose dict-line detector:  _CIRCULAR_XXX = {'Foo': 'pkg.mod', ...}
    GUARD_LINE = re.compile(
        r'^_CIRCULAR_[\w]+\s*=\s*(\{[^}]+\})',
        re.MULTILINE,
    )
    # Marks the very last line of the __getattr__ block we wrote
    RAISE_LINE = re.compile(
        r'    raise AttributeError\([^\n]*\)\n',
        re.MULTILINE,
    )

    fixed = 0
    for py_file in scan_files:
        if not py_file.exists():
            continue
        try:
            src = py_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        # Quick pre-check using plain string — no em-dash dependency
        if '_CIRCULAR_' not in src or 'def __getattr__(name):' not in src:
            continue

        new_src = src
        for gm in list(GUARD_LINE.finditer(src)):
            dict_str = gm.group(1)
            # Parse {'Name1': 'pkg.mod', 'Name2': 'pkg.mod'}
            entries = re.findall(r"['\"](\w+)['\"]:\s*['\"]([^'\"]+)['\"]", dict_str)
            if not entries:
                continue
            names      = [e[0] for e in entries]
            source_mod = entries[0][1]   # all values share the same module

            # ── Locate block boundaries ──────────────────────────────────
            # Block start: look for a "# ... circular dependency ..." comment
            # line immediately before the _CIRCULAR_ line, else the dict line.
            block_start = gm.start()
            preceding   = new_src[:block_start].rstrip('\n')
            nl           = preceding.rfind('\n')
            if nl != -1:
                prev_line = preceding[nl + 1:]
                if prev_line.lstrip().startswith('#') and 'circular' in prev_line.lower():
                    # Include the newline that precedes the comment
                    block_start = nl if new_src[nl - 1:nl] == '\n' else nl
            # Block end: the raise AttributeError line inside __getattr__
            getattr_pos = new_src.find('def __getattr__(name):', gm.end())
            if getattr_pos == -1:
                continue
            em = RAISE_LINE.search(new_src, getattr_pos)
            block_end = em.end() if em else len(new_src)

            # ── Build replacement ─────────────────────────────────────────
            placeholders = "\n".join(
                f"    {n} = type('{n}', (), {{}})" for n in names
            )
            try_block = (
                f"\ntry:\n"
                f"    from {source_mod} import {', '.join(names)}\n"
                f"except ImportError:  # circular import guard — {source_mod}\n"
                f"{placeholders}\n"
            )

            stripped    = new_src[:block_start] + new_src[block_end:]
            imp_matches = list(re.finditer(
                r'^(?:from|import)\s+\S[^\n]*\n', stripped, re.MULTILINE,
            ))
            ins     = imp_matches[-1].end() if imp_matches else 0
            new_src = stripped[:ins] + try_block + stripped[ins:]

        if new_src != src:
            py_file.write_text(new_src, encoding="utf-8")
            print(f"  FIXED [old->guard  ]  {py_file}  →  converted __getattr__ to try/except")
            fixed += 1
    return fixed


def phase1b_break_circular_imports(scan_files: list) -> int:
    """
    Build an intra-project import graph, find A↔B circular pairs, then break
    the cycle in the alphabetically-first module by replacing the circular
    `from X import Y` with a try/except that installs a placeholder class on
    ImportError:

        try:
            from memory.semantic import SemanticMemory
        except ImportError:          # circular import guard
            SemanticMemory = type('SemanticMemory', (), {})

    This works for bare-name lookups inside class bodies (type annotations,
    default-value expressions) which __getattr__ cannot intercept.
    """
    # Pre-step: upgrade any old __getattr__ blocks left by a previous repair run
    fixed = _fix_old_getattr_cycles(scan_files)

    module_imports = _build_import_graph(scan_files)

    seen_pairs: set = set()
    circular_fixes: list = []

    for mod_a, imports_a in module_imports.items():
        for mod_b in list(imports_a):
            if mod_b not in module_imports:
                continue
            if mod_a not in module_imports[mod_b]:
                continue
            pair = tuple(sorted([mod_a, mod_b]))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            patch_mod  = pair[0]   # alphabetically first — patch this one
            source_mod = pair[1]
            lazy_names = module_imports[patch_mod].get(source_mod, [])
            if lazy_names:
                circular_fixes.append((
                    Path(patch_mod.replace(".", "/") + ".py"),
                    source_mod,
                    lazy_names,
                ))

    fixed = 0
    for py_file, from_module, lazy_names in circular_fixes:
        if not py_file.exists():
            continue
        try:
            src = py_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        # Already patched with try/except guard?
        if f"# circular import guard" in src and from_module in src:
            continue

        new_src = src

        # For each import line that pulls from the circular module, wrap it.
        # We match the full "from X import a, b, c" line regardless of how
        # many names it imports, and wrap the entire statement.
        for m in re.finditer(
            rf"^(from {re.escape(from_module)} import ([^\n]+))\n",
            new_src, re.MULTILINE,
        ):
            full_stmt  = m.group(1)           # e.g. "from memory.semantic import SemanticMemory"
            names_part = m.group(2)           # e.g. "SemanticMemory"
            all_names  = [n.strip().split(" as ")[0].strip()
                          for n in names_part.split(",") if n.strip()]
            # Only wrap if any of these are in our circular set
            if not any(n in lazy_names for n in all_names):
                continue
            placeholders = "\n".join(
                f"    {n} = type('{n}', (), {{}})" for n in all_names
            )
            wrapped = (
                f"try:\n"
                f"    {full_stmt}\n"
                f"except ImportError:  # circular import guard — {from_module}\n"
                f"{placeholders}\n"
            )
            new_src = new_src.replace(m.group(0), wrapped, 1)

        if new_src != src:
            py_file.write_text(new_src, encoding="utf-8")
            print(f"  FIXED [circular   ]  {py_file}  →  guarded: {lazy_names} from {from_module}")
            fixed += 1

    return fixed  # includes pre-step count from _fix_old_getattr_cycles


# ── Phase 2: Fix missing imports ─────────────────────────────────────────────

def phase2_fix_imports(scan_files: list) -> int:
    fixed = 0
    problems = []

    for src_file in scan_files:
        try:
            src = src_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        # Collapse parenthesized multi-line imports
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
        print("  NOTE: missing .py files need 'python install.py' to generate them.")

    return fixed


# ── Phase 3: Inject missing auto-imports ─────────────────────────────────────

# Known module-prefix usages that require a specific import line.
# Format: (regex_that_detects_usage, import_line_to_inject, bound_name_guard)
_AUTO_IMPORTS = [
    (r'\bretry\.',             'from google.api_core import retry',                         'retry'),
    (r'\bGoogleAPIError\b',    'from google.api_core.exceptions import GoogleAPIError',     'GoogleAPIError'),
    (r'\bgoogle_exceptions\.',  'from google.api_core import exceptions as google_exceptions', 'google_exceptions'),
    (r'\bfirestore\.',         'from google.cloud import firestore',                        'firestore'),
    (r'\bfirebase_admin\.',    'import firebase_admin',                                     'firebase_admin'),
    (r'\bstorage\.Client\b',   'from google.cloud import storage',                         'storage'),
    (r'\btenacity\.',          'import tenacity',                                           'tenacity'),
    (r'\baiohttp\.',           'import aiohttp',                                            'aiohttp'),
    (r'\bhttpx\.',             'import httpx',                                              'httpx'),
    (r'\bnp\.',                'import numpy as np',                                        'np'),
    (r'\bpd\.',                'import pandas as pd',                                       'pd'),
]


def phase3_inject_missing_imports(scan_files: list) -> int:
    """Inject missing imports for known module-prefix usages (e.g. retry.Retry
    without 'from google.api_core import retry')."""
    fixed = 0
    for py_file in scan_files:
        if py_file.name in ("repair.py", "install.py"):
            continue
        try:
            src = py_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        new_src = src
        for pat, imp, guard in _AUTO_IMPORTS:
            if not re.search(pat, new_src):
                continue
            if imp in new_src:
                continue  # exact import line already present
            last = list(re.finditer(r'^(?:import |from )\S+', new_src, re.MULTILINE))
            if last:
                pos = last[-1].end()
                new_src = new_src[:pos] + f"\n{imp}" + new_src[pos:]
            else:
                new_src = imp + "\n" + new_src

        # Strip @retry.X() module-qualified decorators.
        # google.api_core.retry and tenacity both bind to the name 'retry';
        # even after import injection the wrong one may win, causing NameError
        # at class-body execution time. Firebase/gRPC methods work without them.
        stripped = re.sub(r'^[ \t]*@retry\.\w+\([^)\n]*\)\n', '', new_src, flags=re.MULTILINE)
        if stripped != new_src:
            new_src = stripped

        if new_src != src:
            py_file.write_text(new_src, encoding="utf-8")
            print(f"  FIXED [auto-import]  {py_file}")
            fixed += 1

    return fixed


# ── Phase 4: Make __init__ params optional ────────────────────────────────────

def phase4_fix_init_params(scan_files: list) -> int:
    fixed = 0
    for py_file in scan_files:
        if py_file.name in ("repair.py", "install.py"):
            continue
        try:
            src = py_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        new_src, changed = make_init_optional(src)
        if changed:
            py_file.write_text(new_src, encoding="utf-8")
            print(f"  FIXED [__init__   ]  {py_file}  →  optional: {', '.join(changed)}")
            fixed += 1
    return fixed


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    print("\n  Physics Discovery System v3.0 — Import Repair Tool")
    print("  " + "─" * 52)

    scan_files = all_project_py_files()
    total_fixed = 0

    print("\n  Phase 1: Removing shadowing stubs (def shadows class)")
    print("  " + "─" * 52)
    total_fixed += phase1_remove_shadowing_stubs(scan_files)

    print("\n  Phase 1b: Breaking circular imports (try/except guard)")
    print("  " + "─" * 52)
    total_fixed += phase1b_break_circular_imports(scan_files)

    print("\n  Phase 2: Fixing missing exports (aliases / stubs)")
    print("  " + "─" * 52)
    total_fixed += phase2_fix_imports(scan_files)

    print("\n  Phase 3: Injecting missing auto-imports (retry, firestore, etc.)")
    print("  " + "─" * 52)
    total_fixed += phase3_inject_missing_imports(scan_files)

    print("\n  Phase 4: Making __init__ params optional (default=None)")
    print("  " + "─" * 52)
    total_fixed += phase4_fix_init_params(scan_files)

    # Second pass of Phase 2 — earlier phases may expose new import mismatches
    print("\n  Phase 2 (second pass)")
    print("  " + "─" * 52)
    second = phase2_fix_imports(scan_files)
    if second:
        total_fixed += second
    else:
        print("  Nothing new.")

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
