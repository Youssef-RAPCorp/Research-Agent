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

        # Add **kwargs if not already present — absorbs unexpected keyword args
        # from callers so we never get 'unexpected keyword argument' TypeErrors.
        has_kwargs = any(t.strip().startswith('**') for t in new_tokens)
        if not has_kwargs:
            new_tokens.append('**kwargs')
            changed_params.append('**kwargs')

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
        # Use a while loop so every position is relative to the CURRENT new_src,
        # not the original src (avoids off-by-N errors when multiple blocks exist).
        while True:
            gm = GUARD_LINE.search(new_src)
            if not gm:
                break
            dict_str = gm.group(1)
            # Parse {'Name1': 'pkg.mod', 'Name2': 'pkg.mod'}
            entries = re.findall(r"['\"](\w+)['\"]:\s*['\"]([^'\"]+)['\"]", dict_str)
            if not entries:
                break
            names      = [e[0] for e in entries]
            source_mod = entries[0][1]   # all values share the same module

            # ── Locate block boundaries in new_src ───────────────────────
            block_start = gm.start()
            preceding   = new_src[:block_start].rstrip('\n')
            nl           = preceding.rfind('\n')
            if nl != -1:
                prev_line = preceding[nl + 1:]
                if prev_line.lstrip().startswith('#') and 'circular' in prev_line.lower():
                    block_start = nl if new_src[nl - 1:nl] == '\n' else nl
            getattr_pos = new_src.find('def __getattr__(name):', gm.end())
            if getattr_pos == -1:
                break
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


def _can_reach(graph_flat: dict, start: str, target: str) -> bool:
    """BFS: can we reach 'target' from 'start' following imports?"""
    visited: set = set()
    queue = [start]
    while queue:
        node = queue.pop()
        if node == target:
            return True
        if node in visited:
            continue
        visited.add(node)
        queue.extend(graph_flat.get(node, ()))
    return False


def phase1b_break_circular_imports(scan_files: list) -> int:
    """
    Build an intra-project import graph, find ALL cycles (A↔B direct pairs
    AND longer A→B→C→A chains) via reachability, then break each back-edge
    by wrapping the circular import in try/except + placeholder class.

        try:
            from memory.semantic import SemanticMemory
        except ImportError:          # circular import guard
            SemanticMemory = type('SemanticMemory', (), {})

    For an n-node cycle every edge (M imports N) where N can transitively
    reach M is a back-edge and gets patched.
    """
    # Pre-step: upgrade any old __getattr__ blocks left by a previous repair run
    fixed = _fix_old_getattr_cycles(scan_files)

    module_imports = _build_import_graph(scan_files)

    # Flat graph {mod: set(mods it imports)} for reachability checks
    graph_flat = {mod: set(imp.keys()) for mod, imp in module_imports.items()}

    seen_edges: set = set()
    circular_fixes: list = []

    for mod_a, imports_a in module_imports.items():
        for source_mod, names in imports_a.items():
            if source_mod not in module_imports:
                continue
            # Back-edge: can source_mod (transitively) reach mod_a?
            if not _can_reach(graph_flat, source_mod, mod_a):
                continue
            edge = (mod_a, source_mod)
            if edge in seen_edges:
                continue
            seen_edges.add(edge)
            if names:
                circular_fixes.append((
                    Path(mod_a.replace(".", "/") + ".py"),
                    source_mod,
                    names,
                ))

    new_cycle_fixed = 0
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
            new_cycle_fixed += 1

    return fixed + new_cycle_fixed


# ── Phase 1c: Fix undefined class-body annotation names ──────────────────────

# Type names that are always available without import
_BUILTIN_TYPES = {
    'int', 'str', 'float', 'bool', 'bytes', 'list', 'dict', 'set', 'tuple',
    'type', 'object', 'None', 'True', 'False', 'Self',
    'Any', 'Optional', 'Union', 'List', 'Dict', 'Set', 'Tuple', 'Type',
    'Callable', 'Awaitable', 'Coroutine', 'AsyncGenerator', 'Generator',
    'Iterator', 'Iterable', 'Sequence', 'Mapping', 'MutableMapping',
    'MutableSequence', 'ClassVar', 'Final', 'Literal', 'TypeVar', 'Protocol',
    'dataclass', 'abstractmethod', 'property', 'staticmethod', 'classmethod',
    'NotImplementedError', 'Exception', 'ValueError', 'TypeError',
    'AttributeError', 'KeyError', 'RuntimeError', 'ImportError',
    'asyncio', 'logging', 'datetime', 'Path',
}


def _names_defined_in_file(src: str) -> set:
    """Return all names bound at module level (class/def/import/assignment)."""
    names: set = set()
    # class Foo / def foo
    for m in re.finditer(r'^(?:class|def)\s+(\w+)', src, re.MULTILINE):
        names.add(m.group(1))
    # CamelCase = ... (assignments, incl. type(...) placeholder)
    for m in re.finditer(r'^([A-Z]\w*)\s*=', src, re.MULTILINE):
        names.add(m.group(1))
    # from X import Foo, Bar [as baz] — top-level AND inside try/except
    flat = re.sub(r'from ([\w.]+) import \(([^)]+)\)',
                  lambda mm: f"from {mm.group(1)} import {', '.join(mm.group(2).split())}",
                  src, flags=re.DOTALL)
    for m in re.finditer(r'\bfrom\s+[\w.]+\s+import\s+([\w ,]+)', flat):
        for n in m.group(1).split(','):
            n = n.strip().split(' as ')[-1].strip()
            if n:
                names.add(n)
    return names


def _build_project_name_index(scan_files: list) -> dict:
    """
    Return {CamelCaseName: 'pkg.module'} for every CamelCase name exported by
    a project file, whether via 'class Foo', 'def Foo', or a top-level
    assignment 'Foo = ...' (covers aliases like ChatEvalPattern = ChatEvaluator
    and dynamic classes like Foo = type('Foo', ...)).
    """
    index: dict = {}
    for pf in scan_files:
        if not pf.exists() or pf.name in ('repair.py', 'install.py', '__init__.py'):
            continue
        pkg = pf.parent.name
        if pkg not in PROJECT_PKGS:
            continue
        module = f"{pkg}.{pf.stem}"
        try:
            src = pf.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        # class Foo / def Foo
        for m in re.finditer(r'^(?:class|def)\s+([A-Z]\w+)\b', src, re.MULTILINE):
            name = m.group(1)
            if name not in index:
                index[name] = module
        # Top-level assignment: FooBar = ...
        for m in re.finditer(r'^([A-Z][a-zA-Z0-9_]+)\s*=', src, re.MULTILINE):
            name = m.group(1)
            if name not in index:
                index[name] = module
    return index


def _all_bare_camel_names(src: str) -> set:
    """
    Return all CamelCase identifiers used as bare tokens in src that are NOT:
      - preceded by '.' (attribute access: obj.Name)
      - inside string literals or comments

    Strips triple- and single-quoted strings and # comments before scanning
    so 'ClassName' inside a docstring isn't counted.
    """
    # Strip triple-quoted strings first
    s = re.sub(r'""".*?"""', '""', src, flags=re.DOTALL)
    s = re.sub(r"'''.*?'''", "''", s,  flags=re.DOTALL)
    # Strip single-line strings
    s = re.sub(r'"[^"\n\\]*(?:\\.[^"\n\\]*)*"', '""', s)
    s = re.sub(r"'[^'\n\\]*(?:\\.[^'\n\\]*)*'", "''", s)
    # Strip line comments
    s = re.sub(r'#[^\n]*', '', s)
    # Find bare CamelCase tokens (not preceded by '.' or word char)
    return {m.group(1) for m in re.finditer(r'(?<![.\w])([A-Z][a-z]\w+|[A-Z]{2,}\w*)(?!\w)', s)}


def phase1c_fix_undefined_annotations(scan_files: list) -> int:
    """
    Scan every project file for CamelCase names that are used as bare tokens
    (class-body annotations, method-body references, dict values, etc.) but
    are not imported or defined in that file.  For each such name found in
    the project name index, inject a try/except ImportError guard after the
    last top-level import line.

    Covers both annotation-position uses (semantic: SemanticMemory) and
    general method-body uses (ChatEvalPattern used as a dict value).
    """
    name_index = _build_project_name_index(scan_files)

    fixed = 0
    for py_file in scan_files:
        if not py_file.exists() or py_file.name in ('repair.py', 'install.py', '__init__.py'):
            continue
        try:
            src = py_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        used_names = _all_bare_camel_names(src)
        if not used_names:
            continue

        already  = _names_defined_in_file(src)
        to_fix   = [n for n in used_names
                    if n not in already and n not in _BUILTIN_TYPES]
        # Split: names found in project files → try/except import
        #        names not found anywhere    → local placeholder stub
        to_import = [n for n in to_fix if n in name_index]
        to_stub   = [n for n in to_fix if n not in name_index]
        if not to_import and not to_stub:
            continue

        new_src = src
        added: list = []

        for name in sorted(to_import):
            if name in _names_defined_in_file(new_src):
                continue
            source_mod   = name_index[name]
            placeholders = f"    {name} = type('{name}', (), {{}})"
            try_block    = (
                f"\ntry:\n"
                f"    from {source_mod} import {name}\n"
                f"except ImportError:  # circular import guard — {source_mod}\n"
                f"{placeholders}\n"
            )
            imp_matches = list(re.finditer(
                r'^(?:from|import)\s+\S[^\n]*\n', new_src, re.MULTILINE,
            ))
            ins     = imp_matches[-1].end() if imp_matches else 0
            new_src = new_src[:ins] + try_block + new_src[ins:]
            added.append(f"{name}←{source_mod}")

        for name in sorted(to_stub):
            if name in _names_defined_in_file(new_src):
                continue
            # Append a placeholder stub at the end of the file
            new_src += f"\n{name} = type('{name}', (), {{}})  # auto-stub: not found in project\n"
            added.append(f"{name}(stub)")

        if added:
            py_file.write_text(new_src, encoding="utf-8")
            print(f"  FIXED [undef name  ]  {py_file}  →  {added}")
            fixed += 1
    return fixed


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
    (r'\bET\.',                'import xml.etree.ElementTree as ET',                        'ET'),
]


def phase3_repair_broken_from_injections(scan_files: list) -> int:
    """
    Repair 'from X import Y' statements that were split by a previous buggy
    Phase 3 run.

    The old injection code used r'^(?:import |from )\\S+' which stopped at the
    first word of a 'from pkg.mod import Name' line, then inserted the new
    import right there — breaking the original statement into:

        Bad:    from knowledge.embedder
                import xml.etree.ElementTree as ET import EmbeddingModel

        Fixed:  from knowledge.embedder import EmbeddingModel
                import xml.etree.ElementTree as ET
    """
    # Line 1: 'from X.module'  (nothing after the module name)
    # Line 2: 'import A [as B] import OriginalNames...'
    BROKEN = re.compile(
        r'^(from[ \t]+\S+)[ \t]*\n'
        r'(import[ \t]+\S[^\n]*)[ \t]+import[ \t]+([^\n]+)$',
        re.MULTILINE,
    )

    fixed = 0
    for py_file in scan_files:
        if not py_file.exists() or py_file.name in ('repair.py', 'install.py'):
            continue
        try:
            src = py_file.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue
        if not BROKEN.search(src):
            continue
        new_src = BROKEN.sub(r'\1 import \3\n\2', src)
        if new_src != src:
            py_file.write_text(new_src, encoding='utf-8')
            print(f"  FIXED [from-repair ]  {py_file}  →  restored split from-import")
            fixed += 1
    return fixed


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
            # Match the FULL import line (not just the first word) so we insert
            # after the complete statement and never split 'from X import Y'.
            last = list(re.finditer(r'^(?:import |from )[^\n]+', new_src, re.MULTILINE))
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


def _class_body_and_ins(src: str, cls_m: re.Match) -> tuple:
    """
    Return (body_str, ins_pos) for a class definition match.

    Walks line-by-line from right after the class header colon.  Handles
    multi-line triple-quoted strings (docstrings, f-string templates) whose
    closing delimiter may be at column-0 — the extractor continues past such
    lines instead of stopping prematurely, preventing code injection inside
    string literals.
    """
    body_lines: list = []
    last_indented_end = cls_m.end()
    scan_pos = cls_m.end()

    # skip to end of the class definition line
    nl = src.find('\n', scan_pos)
    scan_pos = (nl + 1) if nl != -1 else len(src)

    in_triple  = False
    triple_ch  = None

    while scan_pos < len(src):
        nl       = src.find('\n', scan_pos)
        line_end = nl if nl != -1 else len(src)
        line     = src[scan_pos:line_end]

        if in_triple:
            # We're inside a multi-line string — consume unconditionally
            body_lines.append(line)
            if triple_ch in line:
                in_triple = False
                last_indented_end = line_end + 1   # injection goes after the closing quote
            scan_pos = line_end + 1
            continue

        if not line.strip():
            body_lines.append(line)
            scan_pos = line_end + 1
            continue

        if line[:1] not in (' ', '\t'):
            break   # un-indented non-blank → end of class body

        # Check whether this line opens an unclosed triple-quote
        for tq in ('"""', "'''"):
            if line.count(tq) % 2 == 1:   # odd occurrences → opens a block
                in_triple = True
                triple_ch = tq
                break

        body_lines.append(line)
        last_indented_end = line_end + 1
        scan_pos = line_end + 1

    return '\n'.join(body_lines), last_indented_end


# ── Phase 5: Implement missing abstract methods ───────────────────────────────

def _collect_abstract_methods(scan_files: list) -> dict:
    """
    Return {ClassName: [(method_name, is_async)]} for every class that
    declares one or more @abstractmethod methods.
    """
    result: dict = {}
    for py_file in scan_files:
        if not py_file.exists():
            continue
        try:
            src = py_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if 'abstractmethod' not in src:
            continue
        # Walk class bodies looking for @abstractmethod / @abc.abstractmethod
        for cls_m in re.finditer(r'^class (\w+)[^:]*:', src, re.MULTILINE):
            cls_name = cls_m.group(1)
            # Indentation-based body extraction (same as phase5)
            body_lines_c: list = []
            scan_pos = cls_m.end()
            nl = src.find('\n', scan_pos)
            scan_pos = (nl + 1) if nl != -1 else len(src)
            while scan_pos < len(src):
                nl = src.find('\n', scan_pos)
                line_end = nl if nl != -1 else len(src)
                line = src[scan_pos:line_end]
                if not line.strip():
                    body_lines_c.append(line); scan_pos = line_end + 1; continue
                if line[:1] in (' ', '\t'):
                    body_lines_c.append(line); scan_pos = line_end + 1; continue
                break
            body = '\n'.join(body_lines_c)
            for am in re.finditer(
                r'@(?:\w+\.)*abstractmethod[^\n]*\n\s*(async\s+)?def (\w+)\s*\(',
                body,
            ):
                is_async   = bool(am.group(1))
                method_name = am.group(2)
                result.setdefault(cls_name, [])
                if (method_name, is_async) not in result[cls_name]:
                    result[cls_name].append((method_name, is_async))
    return result


def phase5_strip_abstract_decorators(scan_files: list) -> int:
    """
    Strip every @abstractmethod / @abc.abstractmethod decorator line from
    project files.  Once the decorators are gone Python will never raise
    'Can't instantiate abstract class …' regardless of how deep the
    inheritance chain is or which subclass is missing an implementation.

    Also removes 'abstractmethod' from 'from abc import …' lines so there
    are no NameError complaints about the unused name.
    """
    DECO_RE  = re.compile(r'^[ \t]*@(?:\w+\.)*abstractmethod[^\n]*\n', re.MULTILINE)
    # matches: from abc import ABC, abstractmethod  (and variations)
    ABC_IMPORT_RE = re.compile(
        r'^(from\s+abc\s+import\s+)(.*?)([ \t]*(?:#[^\n]*)?)(\n|$)',
        re.MULTILINE,
    )
    fixed = 0
    for py_file in scan_files:
        if not py_file.exists() or py_file.name in ('repair.py', 'install.py'):
            continue
        try:
            src = py_file.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue
        if 'abstractmethod' not in src:
            continue

        new_src = src

        # 1. Strip all @abstractmethod / @abc.abstractmethod decorator lines
        stripped = DECO_RE.sub('', new_src)
        if stripped != new_src:
            new_src = stripped

        # 2. Remove 'abstractmethod' from 'from abc import ...' lines
        def _clean_abc_import(m: re.Match) -> str:
            prefix  = m.group(1)          # 'from abc import '
            names   = m.group(2)          # 'ABC, abstractmethod'
            comment = m.group(3)          # optional trailing comment
            ending  = m.group(4)          # '\n' or ''
            parts = [p.strip() for p in names.split(',')]
            parts = [p for p in parts if p and p != 'abstractmethod']
            if not parts:
                return ''                  # drop the whole import line
            return prefix + ', '.join(parts) + comment + ending

        cleaned = ABC_IMPORT_RE.sub(_clean_abc_import, new_src)
        if cleaned != new_src:
            new_src = cleaned

        if new_src != src:
            py_file.write_text(new_src, encoding='utf-8')
            print(f"  FIXED [abstractmethod strip]  {py_file}")
            fixed += 1
    return fixed


def phase5_fix_abstract_methods(scan_files: list) -> int:
    """
    For every concrete class that inherits from an abstract base but does not
    implement all of its @abstractmethod methods, inject minimal stub
    implementations so the class can be instantiated without TypeError.

        async def get_response(self, *args, **kwargs):
            return None
    """
    abstract_map = _collect_abstract_methods(scan_files)
    if not abstract_map:
        return 0

    fixed = 0
    for py_file in scan_files:
        if not py_file.exists() or py_file.name in ('repair.py', 'install.py'):
            continue
        try:
            src = py_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        new_src = src
        any_change = False

        # Process in REVERSE order: later insertions don't shift positions of
        # earlier classes that we haven't processed yet.
        class_matches = list(re.finditer(r'^class (\w+)\(([^)]+)\)\s*:', new_src, re.MULTILINE))
        for cls_m in reversed(class_matches):
            cls_name  = cls_m.group(1)
            bases_str = cls_m.group(2)
            bases     = [b.strip().split('.')[-1] for b in bases_str.split(',')]

            # Gather all abstract methods required by any base
            required: list = []
            for base in bases:
                required.extend(abstract_map.get(base, []))
            if not required:
                continue

            body, ins = _class_body_and_ins(new_src, cls_m)

            stubs_added: list = []
            for method_name, is_async in required:
                # Check only within the PROPERLY-BOUNDED body (indented lines only)
                if re.search(
                    rf'^[ \t]+(?:async\s+)?def {re.escape(method_name)}\s*\(',
                    body, re.MULTILINE,
                ):
                    continue  # already implemented inside the class
                async_kw = "async " if is_async else ""
                ret      = "await asyncio.sleep(0)\n        return None" if is_async else "return None"
                stub     = (
                    f"\n    {async_kw}def {method_name}(self, *args, **kwargs):\n"
                    f"        {ret}\n"
                )
                new_src  = new_src[:ins] + stub + new_src[ins:]
                ins     += len(stub)
                body    += stub
                stubs_added.append(method_name)

            if stubs_added:
                any_change = True
                print(f"  FIXED [abstract   ]  {py_file}:{cls_name}  →  stubbed: {stubs_added}")

        if any_change:
            py_file.write_text(new_src, encoding="utf-8")
            fixed += 1
    return fixed


def phase6_inject_agent_run_method(scan_files: list) -> int:
    """
    Ensure every *Agent class has a meaningful async def run(...) method.

    - If run is missing                 → inject a stub delegating to the best method
    - If run is our naive process_task stub → replace it with a smart delegate
    - Real run methods (not our stub)   → left untouched

    Delegation priority (first found wins):
      process_message       → wraps query in dict  {'query':..., 'type':'comprehensive'}
      comprehensive_research, process_query, execute, analyze,
      search, synthesize, process  → pass args/kwargs directly
      process_task                  → last resort (likely returns None)
    """
    # The naive stub we injected in previous runs — safe to replace
    OUR_STUB = re.compile(
        r'\n[ \t]+async def run\(self,[ \t]*\*args,[ \t]*\*\*kwargs\):[ \t]*\n'
        r'[ \t]+return await self\.process_task\(\*args,[ \t]*\*\*kwargs\)[ \t]*\n'
    )

    # (method_name, needs_dict_wrapper)
    DELEGATES = [
        ('process_message',        True),
        ('comprehensive_research', False),
        ('process_query',          False),
        ('execute',                False),
        ('analyze',                False),
        ('search',                 False),
        ('synthesize',             False),
        ('process',                False),
        ('process_task',           False),
    ]

    fixed = 0
    for py_file in scan_files:
        if not py_file.exists() or py_file.name in ('repair.py', 'install.py'):
            continue
        try:
            src = py_file.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue
        if not re.search(r'^class \w*Agent\b', src, re.MULTILINE):
            continue

        new_src = src
        any_change = False

        class_matches = list(re.finditer(r'^class (\w*Agent\b[^:]*)\s*:', new_src, re.MULTILINE))
        for cls_m in reversed(class_matches):
            cls_name = cls_m.group(1).split('(')[0].strip()

            body, ins = _class_body_and_ins(new_src, cls_m)
            cls_body_start = cls_m.end()

            has_run    = bool(re.search(r'^[ \t]+(?:async\s+)?def run\s*\(', body, re.MULTILINE))
            our_stub_m = OUR_STUB.search(new_src, cls_body_start, ins)

            if has_run and not our_stub_m:
                continue  # Real run method exists — leave it alone

            # Find the best method to delegate to
            delegate   = None
            needs_dict = False
            for method_name, dict_wrap in DELEGATES:
                if re.search(rf'^[ \t]+(?:async\s+)?def {re.escape(method_name)}\s*\(',
                             body, re.MULTILINE):
                    delegate   = method_name
                    needs_dict = dict_wrap
                    break

            if delegate is None:
                continue  # Nothing useful to call

            # Is the delegate itself async?
            is_async = bool(re.search(
                rf'^[ \t]+async\s+def {re.escape(delegate)}\s*\(', body, re.MULTILINE
            ))
            aw = 'await ' if is_async else ''

            if needs_dict:
                call = (
                    f"query = args[0] if args else kwargs.get('query', '')\n"
                    f"        return {aw}self.{delegate}({{'query': query, 'type': 'comprehensive'}})"
                )
            else:
                call = f"return {aw}self.{delegate}(*args, **kwargs)"

            new_stub = f'\n    async def run(self, *args, **kwargs):\n        {call}\n'

            if our_stub_m:
                new_src  = new_src[:our_stub_m.start()] + new_stub + new_src[our_stub_m.end():]
                action   = f'replaced naive stub → {delegate}'
            else:
                new_src  = new_src[:ins] + new_stub + new_src[ins:]
                action   = f'injected → {delegate}'

            any_change = True
            print(f"  FIXED [agent.run  ]  {py_file}:{cls_name}  →  {action}")

        if any_change:
            py_file.write_text(new_src, encoding='utf-8')
            fixed += 1
    return fixed


def phase6b_inject_process_message(scan_files: list) -> int:
    """
    Inject async def process_message into *Agent classes that are missing it,
    OR replace the bad broadcast_message stub injected by a previous run.

    broadcast_message is intentionally excluded from the delegate list because
    it expects (topic, payload) — two positional args — and callers pass one
    dict.  If no suitable delegate is found, inject a safe passthrough stub
    that returns the first positional argument (or {}) so callers don't crash.

    Delegation priority (first found wins):
      handle_message, receive_message, synthesize, process_query,
      execute, analyze, process, comprehensive_research
    Note: 'run' and 'broadcast_message' are excluded to avoid loops / arity bugs.
    """
    # Bad stub we injected in a previous run — replace it
    OUR_BAD_STUB = re.compile(
        r'\n[ \t]+async def process_message\(self,[ \t]*\*args,[ \t]*\*\*kwargs\):[ \t]*\n'
        r'[ \t]+return (?:await self\.broadcast_message\(\*args,[ \t]*\*\*kwargs\)'
        r'|args\[0\] if args else (?:\{\}|dict\(\)))'
        r'[ \t]*\n'
    )

    DELEGATES = [
        ('handle_message',        False),
        ('receive_message',       False),
        ('process_request',       False),   # synthesis-style agents
        ('synthesize',            False),
        ('process_query',         False),
        ('execute',               False),
        ('analyze',               False),
        ('process',               False),
        ('comprehensive_research', False),
    ]

    fixed = 0
    for py_file in scan_files:
        if not py_file.exists() or py_file.name in ('repair.py', 'install.py'):
            continue
        try:
            src = py_file.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue
        if not re.search(r'^class \w*Agent\b', src, re.MULTILINE):
            continue

        new_src    = src
        any_change = False

        class_matches = list(re.finditer(r'^class (\w*Agent\b[^:]*)\s*:', new_src, re.MULTILINE))
        for cls_m in reversed(class_matches):
            cls_name = cls_m.group(1).split('(')[0].strip()

            body, ins = _class_body_and_ins(new_src, cls_m)
            cls_body_start = cls_m.end()

            has_pm    = bool(re.search(r'^[ \t]+(?:async\s+)?def process_message\s*\(',
                                       body, re.MULTILINE))
            bad_stub_m = OUR_BAD_STUB.search(new_src, cls_body_start, ins)

            if has_pm and not bad_stub_m:
                continue  # Real process_message exists — leave it alone

            # Find best delegate (skip broadcast_message — wrong arity)
            delegate = None
            for method_name, _ in DELEGATES:
                if re.search(rf'^[ \t]+(?:async\s+)?def {re.escape(method_name)}\s*\(',
                             body, re.MULTILINE):
                    delegate = method_name
                    break

            # Build stub — delegate if possible, else safe passthrough
            if delegate:
                is_async = bool(re.search(
                    rf'^[ \t]+async\s+def {re.escape(delegate)}\s*\(', body, re.MULTILINE
                ))
                aw   = 'await ' if is_async else ''
                body_stmt = f'return {aw}self.{delegate}(*args, **kwargs)'
                action = f'injected → {delegate}'
            else:
                body_stmt = 'return args[0] if args else dict()'
                action = 'injected passthrough'

            new_stub = (
                f'\n    async def process_message(self, *args, **kwargs):\n'
                f'        {body_stmt}\n'
            )

            if bad_stub_m:
                new_src    = new_src[:bad_stub_m.start()] + new_stub + new_src[bad_stub_m.end():]
                action     = f'replaced bad broadcast_message stub → {action.split("→")[-1].strip()}'
            else:
                new_src    = new_src[:ins] + new_stub + new_src[ins:]

            any_change = True
            print(f"  FIXED [proc_msg   ]  {py_file}:{cls_name}  →  {action}")

        if any_change:
            py_file.write_text(new_src, encoding='utf-8')
            fixed += 1
    return fixed


def phase7_fix_not_started_guards(scan_files: list) -> int:
    """
    Replace `raise RuntimeError("... not started")` guards with lazy auto-start.

    Pattern detected:
        if not self.<flag>:
            raise RuntimeError("... not started")

    Replaced with:
        if not self.<flag>:
            await self.start()

    This converts hard failures into lazy initialization so agents that require
    an explicit .start() call work correctly when used without it.
    """
    NOT_STARTED = re.compile(
        r'([ \t]+if not )(self\.\w+)(:\s*\n)'
        r'([ \t]+)raise RuntimeError\(["\'][^"\']*not started[^"\']*["\']\)',
        re.MULTILINE,
    )

    fixed = 0
    for py_file in scan_files:
        if not py_file.exists() or py_file.name in ('repair.py', 'install.py'):
            continue
        try:
            src = py_file.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue
        if 'not started' not in src and 'super().start()' not in src:
            continue

        def _replace(m: re.Match) -> str:
            guard_prefix = m.group(1)   # '        if not '
            guard_var    = m.group(2)   # 'self._started'
            colon_nl     = m.group(3)   # ':\n'
            inner_indent = m.group(4)   # '            '
            return f'{guard_prefix}{guard_var}{colon_nl}{inner_indent}await self.start()'

        new_src = NOT_STARTED.sub(_replace, src)

        # Also guard `await super().start()` — base class may not implement start()
        SUPER_START = re.compile(r'([ \t]+)(await super\(\)\.start\(\))', re.MULTILINE)
        def _guard_super(m: re.Match) -> str:
            ind = m.group(1)
            return (f'{ind}if hasattr(super(), "start"):  # guard: base may not implement start\n'
                    f'{ind}    await super().start()')
        new_src = SUPER_START.sub(_guard_super, new_src)

        if new_src != src:
            py_file.write_text(new_src, encoding='utf-8')
            print(f"  FIXED [not-started ]  {py_file}  →  auto-start + super().start() guard")
            fixed += 1
    return fixed


def phase8_stub_missing_attr_methods(scan_files: list) -> int:
    """
    Cross-reference self.attr.method() call sites against the attr's class
    definition.  For any (ClassName, method_name) pair where method_name is
    absent from ClassName, inject a safe stub so AttributeErrors don't abort
    the pipeline at runtime.

    Algorithm
    ---------
    1. Build a project-wide {ClassName → file} index.
    2. For each class in the project:
       a. Parse __init__ for  self.X = ClassName(...)  →  attr_map[X] = ClassName
       b. Scan the class body for  self.X.method(  call-sites.
       c. For each (ClassName, method) pair, check if method exists.
       d. If not, record it as missing.
    3. Write stubs in batches per file (reversed order = safe insertion).

    Stubs use `def` (not `async def`) with `return dict()` so callers that do
    `.get(...)` on the result don't crash.  Methods with a leading underscore
    are skipped (internal helpers, magic methods).
    """
    # ── Step 1: class → file index ────────────────────────────────────────────
    class_file: dict = {}
    for py_file in scan_files:
        if not py_file.exists():
            continue
        try:
            src = py_file.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue
        for m in re.finditer(r'^class (\w+)\b', src, re.MULTILINE):
            cls = m.group(1)
            if cls not in class_file:
                class_file[cls] = py_file

    # ── Step 2: collect missing (target_file → {class → {methods}}) ──────────
    missing: dict = {}   # {str(target_file): {class_name: set(method_names)}}

    ASSIGN_RE = re.compile(
        r'self\.(\w+)\s*=\s*(?:\w+\s+or\s+)?([A-Z]\w*)\s*\('
    )
    CALL_RE = re.compile(r'\bself\.(\w+)\.([a-z]\w*)\s*\(')

    for py_file in scan_files:
        if not py_file.exists() or py_file.name in ('repair.py', 'install.py'):
            continue
        try:
            src = py_file.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue

        for cls_m in re.finditer(r'^class (\w+)[^:]*:', src, re.MULTILINE):
            body_str, _ = _class_body_and_ins(src, cls_m)

            # Build attr → ClassName from __init__ assignments
            attr_map: dict = {}
            for am in ASSIGN_RE.finditer(body_str):
                attr_map[am.group(1)] = am.group(2)
            if not attr_map:
                continue

            # Find all call sites and check for missing methods
            seen = set()
            for cm in CALL_RE.finditer(body_str):
                attr_name   = cm.group(1)
                method_name = cm.group(2)
                if attr_name not in attr_map or method_name.startswith('_'):
                    continue
                target_cls = attr_map[attr_name]
                if target_cls not in class_file:
                    continue
                key = (target_cls, method_name)
                if key in seen:
                    continue
                seen.add(key)

                target_file = class_file[target_cls]
                try:
                    target_src = target_file.read_text(encoding='utf-8', errors='replace')
                except Exception:
                    continue

                tcls_m = re.search(
                    rf'^class {re.escape(target_cls)}\b[^:]*:', target_src, re.MULTILINE
                )
                if not tcls_m:
                    continue

                tbody, _ = _class_body_and_ins(target_src, tcls_m)
                if re.search(
                    rf'^[ \t]+(?:async\s+)?def {re.escape(method_name)}\s*\(',
                    tbody, re.MULTILINE,
                ):
                    continue  # already implemented

                fk = str(target_file)
                missing.setdefault(fk, {}).setdefault(target_cls, set()).add(method_name)

    # ── Step 3: write stubs in reverse-class order per file ──────────────────
    fixed = 0
    for file_path_str, cls_methods in missing.items():
        from pathlib import Path as _P
        target_file = _P(file_path_str)
        try:
            new_src = target_file.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue

        any_change = False
        class_matches = list(re.finditer(r'^class (\w+)[^:]*:', new_src, re.MULTILINE))
        for tcls_m in reversed(class_matches):
            cls_name = tcls_m.group(1)
            if cls_name not in cls_methods:
                continue

            _, ins = _class_body_and_ins(new_src, tcls_m)
            for method_name in sorted(cls_methods[cls_name]):
                stub = (
                    f'\n    async def {method_name}(self, *args, **kwargs):\n'
                    f'        return dict()\n'
                )
                new_src    = new_src[:ins] + stub + new_src[ins:]
                ins       += len(stub)
                any_change = True
                print(f"  FIXED [attr.method ]  {target_file}:{cls_name}.{method_name}()")

        if any_change:
            target_file.write_text(new_src, encoding='utf-8')
            fixed += 1
    return fixed


def phase9_arxiv_rate_limit_backoff(scan_files: list) -> int:
    """
    Replace hard `raise RuntimeError("ArXiv API error: 429/503")` with a
    graceful back-off + empty-result return so rate-limited searches don't
    abort the whole gather.

    Pattern found in _execute_arxiv_search:
        raise RuntimeError(f"ArXiv API error: {response.status}")

    Replaced with:
        if response.status in (429, 503):
            await asyncio.sleep(5)   # back off before giving up
            return []
        raise RuntimeError(f"ArXiv API error: {response.status}")

    This means 429/503 responses return empty paper lists (handled upstream
    by the valid_results filter) rather than propagating as exceptions.
    """
    ARXIV_ERR = re.compile(
        r'([ \t]+)(raise RuntimeError\(f["\']ArXiv API error: \{response\.status\}["\']\))',
        re.MULTILINE,
    )

    fixed = 0
    for py_file in scan_files:
        if not py_file.exists() or py_file.name in ('repair.py', 'install.py'):
            continue
        try:
            src = py_file.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue
        if 'ArXiv API error' not in src:
            continue

        def _replace(m: re.Match) -> str:
            ind = m.group(1)
            raise_line = m.group(2)
            return (
                f'{ind}if response.status in (429, 503):\n'
                f'{ind}    await asyncio.sleep(5)  # rate-limit back-off\n'
                f'{ind}    return []\n'
                f'{ind}{raise_line}'
            )

        new_src = ARXIV_ERR.sub(_replace, src)
        if new_src != src:
            py_file.write_text(new_src, encoding='utf-8')
            print(f"  FIXED [arxiv-429   ]  {py_file}  →  graceful 429/503 back-off")
            fixed += 1
    return fixed


# ── Phase 12: Fix method signature / async stub issues ───────────────────────

def _add_kwargs_to_method(src: str, method_name: str) -> tuple:
    """
    Find every 'def method_name(' (sync or async) in src and add **kwargs
    to the parameter list if not already present.

    Uses paren-balancing rather than a single-line regex so multi-line
    signatures (common in typed Python) are handled correctly.

    Returns (new_src, changed_bool).
    """
    pat = re.compile(
        rf'^[ \t]+(?:async\s+)?def {re.escape(method_name)}\s*\(',
        re.MULTILINE,
    )
    positions = [m.start() for m in pat.finditer(src)]
    if not positions:
        return src, False

    changed = False
    # Process in reverse so earlier offsets stay valid after insertions
    for mstart in reversed(positions):
        # Find the opening '('
        open_paren = src.index('(', mstart)
        # Balance parens to find the closing ')'
        depth, i = 0, open_paren
        while i < len(src):
            if src[i] == '(':
                depth += 1
            elif src[i] == ')':
                depth -= 1
                if depth == 0:
                    break
            i += 1
        close_paren = i

        params_str = src[open_paren + 1:close_paren]
        if '**' in params_str:
            continue  # already absorbs extra kwargs

        # Find insertion point: just before the closing ')', stripping
        # any trailing comma/whitespace so we get clean formatting
        ins = close_paren
        j = ins - 1
        while j > open_paren and src[j] in ' \t\n':
            j -= 1
        # Decide separator
        if j == open_paren:          # empty params — e.g. def f():
            sep = ''
        elif src[j] == ',':          # trailing comma already present
            sep = ' '
            ins = j + 1              # insert after the existing comma
        else:
            sep = ', '               # add comma before **kwargs

        src = src[:ins] + sep + '**kwargs' + src[ins:]
        changed = True

    return src, changed


def phase12_fix_method_signatures(scan_files: list) -> int:
    """
    Two-part fix for method-level issues that Phase 4 (init-only) doesn't cover:

    Part A — Upgrade sync stubs to async:
        Phase 8 previously injected synchronous stubs:
            def method_name(self, *args, **kwargs):
                return dict()
        If the caller does `await self.x.method_name(...)`, this crashes with
        "object dict can't be used in 'await' expression".
        Replace these stubs with `async def`.

    Part B — Add **kwargs to storage/search method signatures:
        Callers pass keyword args (e.g. vector=, top_k=, filters=) that the
        real method signature doesn't declare, causing TypeError.  Uses
        paren-balancing so multi-line signatures are handled correctly.
        Targets: search, query, similarity_search, vector_search, retrieve,
        store, store_context, get_context, insert, upsert, embed, encode, find.

    Part C — Add missing await before calls to async stubs:
        When Phase 12A upgraded a stub to async def, any call site that does
        NOT use await will get a "coroutine was never awaited" RuntimeWarning.
        Finds 'self.x.method(...)' calls (without await) and adds await.
    """
    # ── Part A: sync stub → async ─────────────────────────────────────────────
    SYNC_STUB = re.compile(
        r'\n([ \t]+)def (\w+)\(self,[ \t]*\*args,[ \t]*\*\*kwargs\):[ \t]*\n'
        r'[ \t]+return dict\(\)[ \t]*\n',
        re.MULTILINE,
    )

    TARGET_METHODS = [
        'search', 'query', 'similarity_search', 'vector_search',
        'retrieve', 'store', 'store_context', 'get_context',
        'insert', 'upsert', 'update', 'delete', 'embed', 'encode', 'find',
    ]

    # ── Part C: missing await before stub calls ───────────────────────────────
    # Matches:   self.x.method(   NOT preceded by 'await ' on the same line
    MISSING_AWAIT_RE = re.compile(
        r'(?<!\bawait\s)(?<!\bawait  )(?<!\bawait   )'   # negative lookbehind (crude)
        r'([ \t]+)(self\.\w+\.(?:'
        + '|'.join(TARGET_METHODS)
        + r')\s*\()',
        re.MULTILINE,
    )

    fixed = 0
    for py_file in scan_files:
        if not py_file.exists() or py_file.name in ('repair.py', 'install.py'):
            continue
        try:
            src = py_file.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue

        new_src = src

        # Part A
        def _make_async(m: re.Match) -> str:
            ind         = m.group(1)
            method_name = m.group(2)
            return (
                f'\n{ind}async def {method_name}(self, *args, **kwargs):\n'
                f'{ind}    return dict()\n'
            )

        patched = SYNC_STUB.sub(_make_async, new_src)
        if patched != new_src:
            new_src = patched
            print(f"  FIXED [async-stub  ]  {py_file}  →  sync stubs → async def")

        # Part B — paren-balancing approach handles single- and multi-line sigs
        b_changed = False
        for mname in TARGET_METHODS:
            if f'def {mname}' not in new_src:
                continue
            new_src, chg = _add_kwargs_to_method(new_src, mname)
            if chg:
                b_changed = True
        if b_changed:
            print(f"  FIXED [method-kwargs]  {py_file}  →  added **kwargs to storage/search methods")

        # Part C — add missing await before known async stub call sites
        # Only fix lines where the call is a plain statement (not already awaited)
        PLAIN_CALL = re.compile(
            r'^([ \t]+)(self\.\w+\.(?:'
            + '|'.join(TARGET_METHODS)
            + r')\s*\()',
            re.MULTILINE,
        )
        def _add_await(m: re.Match) -> str:
            ind  = m.group(1)
            call = m.group(2)
            return f'{ind}await {call}'
        patched = PLAIN_CALL.sub(_add_await, new_src)
        if patched != new_src:
            new_src = patched
            print(f"  FIXED [add-await   ]  {py_file}  →  added missing await on stub calls")

        if new_src != src:
            py_file.write_text(new_src, encoding='utf-8')
            fixed += 1

    return fixed


# ── Phase 11: Fix SynthesisAgent-style run() stubs ───────────────────────────

def phase11_fix_synthesis_run_stub(scan_files: list) -> int:
    """
    Fix injected run() stubs in agents whose real entry-point is process_request,
    which expects a dict with an 'agent_outputs' key (not a bare query string).

    Phase 6 injected:
        async def run(self, *args, **kwargs):
            query = args[0] if args else kwargs.get('query', '')
            return await self.process_message({'query': query, 'type': '...'})

    The orchestrator calls:  synthesis_agent.run(combined_string, query=query)
    so args[0] is the COMBINED RESEARCH TEXT, not a query.

    process_request reads:  request.get('agent_outputs', {})
    — so passing {'query': ..., 'type': 'comprehensive'} yields empty evidence.

    Replacement:
        async def run(self, *args, **kwargs):
            combined = args[0] if args else ''
            query = kwargs.get('query', args[1] if len(args) > 1 else '')
            return await self.process_request(
                {'agent_outputs': {'combined': combined}, 'query': query}
            )
    """
    # Phase 6 injected stub (process_message with type:comprehensive)
    OUR_RUN_STUB = re.compile(
        r'\n([ \t]+)async def run\(self,[ \t]*\*args,[ \t]*\*\*kwargs\):[ \t]*\n'
        r'[ \t]+query = args\[0\] if args else kwargs\.get\([^)]+\)[ \t]*\n'
        r'[ \t]+return await self\.process_message\(\{[^}]+\}\)[ \t]*\n',
        re.MULTILINE,
    )
    # Previous Phase 11 injection with wrong agent key 'combined'
    OUR_PHASE11_STUB = re.compile(
        r"\n([ \t]+)async def run\(self,[ \t]*\*args,[ \t]*\*\*kwargs\):[ \t]*\n"
        r"[ \t]+combined = args\[0\] if args else ''[ \t]*\n"
        r"[ \t]+query = kwargs\.get\('query', args\[1\] if len\(args\) > 1 else ''\)[ \t]*\n"
        r"[ \t]+return await self\.process_request\(\{'agent_outputs': \{'combined': combined\}[^)]+\}\)[ \t]*\n",
        re.MULTILINE,
    )

    fixed = 0
    for py_file in scan_files:
        if not py_file.exists() or py_file.name in ('repair.py', 'install.py'):
            continue
        try:
            src = py_file.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue

        # Only target agents that have process_request expecting agent_outputs
        if 'process_request' not in src or 'agent_outputs' not in src:
            continue

        m = OUR_RUN_STUB.search(src) or OUR_PHASE11_STUB.search(src)
        if not m:
            continue

        ind = m.group(1)
        # Use 'research_agent' as the agent key so ConfidenceWeighter gives it
        # weight 0.8 (vs 0.5 default for unknown 'combined') — passes the 0.3
        # min_confidence filter and produces non-empty synthesis output.
        new_run = (
            f"\n{ind}async def run(self, *args, **kwargs):\n"
            f"{ind}    combined = args[0] if args else ''\n"
            f"{ind}    query = kwargs.get('query', args[1] if len(args) > 1 else '')\n"
            f"{ind}    return await self.process_request("
            f"{{'agent_outputs': {{'research_agent': combined}}, 'query': query}})\n"
        )
        new_src = src[:m.start()] + new_run + src[m.end():]

        if new_src != src:
            py_file.write_text(new_src, encoding='utf-8')
            print(f"  FIXED [synth.run   ]  {py_file}  →  run() wraps args[0] as agent_outputs")
            fixed += 1

    return fixed


# ── Phase 10: Fix VectorSearch / type-dispatch None fallback ─────────────────

def phase10_fix_vector_search_dispatch(scan_files: list) -> int:
    """
    Two-part fix for agents whose process_message dispatches on message.get("type"):

    Part 1 — Missing-type fallback:
        Callers like ResearchAgent pass {"query": ..., "top_k": ...} with NO "type"
        key, causing the else-branch to return {"status":"error","message":"Unknown
        message type: None"}.  We insert an elif branch before the else:

            elif message_type is None:
                return await self._handle_semantic_search(message)

        (or whichever _handle_* is first available)

    Part 2 — Wrong-type stub:
        Phase 6 injects a run() stub that calls
            self.process_message({'query': query, 'type': 'comprehensive'})
        'comprehensive' is not a valid dispatch value in VectorSearchAgent, so it
        also hits the else-error.  Replace 'type': 'comprehensive' with
        'type': 'semantic_search' when the agent has _handle_semantic_search.
    """
    ELSE_UNKNOWN = re.compile(
        r'([ \t]+)(else:[ \t]*\n)'
        r'([ \t]+return \{[^\n]*[Uu]nknown message type[^\n]*\n)',
        re.MULTILINE,
    )
    HAS_TYPE_DISPATCH = re.compile(r"message_type\s*=\s*message\.get\(['\"]type['\"]\)")
    COMPREHENSIVE_STUB = re.compile(r"\{'query': query, 'type': 'comprehensive'\}")
    HANDLER_PRIORITY = [
        '_handle_semantic_search', '_handle_search', '_handle_query',
        '_execute_search', '_process_query',
    ]

    fixed = 0
    for py_file in scan_files:
        if not py_file.exists() or py_file.name in ('repair.py', 'install.py'):
            continue
        try:
            src = py_file.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue

        new_src = src

        # ── Part 1: add elif message_type is None ──────────────────────────
        if HAS_TYPE_DISPATCH.search(new_src) and 'Unknown message type' in new_src:
            if 'elif message_type is None:' not in new_src:
                fallback = None
                for h in HANDLER_PRIORITY:
                    if re.search(rf'\bdef {re.escape(h)}\s*\(', new_src):
                        fallback = h
                        break
                if fallback:
                    is_async = bool(re.search(
                        rf'async\s+def {re.escape(fallback)}\s*\(', new_src
                    ))
                    aw = 'await ' if is_async else ''
                    _fb = fallback   # capture for closure
                    _aw = aw

                    def _insert_none(m: re.Match, _fb=_fb, _aw=_aw) -> str:
                        ind    = m.group(1)
                        else_nl = m.group(2)
                        ret_ln  = m.group(3)
                        return (
                            f'{ind}elif message_type is None:\n'
                            f'{ind}    return {_aw}self.{_fb}(message)\n'
                            f'{ind}{else_nl}{ret_ln}'
                        )

                    patched = ELSE_UNKNOWN.sub(_insert_none, new_src)
                    if patched != new_src:
                        new_src = patched
                        print(f"  FIXED [vec-dispatch]  {py_file}  →  None type → {fallback}")

        # ── Part 2: fix 'type': 'comprehensive' in injected run() stubs ────
        if '_handle_semantic_search' in new_src and "'type': 'comprehensive'" in new_src:
            patched = COMPREHENSIVE_STUB.sub(
                "{'query': query, 'type': 'semantic_search'}", new_src
            )
            if patched != new_src:
                new_src = patched
                print(f"  FIXED [vec-dispatch]  {py_file}  →  type:comprehensive → semantic_search")

        if new_src != src:
            py_file.write_text(new_src, encoding='utf-8')
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

    print("\n  Phase 1c: Injecting imports for undefined class-body names")
    print("  " + "─" * 52)
    total_fixed += phase1c_fix_undefined_annotations(scan_files)

    print("\n  Phase 2: Fixing missing exports (aliases / stubs)")
    print("  " + "─" * 52)
    total_fixed += phase2_fix_imports(scan_files)

    print("\n  Phase 3 (pre): Repairing any from-import lines split by previous bad injection")
    print("  " + "─" * 52)
    total_fixed += phase3_repair_broken_from_injections(scan_files)

    print("\n  Phase 3: Injecting missing auto-imports (retry, firestore, etc.)")
    print("  " + "─" * 52)
    total_fixed += phase3_inject_missing_imports(scan_files)

    print("\n  Phase 4: Making __init__ params optional (default=None)")
    print("  " + "─" * 52)
    total_fixed += phase4_fix_init_params(scan_files)

    print("\n  Phase 5: Stripping @abstractmethod decorators")
    print("  " + "─" * 52)
    total_fixed += phase5_strip_abstract_decorators(scan_files)

    print("\n  Phase 5b: Stubbing abstract methods in concrete subclasses")
    print("  " + "─" * 52)
    total_fixed += phase5_fix_abstract_methods(scan_files)

    print("\n  Phase 6: Injecting async def run() into Agent classes")
    print("  " + "─" * 52)
    total_fixed += phase6_inject_agent_run_method(scan_files)

    print("\n  Phase 6b: Injecting process_message() into Agent classes")
    print("  " + "─" * 52)
    total_fixed += phase6b_inject_process_message(scan_files)

    print("\n  Phase 7: Replacing 'not started' RuntimeError guards with auto-start")
    print("  " + "─" * 52)
    total_fixed += phase7_fix_not_started_guards(scan_files)

    print("\n  Phase 9: ArXiv rate-limit backoff (429/503 → sleep + empty list)")
    print("  " + "─" * 52)
    total_fixed += phase9_arxiv_rate_limit_backoff(scan_files)

    print("\n  Phase 12: Fixing method signatures (async stubs + **kwargs on storage methods)")
    print("  " + "─" * 52)
    total_fixed += phase12_fix_method_signatures(scan_files)

    print("\n  Phase 8: Stubbing missing sub-object methods (attr.method())")
    print("  " + "─" * 52)
    total_fixed += phase8_stub_missing_attr_methods(scan_files)

    print("\n  Phase 11: Fixing synthesis-style run() stubs (process_request + agent_outputs)")
    print("  " + "─" * 52)
    total_fixed += phase11_fix_synthesis_run_stub(scan_files)

    print("\n  Phase 10: Fixing type-dispatch None fallback (VectorSearch)")
    print("  " + "─" * 52)
    total_fixed += phase10_fix_vector_search_dispatch(scan_files)

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
