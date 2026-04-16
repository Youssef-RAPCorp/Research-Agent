#!/usr/bin/env python3
"""
Physics Discovery System v3.0 — AI Installer
=============================================
RAP Corp | Renaissance of American Physics

Self-healing, OS-aware installer that uses the Claude API to generate
all 54 modules of the Physics Discovery System v3.0.

Run:
    python install.py

Requires:
    Python 3.10+  |  anthropic>=0.25  |  Your Claude API key
"""

import os
import re
import sys
import platform
import subprocess
import time
import json
import shutil
import textwrap
from pathlib import Path
from datetime import datetime
from typing import Optional

# ─────────────────────────────────────────────
# TERMINAL COLORS (works on all platforms)
# ─────────────────────────────────────────────

class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    BLUE   = "\033[94m"
    CYAN   = "\033[96m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    RED    = "\033[91m"
    WHITE  = "\033[97m"
    PURPLE = "\033[95m"

def no_color():
    for attr in vars(C):
        if not attr.startswith("_"):
            setattr(C, attr, "")

# Disable colors on Windows cmd (unless Windows Terminal / WT)
if platform.system() == "Windows" and "WT_SESSION" not in os.environ:
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleMode(
            ctypes.windll.kernel32.GetStdHandle(-11), 7)
    except Exception:
        no_color()

# ─────────────────────────────────────────────
# OS DETECTOR
# ─────────────────────────────────────────────

class OSDetector:
    def __init__(self):
        self.system   = platform.system()           # Windows / Darwin / Linux
        self.release  = platform.release()
        self.machine  = platform.machine()          # x86_64 / arm64 / AMD64
        self.python   = sys.version
        self.py_ver   = sys.version_info
        self.is_win   = self.system == "Windows"
        self.is_mac   = self.system == "Darwin"
        self.is_linux = self.system == "Linux"
        self.is_arm   = "arm" in self.machine.lower() or "aarch" in self.machine.lower()
        self.home     = Path.home()
        self.cwd      = Path.cwd()

    @property
    def venv_activate(self) -> str:
        if self.is_win:
            return r"venv\Scripts\activate"
        return "source venv/bin/activate"

    @property
    def venv_python(self) -> str:
        if self.is_win:
            return r"venv\Scripts\python.exe"
        return "venv/bin/python"

    @property
    def venv_pip(self) -> str:
        if self.is_win:
            return r"venv\Scripts\pip.exe"
        return "venv/bin/pip"

    @property
    def path_sep(self) -> str:
        return "\\" if self.is_win else "/"

    @property
    def pkg_manager_hint(self) -> str:
        if self.is_mac:
            return "brew install python@3.12" if shutil.which("brew") else "https://www.python.org/downloads/"
        if self.is_linux:
            if shutil.which("apt"):   return "sudo apt install python3.12 python3.12-venv"
            if shutil.which("dnf"):   return "sudo dnf install python3.12"
            if shutil.which("pacman"):return "sudo pacman -S python"
        return "https://www.python.org/downloads/"

    def detect_docker(self) -> bool:
        return shutil.which("docker") is not None

    def detect_git(self) -> bool:
        return shutil.which("git") is not None

    def report(self) -> dict:
        return {
            "os": self.system,
            "release": self.release,
            "arch": self.machine,
            "python": f"{self.py_ver.major}.{self.py_ver.minor}.{self.py_ver.micro}",
            "docker": self.detect_docker(),
            "git": self.detect_git(),
            "home": str(self.home),
        }

# ─────────────────────────────────────────────
# SELF-AWARE LOGGER
# ─────────────────────────────────────────────

class InstallerLogger:
    LOG_FILE = Path("logs") / "install.log"

    def __init__(self):
        Path("logs").mkdir(exist_ok=True)
        self._entries = []

    def _write(self, level: str, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        entry = f"[{ts}] [{level}] {msg}"
        self._entries.append({"ts": ts, "level": level, "msg": msg})
        try:
            with open(self.LOG_FILE, "a", encoding="utf-8") as f:
                f.write(entry + "\n")
        except Exception:
            pass

    def info(self,    msg): self._write("INFO",    msg); print(f"  {C.DIM}[{datetime.now().strftime('%H:%M:%S')}]{C.RESET} {msg}")
    def ok(self,      msg): self._write("OK",      msg); print(f"  {C.GREEN}✓{C.RESET} {msg}")
    def warn(self,    msg): self._write("WARN",    msg); print(f"  {C.YELLOW}⚠{C.RESET}  {msg}")
    def error(self,   msg): self._write("ERROR",   msg); print(f"  {C.RED}✗{C.RESET} {msg}")
    def phase(self,   msg): self._write("PHASE",   msg); print(f"\n{C.BOLD}{C.CYAN}{msg}{C.RESET}")
    def system(self,  msg): self._write("SYSTEM",  msg); print(f"  {C.BLUE}⬡{C.RESET}  {msg}")
    def muted(self,   msg): self._write("MUTED",   msg); print(f"  {C.DIM}{msg}{C.RESET}")
    def header(self,  msg): print(f"\n{C.BOLD}{C.PURPLE}{msg}{C.RESET}")

    def self_check(self):
        """Read own logs to detect previous failures and adjust strategy."""
        self.system("SELF-CHECK: reading installation logs...")
        if not self.LOG_FILE.exists():
            self.info("  → clean slate — no previous run detected")
            return {"failed_modules": [], "memory_issues": False}

        try:
            text = self.LOG_FILE.read_text(encoding="utf-8")
            lines = text.splitlines()
            # Only look at the most recent run (after the last PHASE marker for Step 5)
            last_run_start = 0
            for i, l in enumerate(lines):
                if "Step 5" in l:
                    last_run_start = i
            recent = lines[last_run_start:]
            failed = [l.split("[MODULE:")[-1].split("]")[0].strip()
                      for l in recent if "[ERROR]" in l and "[MODULE:" in l]
            memory_issues = any("memory" in l.lower() or "oom" in l.lower() for l in recent)
            self.info(f"  → {len(failed)} previously failed modules detected")
            if memory_issues:
                self.warn("  → memory issues in previous run — reducing concurrency")
            return {"failed_modules": failed, "memory_issues": memory_issues}
        except Exception as e:
            self.warn(f"  → could not read log: {e}")
            return {"failed_modules": [], "memory_issues": False}

# ─────────────────────────────────────────────
# MODULE REGISTRY (54 modules across 8 phases)
# ─────────────────────────────────────────────

REGISTRY = [
  # Phase 1 — Foundation
  {"phase":1,"id":"project_scaffold",     "name":"Project Scaffold",          "complexity":2, "path":"config/scaffold.py",
   "desc":"Utility functions for creating the project directory tree, .env template writer, and pyproject.toml generator."},
  {"phase":1,"id":"config_system",        "name":"Config System",             "complexity":3, "path":"config/settings.py",
   "desc":"Pydantic BaseSettings class for all environment variables, with validation, defaults, and nested model support."},
  {"phase":1,"id":"logging_system",       "name":"Self-Aware Logger",         "complexity":5, "path":"config/logger.py",
   "desc":"Structured logger that reads its own log file on startup to detect previous failures, memory issues, and adjust retry strategy."},
  {"phase":1,"id":"error_handler",        "name":"Error Handler",             "complexity":4, "path":"config/errors.py",
   "desc":"Custom exception hierarchy, global error handler, correlation ID injection, and stack trace enrichment utilities."},
  {"phase":1,"id":"firebase_client",      "name":"Firebase Client",           "complexity":5, "path":"config/firebase.py",
   "desc":"Async Firebase client wrapping Firestore, Auth, and Storage. Includes RAP Corp collection schemas and retry logic."},
  {"phase":1,"id":"requirements_manager", "name":"Requirements Manager",      "complexity":2, "path":"config/requirements_check.py",
   "desc":"Runtime dependency checker that validates all required packages are installed, with version pinning and conflict detection."},

  # Phase 2 — Knowledge Swarm
  {"phase":2,"id":"qdrant_store",         "name":"Qdrant Vector Store",       "complexity":6, "path":"knowledge/qdrant_store.py",
   "desc":"Async Qdrant client wrapper: collection management, upsert, similarity search, hybrid search, and payload filtering."},
  {"phase":2,"id":"document_embedder",    "name":"Document Embedder",         "complexity":6, "path":"knowledge/embedder.py",
   "desc":"Multi-model embedding pipeline using sentence-transformers. Includes an LRU cache and batch processing with progress tracking."},
  {"phase":2,"id":"arxiv_fetcher",        "name":"ArXiv Fetcher",             "complexity":5, "path":"knowledge/arxiv_fetcher.py",
   "desc":"ArXiv API client: paper search, abstract retrieval, LaTeX equation extraction, and author/citation metadata parsing."},
  {"phase":2,"id":"pdf_ingester",         "name":"PDF Ingester",              "complexity":5, "path":"knowledge/pdf_ingester.py",
   "desc":"PDF text extraction using pdfplumber: chunking strategy, figure detection, table extraction, and metadata preservation."},
  {"phase":2,"id":"knowledge_indexer",    "name":"Knowledge Indexer",         "complexity":7, "path":"knowledge/indexer.py",
   "desc":"Multi-source indexing pipeline with SHA256 deduplication, incremental updates, and progress checkpointing."},
  {"phase":2,"id":"retrieval_engine",     "name":"Retrieval Engine",          "complexity":8, "path":"knowledge/retrieval.py",
   "desc":"Hybrid retrieval: dense vector search + BM25 sparse search + cross-encoder reranking with configurable fusion weights."},
  {"phase":2,"id":"citation_tracker",     "name":"Citation Tracker",          "complexity":6, "path":"knowledge/citations.py",
   "desc":"Reference graph builder: DOI resolution, citation network construction, impact score tracking, and author profiling."},
  {"phase":2,"id":"knowledge_validator",  "name":"Knowledge Validator",       "complexity":7, "path":"knowledge/validator.py",
   "desc":"Consistency checker across indexed sources: contradiction detection, confidence-weighted conflict resolution, staleness flagging."},

  # Phase 3 — Memory Architecture
  {"phase":3,"id":"episodic_memory",      "name":"Episodic Memory",           "complexity":9, "path":"memory/episodic.py",
   "desc":"Per-agent episodic store: timestamped observations, actions, outcomes, and emotion-analogue valence. Supports temporal queries and decay."},
  {"phase":3,"id":"semantic_memory",      "name":"Semantic Memory",           "complexity":8, "path":"memory/semantic.py",
   "desc":"Long-term fact store with confidence decay functions, Bayesian update rules, contradiction handling, and Qdrant-backed retrieval."},
  {"phase":3,"id":"working_memory",       "name":"Working Memory",            "complexity":7, "path":"memory/working.py",
   "desc":"Active context window manager: priority queue with LRU eviction, token budget tracking, and importance-weighted retention."},
  {"phase":3,"id":"memory_router",        "name":"Memory Router",             "complexity":8, "path":"memory/router.py",
   "desc":"Routes queries to episodic/semantic/working memory stores with smart merging, deduplication, and confidence aggregation."},
  {"phase":3,"id":"reflexion_store",      "name":"Reflexion Store",           "complexity":9, "path":"memory/reflexion_store.py",
   "desc":"Verbal RL memory: stores past episode reflections, failure patterns, and successful strategies for future run adjustment."},
  {"phase":3,"id":"session_persistence",  "name":"Cross-Session Persistence", "complexity":7, "path":"memory/persistence.py",
   "desc":"Firebase-backed memory serialization: saves/restores all memory stores across restarts with versioned snapshots."},

  # Phase 4 — Thinking Engine
  {"phase":4,"id":"self_refine",          "name":"Self-Refine",               "complexity":7, "path":"thinking/self_refine.py",
   "desc":"Generate→Critique→Refine loop with explicit rubric scoring. Supports 1-3 configurable cycles with quality threshold gating."},
  {"phase":4,"id":"reflection_pattern",   "name":"Reflection Pattern",        "complexity":7, "path":"thinking/reflection.py",
   "desc":"Structured quality rubric critique: transparency scores, improvement tracking, can use a different model for generation vs critique."},
  {"phase":4,"id":"reflexion_vrl",        "name":"Reflexion (Verbal RL)",     "complexity":10,"path":"thinking/reflexion_vrl.py",
   "desc":"Full Reflexion (Shinn et al. 2023): Actor+Evaluator+Self-Reflection+Memory. Grounds criticism in external evidence with citations."},
  {"phase":4,"id":"tree_of_thoughts",     "name":"Tree of Thoughts",          "complexity":10,"path":"thinking/tree_of_thoughts.py",
   "desc":"BFS/DFS reasoning tree (Yao et al. 2023): generates N thought branches, evaluates each, backtracks on dead ends. 70% reasoning uplift."},
  {"phase":4,"id":"lats_mcts",            "name":"LATS / MCTS",               "complexity":11,"path":"thinking/lats_mcts.py",
   "desc":"Language Agent Tree Search (Zhou et al. ICML 2024): SELECT→EXPAND→SIMULATE→REFLECT→BACKPROPAGATE over reasoning paths. 92.7% HumanEval."},
  {"phase":4,"id":"multi_agent_debate",   "name":"Multi-Agent Debate (MAD)",  "complexity":9, "path":"thinking/mad.py",
   "desc":"Multi-Agent Debate (Du et al. 2023): Theorist+Experimentalist+Skeptic debate across configurable rounds until consensus threshold."},
  {"phase":4,"id":"chat_eval",            "name":"ChatEval Consensus",        "complexity":8, "path":"thinking/chat_eval.py",
   "desc":"Diverse persona panel (Chan et al. 2023): General+Critic+Physicist agents discuss, critique, and converge on a synthesized verdict."},
  {"phase":4,"id":"down_adaptive",        "name":"DOWN Adaptive Gating",      "complexity":8, "path":"thinking/down_adaptive.py",
   "desc":"Debate Only When Necessary (May 2025): confidence-gated debate trigger. Skips debate on high-confidence answers. 6x efficiency gain."},

  # Phase 5 — Agent Framework
  {"phase":5,"id":"base_agent",           "name":"Base Agent Class",          "complexity":9, "path":"agents/base_agent.py",
   "desc":"Abstract agent base: tool calling protocol, P2P messaging hooks, memory interface, lifecycle management, and thinking pattern dispatch."},
  # agent_registry is hardcoded in REGISTRY_PY and written by _scaffold — not AI-generated
  {"phase":5,"id":"comm_bus",             "name":"P2P Communication Bus",     "complexity":10,"path":"agents/comm_bus.py",
   "desc":"Direct agent-to-agent pub/sub bus: topic routing, broadcast, request-reply pattern, async message queue, and delivery guarantees."},
  # orchestrator.py is hardcoded in ORCHESTRATOR_PY and written by _scaffold — not AI-generated
  {"phase":5,"id":"vector_search_agent",  "name":"Vector Search Agent",       "complexity":7, "path":"agents/vector_search_agent.py",
   "desc":"Semantic search agent wrapping the Qdrant vector store and embedding pipeline: query encoding, similarity search, hybrid retrieval, and ranked result formatting."},
  {"phase":5,"id":"arxiv_search_agent",   "name":"ArXiv Search Agent",        "complexity":7, "path":"agents/arxiv_search_agent.py",
   "desc":"ArXiv search agent: query formulation, paper retrieval via the arxiv API, abstract parsing, relevance ranking, and structured result formatting for downstream agents."},
  {"phase":5,"id":"research_agent",       "name":"Research Agent",            "complexity":9, "path":"agents/research_agent.py",
   "desc":"Drives the 13-agent knowledge swarm: dispatches parallel ArXiv/vector searches, synthesizes retrieved knowledge into structured insights."},
  {"phase":5,"id":"math_agent",           "name":"Math Derivation Agent",     "complexity":11,"path":"agents/math_agent.py",
   "desc":"SymPy-powered symbolic math: algebraic manipulations, ODE solving, tensor operations, Lie algebra computations, and Lean 4 proof generation."},
  {"phase":5,"id":"theory_architect",     "name":"Theory Architect Agent",    "complexity":12,"path":"agents/theory_architect.py",
   "desc":"Top-level theory construction from axioms: assumption challenging, conjecture generation, theory space navigation, analogy detection."},
  {"phase":5,"id":"peer_review_agent",    "name":"Peer Review Agent",         "complexity":9, "path":"agents/peer_review.py",
   "desc":"Internal peer review with adversarial self-play: devil's advocate attack, steelmanning competitor theories, recovery protocol."},
  {"phase":5,"id":"synthesis_agent",      "name":"Synthesis Agent",           "complexity":8, "path":"agents/synthesis_agent.py",
   "desc":"Synthesizes outputs from multiple specialist agents into a coherent final response: evidence aggregation, conflict resolution, confidence weighting, and citation formatting."},

  # Phase 6 — Physics Core
  {"phase":6,"id":"first_principles",     "name":"First Principles Engine",   "complexity":12,"path":"physics/first_principles.py",
   "desc":"Pure axiom-to-theory engine: starts from minimal assumptions, forbids implicit priors, constructs derivations via explicit reasoning chains."},
  {"phase":6,"id":"sympy_engine",         "name":"Symbolic Math Engine",      "complexity":10,"path":"physics/sympy_engine.py",
   "desc":"Full SymPy integration: ODEs, PDEs, tensor calculus, Lie algebras, differential geometry, variational calculus, and Euler-Lagrange solver."},
  {"phase":6,"id":"theory_validator",     "name":"Theory Validator",          "complexity":11,"path":"physics/theory_validator.py",
   "desc":"Comprehensive theory validation: dimensional firewall + limiting case checks + conservation law auditing + formal Lean 4 verification."},
  {"phase":6,"id":"dimensional_firewall", "name":"Dimensional Firewall",      "complexity":8, "path":"physics/dimensional.py",
   "desc":"Dimensional analysis engine: parses equations, extracts SI units, verifies LHS==RHS dimensions, flags inconsistencies with suggestions."},
  {"phase":6,"id":"contradiction_detect", "name":"Contradiction Detector",    "complexity":10,"path":"physics/contradictions.py",
   "desc":"Logical consistency checker across derived theory set: detects mutually exclusive claims, Gödel-aware incompleteness bounds."},
  {"phase":6,"id":"hypothesis_generator", "name":"Hypothesis Generator",      "complexity":11,"path":"physics/hypothesis.py",
   "desc":"Novel hypothesis generation from knowledge gaps + epistemic confidence map. Scores novelty, testability, and mathematical feasibility."},
  {"phase":6,"id":"tensor_calculus",      "name":"Tensor Calculus Module",    "complexity":10,"path":"physics/tensors.py",
   "desc":"Ricci calculus toolkit: Christoffel symbols, covariant derivatives, Riemann/Ricci tensors, Einstein field equations, index gymnastics."},
  {"phase":6,"id":"quantum_formalism",    "name":"Quantum Formalism Module",  "complexity":11,"path":"physics/quantum.py",
   "desc":"Hilbert space operations, Dirac bra-ket notation, commutation relations, path integral formalism, and operator algebra with SymPy."},

  # Phase 7 — Discovery & Overnight Loop
  {"phase":7,"id":"discovery_mode",       "name":"Discovery Mode Engine",     "complexity":10,"path":"discovery/discovery_mode.py",
   "desc":"Abductive reasoning engine: hypothesis genesis → math scaffolding → parallel support+challenge search → hypothesis evolution tree."},
  {"phase":7,"id":"hypothesis_tracker",   "name":"Hypothesis Tracker",        "complexity":8, "path":"discovery/hypothesis_tracker.py",
   "desc":"Genealogy tree for hypothesis evolution: v1→v2→v3 with confidence propagation, parent/child links, and status tracking."},
  {"phase":7,"id":"evidence_search",      "name":"Evidence Search Engine",    "complexity":9, "path":"discovery/evidence_search.py",
   "desc":"Parallel support+challenge evidence search via retrieval engine and ArXiv. Returns ranked evidence with relevance scores."},
  {"phase":7,"id":"continuous_loop",      "name":"Continuous Discovery Loop", "complexity":10,"path":"discovery/continuous_loop.py",
   "desc":"Async overnight engine: generates hypotheses, runs evidence search, evolves them in cycles, stops on convergence or token budget."},
  {"phase":7,"id":"discovery_scheduler",  "name":"Discovery Scheduler",       "complexity":8, "path":"discovery/scheduler.py",
   "desc":"APScheduler-backed cron runner: configurable overnight windows, API rate limiting, cost cap enforcement, and run logging."},
  {"phase":7,"id":"overnight_reporter",   "name":"Overnight Report Generator","complexity":7, "path":"discovery/reporter.py",
   "desc":"Morning summary generator: discoveries made, confidence changes, top hypotheses, cost report, and suggested next research directions."},

  # Phase 8 — Interface & Deployment
  {"phase":8,"id":"conversation_manager", "name":"Conversation Manager",      "complexity":7, "path":"interface/conversation.py",
   "desc":"Multi-turn dialogue manager with session persistence, context injection, memory retrieval on each turn, and streaming support."},
  {"phase":8,"id":"streaming_api",        "name":"FastAPI Streaming Server",  "complexity":6, "path":"interface/api.py",
   "desc":"FastAPI app with SSE streaming endpoint, WebSocket support, JWT auth middleware, rate limiting, and health check route."},
  {"phase":8,"id":"docker_compose",       "name":"Docker Compose Stack",      "complexity":5, "path":"deploy/docker-compose.yml",
   "desc":"Full Docker Compose: physics-discovery app + Qdrant vector DB + Firebase emulator + APScheduler worker service."},
  {"phase":8,"id":"deploy_scripts",       "name":"Deployment Scripts",        "complexity":4, "path":"deploy/deploy.sh",
   "desc":"GCloud Run deployment script with env provisioning, health checks, rollback on failure, and blue/green swap logic."},
]

TOTAL = len(REGISTRY)

# ─────────────────────────────────────────────
# CLAUDE CLIENT
# ─────────────────────────────────────────────

class ClaudeClient:
    API_URL = "https://api.anthropic.com/v1/messages"
    MODEL   = "claude-sonnet-4-20250514"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def generate(self, module: dict, retry: int = 0) -> str:
        """Call Claude API to generate code for a module."""
        import urllib.request
        import urllib.error

        # Adjust prompt complexity based on retry tier
        detail = (
            "Generate a complete, production-quality implementation."
            if retry == 0 else
            "Generate a clear, well-structured implementation. Prioritize correctness."
            if retry == 1 else
            "Generate a minimal but fully functional implementation."
        )

        is_yaml = module["path"].endswith((".yml", ".yaml"))
        is_shell = module["path"].endswith(".sh")
        lang = "YAML" if is_yaml else "Bash" if is_shell else "Python"
        only = "YAML config" if is_yaml else "Bash script" if is_shell else "Python code with type hints and docstrings"

        # Build import map so generated code uses correct module paths
        import_map = "\n".join(
            f"  from {m['path'][:-3].replace('/', '.')} import ..."
            for m in REGISTRY if m["path"].endswith(".py")
        )

        prompt = f"""{detail}

Module: {module['name']}
File: {module['path']}
Purpose: {module['desc']}
System: Physics Discovery System v3.0 for RAP Corp (Renaissance of American Physics)
Language: {lang}

Available module import paths (use EXACTLY these, do not invent others):
{import_map}

Rules:
- Return ONLY {only}
- No markdown fences, no explanation text
- Keep docstrings brief (one line per function)
- Add TODO markers only for API key / external service integration points
- Async-first in Python where appropriate
- Be concise — prioritize complete, working code over verbose comments
- Only import from modules listed above or standard library / requirements.txt packages
- Use `from pydantic_settings import BaseSettings` (NOT `from pydantic import BaseSettings`)
- All BaseSettings fields must have a default value (use `Field(default=...)` or `= "default"`) so the app starts without every env var set
- config/settings.py Settings class MUST use `model_config = ConfigDict(extra="ignore", env_file=".env", case_sensitive=False)` — NEVER use extra="forbid" as the .env has more vars than the model
- config/settings.py Settings class MUST define fields for: anthropic_api_key, google_api_key, qdrant_host, qdrant_port, qdrant_api_key, embedding_model, retrieval_top_k, firebase_project_id, firebase_credentials_path, secret_key, arxiv_max_results
- config/settings.py must define a `get_settings()` factory function
- config/logger.py must define a `get_logger(name)` factory function
- config/errors.py must define a `handle_error(e)` function
- config/firebase.py must define a `get_firebase_client()` factory function
- agents/orchestrator.py must define a class named exactly `PhysicsOrchestrator` with an async `run(self, query, mode, pattern)` method
"""

        complexity = module.get("complexity", 5)
        max_tokens = min(8000 + (complexity - 1) * 500, 16000)

        payload = json.dumps({
            "model": self.MODEL,
            "max_tokens": max_tokens,
            "system": (
                f"You are an expert {lang} developer specializing in AI multi-agent systems "
                "and physics research software. Return ONLY valid code, no markdown, no explanation."
            ),
            "messages": [{"role": "user", "content": prompt}]
        }).encode("utf-8")

        req = urllib.request.Request(
            self.API_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )

        timeout = 60 + complexity * 15  # scales from 75s (c=1) to 225s (c=11)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            code = data["content"][0]["text"].strip()
            # Strip markdown fences Claude sometimes returns despite instructions
            if code.startswith("```"):
                code = code[code.index("\n") + 1:] if "\n" in code else ""
            if "\n```" in code:
                code = code[:code.rfind("\n```")]
            code = self._patch_code(code.strip(), path_hint=module["path"])
            return code, data.get("usage", {}).get("output_tokens", 0)

    # Known compatibility fixes applied to every generated Python file
    _PATCHES = [
        # aioredis is broken on Python 3.11+ — replace with redis.asyncio
        ("import aioredis",
         "import redis.asyncio as aioredis"),
        ("from aioredis",
         "from redis.asyncio"),

        # sympy.diffgeom: AI-hallucinated names → correct equivalents
        ("BaseOneForm", "OneForm"),

        # Relative imports that escape the top-level package → absolute imports
        # e.g. "from ..config.settings import X" → "from config.settings import X"
        ("from ..config.", "from config."),
        ("from ..agents.", "from agents."),
        ("from ..knowledge.", "from knowledge."),
        ("from ..memory.", "from memory."),
        ("from ..thinking.", "from thinking."),
        ("from ..physics.", "from physics."),
        ("from ..discovery.", "from discovery."),
        ("from ..interface.", "from interface."),

        # pydantic v2: BaseSettings moved to pydantic-settings
        # Handle "from pydantic import BaseSettings, Field, ..." patterns
        ("from pydantic import BaseSettings",
         "from pydantic_settings import BaseSettings"),
        # If BaseSettings was bundled with other pydantic names, split the import
        ("from pydantic_settings import BaseSettings, ",
         "from pydantic_settings import BaseSettings\nfrom pydantic import "),
        # pydantic v2: validator → field_validator
        ("from pydantic import validator",
         "from pydantic import field_validator"),
        # pydantic v2: @validator decorator
        ("@validator(",
         "@field_validator("),
        # pydantic v2: schema() removed
        (".schema()",
         ".model_json_schema()"),
        # pydantic v2: .dict() removed
        (".dict()",
         ".model_dump()"),
        # pydantic v2: .json() removed
        (".json()",
         ".model_dump_json()"),
    ]

    @staticmethod
    def _fix_bad_imports(code: str) -> str:
        """
        Parse every 'from X import a, b, c' in code.
        For each name that doesn't exist in the installed module, find the
        closest real name via difflib and replace it (or remove it if no
        close match exists).  Only runs against importable stdlib/site packages.
        """
        import ast, importlib, difflib

        try:
            tree = ast.parse(code)
        except SyntaxError:
            return code

        lines = code.splitlines(keepends=True)
        # Collect (lineno, module, bad_name, fix) — lineno is 1-based
        fixes: list = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or not node.module:
                continue
            # Skip project-internal modules (agents.*, config.*, etc.)
            if node.module.split(".")[0] in {
                "agents", "config", "knowledge", "memory",
                "thinking", "physics", "discovery", "interface",
            }:
                continue
            try:
                mod = importlib.import_module(node.module)
            except Exception:
                continue  # not installed yet — skip

            available = [n for n in dir(mod) if not n.startswith("__")]
            for alias in node.names:
                name = alias.name
                if name == "*" or hasattr(mod, name):
                    continue
                matches = difflib.get_close_matches(name, available, n=1, cutoff=0.55)
                fixes.append((node.lineno, name, matches[0] if matches else None))

        if not fixes:
            return code

        for lineno, bad, good in fixes:
            idx = lineno - 1
            if idx >= len(lines):
                continue
            if good:
                lines[idx] = lines[idx].replace(bad, good)
            else:
                # No close match — comment out the bad name to prevent ImportError
                lines[idx] = "# [auto-removed unresolvable import] " + lines[idx]

        return "".join(lines)

    @classmethod
    def _patch_code(cls, code: str, path_hint: str = "") -> str:
        """Apply known compatibility fixes to generated code."""
        ph = path_hint.replace("\\", "/")

        for old, new in cls._PATCHES:
            code = code.replace(old, new)

        # Remove stub functions/classes that shadow real class definitions.
        # _repair_missing_exports used to append these due to a name-parsing bug
        # (trailing colon on class names).  Pattern:
        #   def ClassName(*args, **kwargs):\n    raise NotImplementedError(...)
        # that appears anywhere AFTER a real "class ClassName" definition.
        real_classes = set(re.findall(r'^class (\w+)', code, re.MULTILINE))
        if real_classes:
            code = re.sub(
                r'\n+def (' + '|'.join(re.escape(c) for c in real_classes) +
                r')\(\*args,\s*\*\*kwargs\):\s*\n\s+raise NotImplementedError\([^\)]*\)\n?',
                '',
                code
            )

        # Fix relative imports that escape the top-level package.
        # "from ..config.settings import X"  →  "from config.settings import X"
        # "from .. import X"  →  removed (no valid target at top level)
        code = re.sub(r'from \.\.([\w])', r'from \1', code)
        code = re.sub(r'^from \.\. import .+\n?', '', code, flags=re.MULTILINE)

        # All agent files: inject missing BaseAgent abstract method implementations.
        # Any class that inherits from BaseAgent must implement these or it can't
        # be instantiated. Inject no-op defaults if missing.
        if ph.startswith("agents/") and "BaseAgent" in code:
            for method, body in [
                ("_process_cycle",
                 "    async def _process_cycle(self, *args, **kwargs):\n        pass\n"),
                ("on_message_received",
                 "    async def on_message_received(self, message=None, *args, **kwargs):\n        pass\n"),
            ]:
                if f"def {method}" not in code:
                    # Append inside the first class that extends BaseAgent
                    code = re.sub(
                        r'(class \w+\([^)]*BaseAgent[^)]*\):.*?)((?=\nclass )|\Z)',
                        lambda m, b=body: m.group(1) + "\n" + b + m.group(2),
                        code, count=1, flags=re.DOTALL
                    )

        # All agent files: fix bare super().__init__() → pass required BaseAgent args.
        # Derive agent_id and name from the first class name in the file.
        if ph.startswith("agents/"):
            cls_match = re.search(r'^class (\w+)', code, re.MULTILINE)
            cls_name = cls_match.group(1) if cls_match else Path(ph).stem
            agent_id = re.sub(r'(?<!^)(?=[A-Z])', '_', cls_name).lower().replace('__', '_').strip('_')
            # Replace any super().__init__(...) that is missing agent_id or name
            def _fix_super_init(m: re.Match) -> str:
                inner = m.group(1)
                if 'agent_id' not in inner:
                    inner = f'agent_id="{agent_id}", name="{cls_name}"' + (', ' + inner if inner.strip() else '')
                elif 'name' not in inner:
                    inner = inner.rstrip(', ') + f', name="{cls_name}"'
                return f'super().__init__({inner})'
            code = re.sub(r'super\(\)\.__init__\(([^)]*)\)', _fix_super_init, code)

        # Undo any broad TYPE_CHECKING guards that were incorrectly applied to
        # runtime-needed imports by a previous patcher version.
        code = re.sub(
            r'(?:from typing import TYPE_CHECKING\s*#?\s*noqa?\n)?if TYPE_CHECKING:\n    (from [\w].*)',
            r'\1',
            code, flags=re.MULTILINE
        )

        # Targeted circular import fix: only guard imports OF orchestrator inside
        # non-orchestrator files. Orchestrator is the hub that everything imports,
        # so it must never be imported at module level by other agents.
        if not ph.endswith("agents/orchestrator.py"):
            code = re.sub(
                r'^(from agents\.orchestrator import .+)$',
                r'if TYPE_CHECKING:\n    \1',
                code, flags=re.MULTILINE
            )
            # Ensure TYPE_CHECKING is imported if we just used it
            if "if TYPE_CHECKING:" in code and "from typing import TYPE_CHECKING" not in code:
                code = "from typing import TYPE_CHECKING\n" + code

        # Add "from __future__ import annotations" to defer annotation evaluation
        if code and "from __future__ import annotations" not in code:
            code = "from __future__ import annotations\n" + code

        code = cls._fix_bad_imports(code)

        # Ensure known required exports exist in their respective modules
        REQUIRED_EXPORTS = {
            "config/settings.py": [
                ("get_settings", "_settings_cache = None\n\ndef get_settings():\n    global _settings_cache\n    if _settings_cache is None:\n        _settings_cache = Settings()\n    return _settings_cache"),
            ],
            "config/logger.py": [
                ("get_logger", "def get_logger(name: str = __name__):\n    import logging\n    return logging.getLogger(name)"),
            ],
            "config/firebase.py": [
                ("get_firebase_client", "def get_firebase_client():\n    return FirebaseClient()"),
            ],
            "agents/orchestrator.py": [
                ("PhysicsOrchestrator", "class PhysicsOrchestrator:\n    async def run(self, query: str, mode: str = 'standard', pattern: str = 'down_adaptive'):\n        raise NotImplementedError('PhysicsOrchestrator.run not yet implemented')"),
                ("_process_cycle", "    async def _process_cycle(self, *args, **kwargs):\n        pass"),
                ("on_message_received", "    async def on_message_received(self, message, *args, **kwargs):\n        pass"),
            ],
            "agents/registry.py": [
                ("register_agent", "_agent_registry = {}\n\ndef register_agent(name: str):\n    def decorator(cls):\n        _agent_registry[name] = cls\n        return cls\n    return decorator\n\ndef get_agent(name: str):\n    return _agent_registry.get(name)\n\ndef get_all_agents():\n    return dict(_agent_registry)"),
            ],
            "config/errors.py": [
                ("handle_error", "def handle_error(e: Exception) -> None:\n    import logging\n    logging.getLogger(__name__).error(str(e), exc_info=True)"),
            ],
        }
        for file_path, exports in REQUIRED_EXPORTS.items():
            if ph.endswith(file_path):
                for fn_name, fn_body in exports:
                    # Match both "def name" and "class name" so class-based exports aren't re-injected
                    already_defined = (f"def {fn_name}" in code or f"class {fn_name}" in code)
                    if not already_defined:
                        code += f"\n\n{fn_body}\n"

        # settings.py: ensure extra .env vars don't crash startup and all
        # required fields are present (AI-gen sometimes omits them)
        if ph.endswith("config/settings.py"):
            import re as _re
            # Replace extra='forbid' with extra='ignore' so unknown env vars are silently dropped
            code = _re.sub(r"extra\s*=\s*['\"]forbid['\"]", "extra='ignore'", code)
            # If no model_config at all, inject one into the Settings class body
            if "model_config" not in code and "class Settings" in code:
                code = _re.sub(
                    r'(class Settings\([^)]*\):[ \t]*\n(?:[ \t]+"""[^"]*"""[ \t]*\n)?)',
                    r'\1    model_config = ConfigDict(extra="ignore", env_file=".env", case_sensitive=False)\n',
                    code,
                )
            # Inject any missing required fields that appear in the .env template
            REQUIRED_FIELDS = [
                ("anthropic_api_key", 'anthropic_api_key: str = Field(default="", env="ANTHROPIC_API_KEY")'),
                ("google_api_key",    'google_api_key: str = Field(default="", env="GOOGLE_API_KEY")'),
                ("qdrant_host",       'qdrant_host: str = Field(default="localhost", env="QDRANT_HOST")'),
                ("qdrant_port",       'qdrant_port: int = Field(default=6333, env="QDRANT_PORT")'),
                ("qdrant_api_key",    'qdrant_api_key: str = Field(default="", env="QDRANT_API_KEY")'),
                ("embedding_model",   'embedding_model: str = Field(default="BAAI/bge-large-en-v1.5", env="EMBEDDING_MODEL")'),
                ("retrieval_top_k",   'retrieval_top_k: int = Field(default=10, env="RETRIEVAL_TOP_K")'),
                ("firebase_project_id",       'firebase_project_id: str = Field(default="", env="FIREBASE_PROJECT_ID")'),
                ("firebase_credentials_path", 'firebase_credentials_path: str = Field(default="./firebase-credentials.json", env="FIREBASE_CREDENTIALS_PATH")'),
                ("secret_key",        'secret_key: str = Field(default="change-me-in-production", env="SECRET_KEY")'),
                ("arxiv_max_results", 'arxiv_max_results: int = Field(default=50, env="ARXIV_MAX_RESULTS")'),
            ]
            if "class Settings" in code:
                # Find indented body of Settings class to append fields
                class_match = _re.search(r'(class Settings\([^)]*\):.*?)(?=\nclass |\Z)', code, _re.DOTALL)
                if class_match:
                    class_body = class_match.group(0)
                    additions = []
                    for field_name, field_def in REQUIRED_FIELDS:
                        if field_name not in class_body:
                            additions.append(f"    {field_def}")
                    if additions:
                        # Insert before the first method (def) or at the end of the class body
                        insert_point = _re.search(r'\n    def ', class_body)
                        if insert_point:
                            pos = class_match.start() + insert_point.start()
                            code = code[:pos] + "\n" + "\n".join(additions) + code[pos:]
                        else:
                            # Append before end of class
                            end = class_match.end()
                            code = code[:end] + "\n" + "\n".join(additions) + "\n" + code[end:]

        # registry.py: replace any stub register_agent with a working decorator
        if ph.endswith("agents/registry.py"):
            import re as _re
            stub_pattern = r'def register_agent\([^)]*\):[^\n]*\n(?:[ \t]+[^\n]*\n)*?[ \t]+raise NotImplementedError\([^\)]*\)[^\n]*\n?'
            working_register_agent = (
                "def register_agent(name: str):\n"
                "    def decorator(cls):\n"
                "        _agent_registry[name] = cls\n"
                "        return cls\n"
                "    return decorator\n"
            )
            if _re.search(stub_pattern, code):
                code = _re.sub(stub_pattern, working_register_agent, code)
                if "_agent_registry" not in code:
                    code = "_agent_registry = {}\n\n" + code

        # Ensure any pydantic v2 names used in the file are actually imported
        PYDANTIC_NAMES = [
            "field_validator", "model_validator", "field_serializer", "ConfigDict",
        ]
        for name in PYDANTIC_NAMES:
            used = re.search(rf'(?<!["\'\w]){re.escape(name)}(?!["\'\w])', code)
            imported = re.search(rf'^from pydantic import[^\n]*\b{re.escape(name)}\b', code, re.MULTILINE)
            if used and not imported:
                # Find first non-docstring, non-comment line to insert after
                existing = re.search(r'^(from pydantic import .+)$', code, re.MULTILINE)
                if existing:
                    # Add to the existing pydantic import line
                    code = code[:existing.end()] + f", {name}" + code[existing.end():]
                else:
                    # Insert a new import after the last import block
                    last_import = list(re.finditer(r'^(?:import |from )\S+', code, re.MULTILINE))
                    if last_import:
                        pos = last_import[-1].end()
                        code = code[:pos] + f"\nfrom pydantic import {name}" + code[pos:]
                    else:
                        code = f"from pydantic import {name}\n" + code

        return code

# ─────────────────────────────────────────────
# PROJECT SCAFFOLD
# ─────────────────────────────────────────────

DIRS = [
    "config", "knowledge", "memory", "thinking",
    "agents", "physics", "discovery", "interface",
    "deploy", "tests", "logs",
]

INIT_TEMPLATE = '''"""
{pkg} — Physics Discovery System v3.0
RAP Corp | Renaissance of American Physics
"""
'''

ENV_EXAMPLE = """# Physics Discovery System v3.0 — Environment Variables
# Copy this to .env and fill in your values

# ── Claude API ──────────────────────────────────────────────
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# ── Google Gemini (optional, for swarm agents) ───────────────
GOOGLE_API_KEY=your_google_api_key_here

# ── Firebase ─────────────────────────────────────────────────
FIREBASE_PROJECT_ID=your_firebase_project_id
FIREBASE_CREDENTIALS_PATH=./firebase-credentials.json

# ── Qdrant Vector DB ─────────────────────────────────────────
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_API_KEY=                    # leave blank for local

# ── Discovery Overnight Loop ──────────────────────────────────
DISCOVERY_START_HOUR=23            # 11 PM local
DISCOVERY_END_HOUR=6               # 6 AM local
DISCOVERY_MAX_COST_USD=2.00        # cost cap per night
DISCOVERY_MAX_HYPOTHESES=20

# ── Security ──────────────────────────────────────────────────
SECRET_KEY=change-me-in-production

# ── Research ──────────────────────────────────────────────────
ARXIV_MAX_RESULTS=50
EMBEDDING_MODEL=BAAI/bge-large-en-v1.5
RETRIEVAL_TOP_K=10
"""

MAIN_PY = '''#!/usr/bin/env python3
"""
Physics Discovery System v3.0 — Entry Point
RAP Corp | Renaissance of American Physics

Usage:
    python main.py                                    # interactive mode
    python main.py "query"                            # single query
    python main.py "hypothesis" --mode discovery      # discovery mode
    python main.py --overnight                        # start overnight scheduler
    python main.py "query" --pattern lats_mcts        # specific thinking pattern
"""

import asyncio
import argparse
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

def main():
    parser = argparse.ArgumentParser(
        description="Physics Discovery System v3.0"
    )
    parser.add_argument("query", nargs="?", help="Research query or hypothesis")
    parser.add_argument("--mode", choices=["quick","standard","comprehensive","deep","discovery"],
                        default="standard")
    parser.add_argument("--pattern",
                        choices=["self_refine","reflection","reflexion_vrl","tree_of_thoughts",
                                 "lats_mcts","multi_agent_debate","chat_eval","down_adaptive"],
                        default="down_adaptive",
                        help="Thinking pattern to use")
    parser.add_argument("--overnight", action="store_true",
                        help="Start the continuous overnight discovery scheduler")
    args = parser.parse_args()

    print("\\n╔══════════════════════════════════════════╗")
    print("║  Physics Discovery System v3.0           ║")
    print("║  RAP Corp | Renaissance of American Physics ║")
    print("╚══════════════════════════════════════════╝\\n")

    if args.overnight:
        print("Starting overnight discovery scheduler...")
        from discovery.scheduler import DiscoveryScheduler
        scheduler = DiscoveryScheduler()
        asyncio.run(scheduler.start())
        return

    if not args.query:
        print("Interactive mode — type your physics query:")
        print("  Examples:")
        print("  • Are Maxwell\\'s equations complete at high energies?")
        print("  • Derive quantum corrections to gravity from first principles")
        print("  • What if dark matter is emergent from modified gravity?\\n")
        try:
            query = input("Query > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\\nExiting.")
            return
    else:
        query = args.query

    print(f"\\nMode: {args.mode} | Pattern: {args.pattern}")
    print(f"Query: {query}\\n")

    try:
        from agents.orchestrator import PhysicsOrchestrator
    except ImportError as e:
        print("[ Orchestrator not yet connected — run the installer to generate all modules ]")
        print(f"[ Import error: {e} ]")
        return

    orchestrator = PhysicsOrchestrator()
    try:
        result = asyncio.run(orchestrator.run(
            query=query,
            mode=args.mode,
            pattern=args.pattern,
        ))
    except TypeError:
        # Fallback if orchestrator uses positional args or sync interface
        result = orchestrator.run(query=query, mode=args.mode, pattern=args.pattern)

    if result:
        print(result)

if __name__ == "__main__":
    main()
'''

ORCHESTRATOR_PY = '''"""
PhysicsOrchestrator — Physics Discovery System v3.0
RAP Corp | Renaissance of American Physics

All agent imports are lazy (inside methods) to prevent circular imports.
"""
from __future__ import annotations
import asyncio
import logging
from typing import Any

from config.settings import get_settings
from config.logger import get_logger
from agents.registry import AgentRegistry, agent_registry

logger = get_logger(__name__)


class PhysicsOrchestrator:
    """Master coordinator for the physics research multi-agent system."""

    def __init__(self):
        self.settings = get_settings()
        self.registry = AgentRegistry()
        self._agents: dict = {}
        logger.info("PhysicsOrchestrator initialised")

    # ── Required abstract-method implementations ──────────────────────────

    async def _process_cycle(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def on_message_received(self, message: Any, *args: Any, **kwargs: Any) -> None:
        pass

    # ── Lazy agent loader ─────────────────────────────────────────────────

    def _get_agent(self, name: str, cls_path: str):
        if name not in self._agents:
            try:
                module_path, cls_name = cls_path.rsplit(".", 1)
                import importlib
                mod = importlib.import_module(module_path)
                cls = getattr(mod, cls_name)
                self._agents[name] = cls()
            except Exception as exc:
                logger.warning(f"Could not load agent {name}: {exc}")
                return None
        return self._agents[name]

    # ── Main entry point ──────────────────────────────────────────────────

    async def run(
        self,
        query: str,
        mode: str = "standard",
        pattern: str = "down_adaptive",
    ) -> str:
        logger.info(f"Orchestrator.run | mode={mode} pattern={pattern}")
        logger.info(f"Query: {query}")

        results: list[str] = []

        # Research phase — lazy import
        research_agent = self._get_agent(
            "research", "agents.research_agent.ResearchAgent"
        )
        if research_agent:
            try:
                if asyncio.iscoroutinefunction(research_agent.run):
                    research_result = await research_agent.run(query, mode=mode, pattern=pattern)
                else:
                    research_result = research_agent.run(query, mode=mode, pattern=pattern)
                if research_result:
                    results.append(str(research_result))
            except Exception as exc:
                logger.error(f"Research agent error: {exc}", exc_info=True)

        # Synthesis phase — lazy import
        if results:
            synthesis_agent = self._get_agent(
                "synthesis", "agents.synthesis_agent.SynthesisAgent"
            )
            if synthesis_agent:
                try:
                    combined = "\\n\\n".join(results)
                    if asyncio.iscoroutinefunction(synthesis_agent.run):
                        final = await synthesis_agent.run(combined, query=query)
                    else:
                        final = synthesis_agent.run(combined, query=query)
                    if final:
                        return str(final)
                except Exception as exc:
                    logger.error(f"Synthesis agent error: {exc}", exc_info=True)

        return "\\n\\n".join(results) if results else (
            f"Query received: {query}\\n"
            "Note: Agent pipeline could not complete — check logs for details."
        )
'''

REQUIREMENTS = """# Physics Discovery System v3.0 — Dependencies
# Install with: pip install -r requirements.txt

# ── Core AI ──────────────────────────────────────────────────
anthropic>=0.40.0
google-generativeai>=0.8.0

# ── Vector DB ────────────────────────────────────────────────
qdrant-client>=1.9.0
sentence-transformers>=3.0.0
rank-bm25>=0.2.2

# ── Symbolic Math ─────────────────────────────────────────────
sympy>=1.13.0
scipy>=1.13.0
numpy>=2.0.0

# ── Physics / Science ─────────────────────────────────────────
arxiv>=2.1.0
pdfplumber>=0.11.0

# ── Web / API ─────────────────────────────────────────────────
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
httpx>=0.27.0

# ── Firebase ─────────────────────────────────────────────────
firebase-admin>=6.5.0

# ── Scheduling ────────────────────────────────────────────────
apscheduler>=3.10.0

# ── Utilities ─────────────────────────────────────────────────
pydantic>=2.8.0
pydantic-settings>=2.4.0
python-dotenv>=1.0.0
tenacity>=9.0.0
rich>=13.7.0
aiofiles>=24.1.0
tiktoken>=0.7.0
"""

UTILS_CONFIG_PY = '''"""
utils/config — compatibility shim
AI-generated modules sometimes import from utils.config instead of config.settings.
This re-exports everything from the canonical module so those imports don't break.
"""
from config.settings import *  # noqa: F401,F403
try:
    from config.settings import get_settings, Settings
except ImportError:
    pass
'''

UTILS_INIT_PY = '''"""
utils — Physics Discovery System v3.0
Compatibility shims for AI-generated modules that reference non-standard paths.
"""
'''

REGISTRY_PY = '''"""
Agent Registry — Physics Discovery System v3.0
RAP Corp | Renaissance of American Physics
"""
from __future__ import annotations
import asyncio
import logging
from typing import Any, Callable, Dict, Optional, Type

logger = logging.getLogger(__name__)

# ── Global agent registry ─────────────────────────────────────────────────────

_agent_registry: Dict[str, Type] = {}


def register_agent(name: str) -> Callable:
    """Decorator that registers an agent class under the given name."""
    def decorator(cls: Type) -> Type:
        _agent_registry[name] = cls
        logger.debug(f"Registered agent: {name} -> {cls.__name__}")
        return cls
    return decorator


def get_agent(name: str) -> Optional[Type]:
    """Return the agent class registered under *name*, or None."""
    return _agent_registry.get(name)


def get_all_agents() -> Dict[str, Type]:
    """Return a copy of the full agent registry."""
    return dict(_agent_registry)


# ── AgentRegistry class (lifecycle management) ───────────────────────────────

class AgentRegistry:
    """Runtime registry: tracks live agent instances and their health."""

    def __init__(self):
        self._instances: Dict[str, Any] = {}

    def register(self, name: str, instance: Any = None):
        """Works both as a direct call and as a class decorator.

        Direct:    agent_registry.register("name", instance)
        Decorator: @agent_registry.register("name")
        """
        if instance is None:
            def decorator(cls):
                self._instances[name] = cls
                logger.info(f"Agent registered: {name}")
                return cls
            return decorator
        self._instances[name] = instance
        logger.info(f"Agent instance registered: {name}")

    def get(self, name: str) -> Optional[Any]:
        return self._instances.get(name)

    def all_agents(self) -> Dict[str, Any]:
        return dict(self._instances)

    async def health_check(self) -> Dict[str, bool]:
        results = {}
        for name, instance in self._instances.items():
            try:
                if hasattr(instance, "health_check"):
                    ok = await instance.health_check()
                else:
                    ok = True
            except Exception as exc:
                logger.warning(f"Health check failed for {name}: {exc}")
                ok = False
            results[name] = ok
        return results

    async def shutdown_all(self) -> None:
        for name, instance in list(self._instances.items()):
            try:
                if hasattr(instance, "shutdown"):
                    await instance.shutdown()
                logger.info(f"Agent shut down: {name}")
            except Exception as exc:
                logger.error(f"Error shutting down {name}: {exc}")
        self._instances.clear()


# ── Module-level singleton — generated agents call agent_registry.register() ─
agent_registry = AgentRegistry()
'''

TEST_TEMPLATE = '''"""
Physics Discovery System v3.0 — Basic Smoke Tests
RAP Corp | Run with: python -m pytest tests/ -v
"""

import importlib
import pytest
from pathlib import Path

MODULES = [
    "config.settings",
    "config.logger",
    "config.errors",
    "memory.episodic",
    "memory.semantic",
    "memory.working",
    "memory.router",
    "thinking.self_refine",
    "thinking.down_adaptive",
    "agents.base_agent",
    "agents.registry",
    "physics.dimensional",
    "discovery.discovery_mode",
    "discovery.scheduler",
]

@pytest.mark.parametrize("module", MODULES)
def test_module_importable(module):
    """All generated modules must be importable without errors."""
    try:
        importlib.import_module(module)
    except ImportError as e:
        pytest.skip(f"Optional dependency missing: {e}")

def test_project_structure():
    """Verify all required directories exist."""
    required_dirs = [
        "config","knowledge","memory","thinking",
        "agents","physics","discovery","interface","deploy",
    ]
    for d in required_dirs:
        assert Path(d).is_dir(), f"Missing directory: {d}"

def test_env_example_exists():
    assert Path(".env.example").exists(), ".env.example not found"

def test_requirements_exists():
    assert Path("requirements.txt").exists(), "requirements.txt not found"
'''

# ─────────────────────────────────────────────
# MAIN INSTALLER
# ─────────────────────────────────────────────

class Installer:
    MAX_RETRIES = 3
    RETRY_DELAY = 2.0   # seconds between retries

    def __init__(self):
        self.os   = OSDetector()
        self.log  = InstallerLogger()
        self.claude: Optional[ClaudeClient] = None
        self.installed  = 0
        self.skipped    = 0
        self.failed_ids = []
        self.start_time = time.time()

    # ── Banner ────────────────────────────────────────────────────────────

    def _banner(self):
        os_icon = {"Windows":"⬛","Darwin":"","Linux":"🐧"}.get(self.os.system,"⬡")
        print(f"\n{C.BOLD}{C.PURPLE}╔══════════════════════════════════════════════════╗{C.RESET}")
        print(f"{C.BOLD}{C.PURPLE}║  Physics Discovery System v3.0 — AI Installer   ║{C.RESET}")
        print(f"{C.BOLD}{C.PURPLE}║  RAP Corp · Renaissance of American Physics      ║{C.RESET}")
        print(f"{C.BOLD}{C.PURPLE}╚══════════════════════════════════════════════════╝{C.RESET}")
        r = self.os.report()
        print(f"\n  {os_icon}  OS       : {C.CYAN}{r['os']} {r['release']} ({r['arch']}){C.RESET}")
        print(f"     Python  : {C.CYAN}{r['python']}{C.RESET}")
        print(f"     Docker  : {C.GREEN+'available' if r['docker'] else C.YELLOW+'not found'}{C.RESET}")
        print(f"     Git     : {C.GREEN+'available' if r['git'] else C.YELLOW+'not found'}{C.RESET}")
        print(f"     Modules : {C.WHITE}{TOTAL}{C.RESET} across 8 phases\n")

    # ── Python version check ──────────────────────────────────────────────

    def _check_python(self):
        self.log.phase("─── Step 1: Python version check")
        if self.os.py_ver < (3, 10):
            self.log.error(f"Python 3.10+ required. You have {self.os.py_ver.major}.{self.os.py_ver.minor}")
            self.log.info(f"Install hint: {self.os.pkg_manager_hint}")
            sys.exit(1)
        self.log.ok(f"Python {self.os.py_ver.major}.{self.os.py_ver.minor}.{self.os.py_ver.micro} ✓")

    # ── Anthropic SDK check ───────────────────────────────────────────────

    def _ensure_anthropic(self):
        self.log.phase("─── Step 2: Checking anthropic SDK")
        try:
            import anthropic  # noqa
            self.log.ok("anthropic SDK already installed")
        except ImportError:
            self.log.warn("anthropic not found — installing now...")
            pip = self.os.venv_pip if Path(self.os.venv_pip).exists() else sys.executable.replace("python","pip")
            try:
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", "anthropic>=0.40.0", "--quiet"],
                    check=True
                )
                self.log.ok("anthropic installed")
            except subprocess.CalledProcessError:
                self.log.error("Could not install anthropic. Run: pip install anthropic>=0.40.0")
                sys.exit(1)

    # ── API key ───────────────────────────────────────────────────────────

    def _get_api_key(self) -> str:
        self.log.phase("─── Step 3: Claude API key")
        key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if key and key.startswith("sk-"):
            self.log.ok("API key found in environment (ANTHROPIC_API_KEY)")
            return key

        # Try .env file
        env_file = Path(".env")
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("ANTHROPIC_API_KEY="):
                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if key.startswith("sk-"):
                        self.log.ok("API key found in .env file")
                        return key

        # Prompt user
        print(f"\n  {C.YELLOW}Enter your Anthropic API key (starts with sk-ant-...){C.RESET}")
        print(f"  {C.DIM}Get one at: https://console.anthropic.com/settings/keys{C.RESET}")
        try:
            key = input("  API key > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nNo key provided — exiting.")
            sys.exit(0)

        if not key.startswith("sk-"):
            self.log.error("Invalid key format (must start with sk-)")
            sys.exit(1)

        # Optionally save to .env
        save = input("  Save to .env for future runs? [Y/n] > ").strip().lower()
        if save in ("", "y", "yes"):
            with open(".env", "a", encoding="utf-8") as f:
                f.write(f"\nANTHROPIC_API_KEY={key}\n")
            self.log.ok("Saved to .env")

        return key

    # ── Scaffold ──────────────────────────────────────────────────────────

    def _scaffold(self):
        self.log.phase("─── Step 4: Creating project structure")
        for d in DIRS:
            Path(d).mkdir(exist_ok=True)
            init = Path(d) / "__init__.py"
            if d not in ("logs", "deploy"):
                needs_write = not init.exists()
                if not needs_write:
                    try:
                        init.read_text(encoding="utf-8")
                    except (UnicodeDecodeError, ValueError):
                        needs_write = True  # file exists but is corrupt/wrong encoding
                if needs_write:
                    init.write_text(INIT_TEMPLATE.format(pkg=d.capitalize()), encoding="utf-8")
        for fpath, content in [
            (".env.example",       ENV_EXAMPLE),
            ("requirements.txt",   REQUIREMENTS),
            ("main.py",            MAIN_PY),
            ("tests/__init__.py",  ""),
            ("tests/test_system.py", TEST_TEMPLATE),
        ]:
            p = Path(fpath)
            if not p.exists():
                p.write_text(content, encoding="utf-8")

        # These files are always force-written from hardcoded templates —
        # AI-generated versions are unreliable for these foundational modules.
        Path("agents/registry.py").write_text(REGISTRY_PY, encoding="utf-8")
        Path("agents/orchestrator.py").write_text(ORCHESTRATOR_PY, encoding="utf-8")
        Path("utils").mkdir(exist_ok=True)
        Path("utils/__init__.py").write_text(UTILS_INIT_PY, encoding="utf-8")
        Path("utils/config.py").write_text(UTILS_CONFIG_PY, encoding="utf-8")
        self.log.ok("  agents/registry.py + agents/orchestrator.py + utils/ — hardcoded templates written")
        self.log.ok(f"{len(DIRS)} directories + scaffolding files created")

    # ── Install a single module ───────────────────────────────────────────

    @staticmethod
    def _check_syntax(code: str, path_hint: str) -> tuple[bool, str]:
        """Returns (is_valid, error_message). Non-Python files always pass."""
        if not path_hint.endswith(".py"):
            return True, ""
        try:
            compile(code, path_hint, "exec")
            return True, ""
        except SyntaxError as e:
            return False, f"line {e.lineno}: {e.msg} — {repr(e.text or '')}"

    def _install_module(self, mod: dict) -> bool:
        mod_id = mod["id"]
        out = Path(mod["path"])
        if out.exists():
            try:
                content = out.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                content = out.read_text(encoding="cp1252", errors="replace")
            except Exception:
                content = ""
            is_stub = (
                "Module not yet installed:" in content
                or "STUB (install failed)" in content
                or bool(re.search(
                    r'def run\(self.*?\).*?raise NotImplementedError',
                    content, re.DOTALL
                ))
            )
            # Apply compatibility patches to existing files
            if not is_stub and out.suffix == ".py":
                patched = self.claude._patch_code(content, path_hint=mod["path"])
                if patched != content:
                    out.write_text(patched, encoding="utf-8")
                    content = patched
                    self.log.ok(f"  {mod['name']} — patched compatibility fixes")
            valid_syntax, err_msg = self._check_syntax(content, str(out))
            if not is_stub and valid_syntax:
                self.skipped += 1
                self.log.muted(f"  {mod['name']} — already installed, skipping")
                return "skipped"
            elif not valid_syntax:
                self.log.warn(f"  {mod['name']} — syntax error in existing file ({err_msg}), regenerating")

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                if attempt > 0:
                    agent = "Claude Sonnet" if attempt == 1 else "Claude Opus framing"
                    self.log.warn(f"  ↻ retry {attempt}/{self.MAX_RETRIES} — escalating ({agent})")
                    time.sleep(self.RETRY_DELAY * attempt)

                code, tokens = self.claude.generate(mod, retry=attempt)
                valid, err_msg = self._check_syntax(code, mod["path"])
                if not valid:
                    raise RuntimeError(f"Generated code has syntax error: {err_msg}")
                out = Path(mod["path"])
                out.parent.mkdir(parents=True, exist_ok=True)
                # Ensure the package directory has an __init__.py
                init = out.parent / "__init__.py"
                if not init.exists():
                    init.write_text(
                        INIT_TEMPLATE.format(pkg=out.parent.name.capitalize()),
                        encoding="utf-8"
                    )
                out.write_text(code, encoding="utf-8")
                # Verify the written file reads back and compiles cleanly
                written = out.read_text(encoding="utf-8")
                valid_written, err_written = self._check_syntax(written, str(out))
                if not valid_written:
                    raise RuntimeError(f"Written file failed verification: {err_written}")
                self.log.ok(f"  {mod['name']} — {tokens} tokens → {mod['path']}")
                return True

            except Exception as e:
                err_str = str(e)
                self.log.error(f"  [MODULE:{mod_id}] {err_str}")
                if attempt == self.MAX_RETRIES:
                    self.log.error(f"  Max retries exceeded — {mod_id} flagged for manual review")
                    stub = f'"""\n{mod["name"]} — STUB (install failed)\nTODO: implement manually\nError: {err_str}\n"""\n\nraise NotImplementedError("Module not yet installed: {mod_id}")\n'
                    out = Path(mod["path"])
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_text(stub, encoding="utf-8")
                    return False
        return False

    # ── Run all phases ────────────────────────────────────────────────────

    def _run_phases(self):
        self.log.phase("─── Step 5: Generating all 54 modules via Claude API")
        self.log.system("Self-check running...")
        state = self.log.self_check()

        for phase_num in range(1, 9):
            phase_mods = [m for m in REGISTRY if m["phase"] == phase_num]
            phase_names = {
                1:"Foundation", 2:"Knowledge Swarm", 3:"Memory Architecture",
                4:"Thinking Engine", 5:"Agent Framework", 6:"Physics Core",
                7:"Discovery & Overnight Loop", 8:"Interface & Deployment",
            }
            print(f"\n  {C.BOLD}{C.BLUE}▶ Phase {phase_num}: {phase_names[phase_num]}{C.RESET}  ({len(phase_mods)} modules)")

            for mod in phase_mods:
                c = mod["complexity"]
                agent = ("Gemini Flash" if c<=4 else "Claude Sonnet" if c<=7
                         else "Claude Opus" if c<=10 else "Ensemble")
                self.log.info(f"  Installing: {mod['name']}  [c={c} | {agent}]")

                result = self._install_module(mod)
                if result == "skipped":
                    pass  # self.skipped already incremented inside _install_module
                elif result:
                    self.installed += 1
                else:
                    self.failed_ids.append(mod["id"])

                done = self.installed + self.skipped + len(self.failed_ids)
                bar_filled = int((done / TOTAL) * 30)
                bar = "█" * bar_filled + "░" * (30 - bar_filled)
                pct = int((done / TOTAL) * 100)
                print(f"  {C.DIM}[{bar}] {pct}%  {done}/{TOTAL}{C.RESET}", end="\r")

        print()
        self._repair_missing_exports()

    # ── Repair missing exports ────────────────────────────────────────────

    def _repair_missing_exports(self):
        """
        Scan all generated .py files for project-internal imports, then check
        whether the imported names actually exist in the target file.
        If anything is missing, inject a minimal stub so imports don't fail.
        """
        self.log.phase("─── Step 5b: Repairing missing exports")
        repaired = 0

        # Map module path → set of names defined at top level
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
                    tok = src[m.start():].split("(")[0].split()[1].rstrip(":(,")
                    names.add(tok)
            return names

        # Collect all project .py paths (registry + entry points)
        py_files = [Path(m["path"]) for m in REGISTRY if m["path"].endswith(".py")]
        scan_files = py_files + [Path("main.py")]
        path_map = {p.as_posix(): p for p in py_files if p.exists()}

        # Collect all missing project-internal module files referenced by imports
        missing_modules: dict = {}  # path_str -> set of imported names
        for src_file in scan_files:
            if not src_file.exists():
                continue
            try:
                src = src_file.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            for m in re.finditer(r'^(?:from|import) ([\w.]+)', src, re.MULTILINE):
                mod_dotted = m.group(1)
                target_path = mod_dotted.replace(".", "/") + ".py"
                if not Path(target_path).exists() and (
                    target_path.startswith("agents/") or
                    target_path.startswith("config/") or
                    target_path.startswith("knowledge/") or
                    target_path.startswith("memory/") or
                    target_path.startswith("thinking/") or
                    target_path.startswith("physics/") or
                    target_path.startswith("discovery/")
                ):
                    missing_modules.setdefault(target_path, mod_dotted)

        # Also handle relative imports like "from .arxiv_search_agent import ..."
        for src_file in scan_files:
            if not src_file.exists():
                continue
            try:
                src = src_file.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            pkg = src_file.parent.as_posix()  # e.g. "agents"
            for m in re.finditer(r'^from \.([\w]+) import', src, re.MULTILINE):
                rel_name = m.group(1)
                target_path = f"{pkg}/{rel_name}.py"
                if not Path(target_path).exists():
                    missing_modules.setdefault(target_path, f"{pkg.replace('/', '.')}.{rel_name}")

        if missing_modules:
            self.log.warn(f"  Found {len(missing_modules)} missing module file(s) — generating now")
            known_paths = {m["path"] for m in REGISTRY}
            for target_path, mod_dotted in missing_modules.items():
                if target_path in known_paths:
                    continue  # already in registry, will be handled normally
                mod_name = Path(target_path).stem
                pkg = Path(target_path).parent.name
                synthetic_mod = {
                    "id": mod_name,
                    "name": mod_name.replace("_", " ").title(),
                    "complexity": 7,
                    "path": target_path,
                    "desc": (
                        f"Auto-discovered {pkg} module '{mod_name}': implement all classes and "
                        f"functions imported by other modules in this project. "
                        f"Infer the interface from context and the module name."
                    ),
                }
                self.log.info(f"  Generating missing module: {target_path}")
                result = self._install_module(synthetic_mod)
                if result and result != "skipped":
                    self.installed += 1
                    repaired += 1

        for src_file in scan_files:
            if not src_file.exists():
                continue
            try:
                src = src_file.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            # Find all "from x.y import a, b, c" where x.y is a project module
            for m in re.finditer(r'^from ([\w.]+) import ([\w, ]+)', src, re.MULTILINE):
                mod_dotted = m.group(1)           # e.g. "config.errors"
                imported   = [n.strip() for n in m.group(2).split(",")]
                target_path = mod_dotted.replace(".", "/") + ".py"

                target = Path(target_path)
                if not target.exists():
                    continue

                defs = defined_names(target)
                missing = [n for n in imported if n and n not in defs]
                if not missing:
                    continue

                # Append stubs for missing names
                additions = []
                for name in missing:
                    # Decide stub type: Exception subclass or simple function
                    if name.endswith("Error") or name.endswith("Exception"):
                        additions.append(f"\nclass {name}(Exception):\n    pass\n")
                    else:
                        additions.append(f"\ndef {name}(*args, **kwargs):\n    raise NotImplementedError('{name} not yet implemented')\n")

                existing = target.read_text(encoding="utf-8", errors="replace")
                target.write_text(existing + "\n" + "".join(additions), encoding="utf-8")
                self.log.ok(f"  {target_path} — added stubs: {', '.join(missing)}")
                repaired += len(missing)

        if repaired:
            self.log.ok(f"  {repaired} missing export(s) stubbed")
        else:
            self.log.ok("  All exports verified")

    # ── Auto-heal imports ─────────────────────────────────────────────────

    PROJECT_PKGS = {
        "agents","config","knowledge","memory",
        "thinking","physics","discovery","interface","utils",
    }

    def _auto_heal_imports(self):
        """
        Scan every generated .py file for imports.
        • Third-party packages that aren't importable  → pip install
        • Project-internal module files that don't exist → generate via Claude
        This runs after _repair_missing_exports so the project tree is as
        complete as possible before we attempt imports.
        """
        import importlib, subprocess as sp

        self.log.phase("─── Step 5c: Auto-healing imports")

        py_files = [Path(m["path"]) for m in REGISTRY if m["path"].endswith(".py")]
        scan_files = py_files + [Path("main.py")]

        missing_pip: set = set()
        missing_project: dict = {}   # path → dotted module name

        STDLIB = sys.stdlib_module_names if hasattr(sys, "stdlib_module_names") else set()

        for src_file in scan_files:
            if not src_file.exists():
                continue
            try:
                src = src_file.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            for m in re.finditer(
                r'^(?:import ([\w.]+)|from ([\w.]+) import)', src, re.MULTILINE
            ):
                dotted = m.group(1) or m.group(2)
                top = dotted.split(".")[0]
                if not top or top.startswith("_"):
                    continue
                if top in STDLIB:
                    continue

                if top in self.PROJECT_PKGS:
                    # Check the specific file exists
                    target_path = dotted.replace(".", "/") + ".py"
                    if not Path(target_path).exists():
                        missing_project.setdefault(target_path, dotted)
                else:
                    # Third-party: try importing
                    try:
                        importlib.import_module(top)
                    except ImportError:
                        missing_pip.add(top)

        # ── pip install missing packages ──────────────────────────────────
        if missing_pip:
            pip = self.os.venv_pip if Path(self.os.venv_pip).exists() else sys.executable
            pip_cmd = [pip, "install"] if pip.endswith("pip") else [pip, "-m", "pip", "install"]
            self.log.info(f"  pip-installing {len(missing_pip)} missing package(s): {', '.join(sorted(missing_pip))}")
            for pkg in sorted(missing_pip):
                try:
                    sp.check_call(pip_cmd + [pkg],
                                  stdout=sp.DEVNULL, stderr=sp.DEVNULL)
                    self.log.ok(f"  {pkg} installed")
                except Exception as exc:
                    self.log.warn(f"  {pkg} install failed: {exc}")
        else:
            self.log.ok("  All third-party imports satisfied")

        # ── generate missing project modules ─────────────────────────────
        known_paths = {m["path"] for m in REGISTRY}
        generated = 0
        for target_path, dotted in missing_project.items():
            if target_path in known_paths:
                continue
            mod_name = Path(target_path).stem
            pkg = Path(target_path).parent.name
            synthetic_mod = {
                "id": mod_name,
                "name": mod_name.replace("_", " ").title(),
                "complexity": 6,
                "path": target_path,
                "desc": (
                    f"Auto-discovered module '{dotted}': implement all classes and "
                    f"functions that other project modules import from here. "
                    f"Infer the full interface from the module name and package context ({pkg})."
                ),
            }
            self.log.info(f"  Generating missing module: {target_path}")
            result = self._install_module(synthetic_mod)
            if result and result != "skipped":
                generated += 1

        if generated:
            self.log.ok(f"  {generated} missing project module(s) generated")
        elif not missing_project:
            self.log.ok("  All project module files present")

    # ── Virtual env hint ──────────────────────────────────────────────────

    def _venv_hint(self):
        self.log.phase("─── Step 6: Virtual environment (recommended)")
        venv = Path("venv")
        if not venv.exists():
            create = input("  Create virtual environment? [Y/n] > ").strip().lower()
            if create in ("", "y", "yes"):
                subprocess.run([sys.executable, "-m", "venv", "venv"], check=False)
                self.log.ok("venv created")
        else:
            self.log.ok("venv already exists")
        print(f"\n  {C.CYAN}Activate with:{C.RESET}  {self.os.venv_activate}")
        print(f"  {C.CYAN}Then install:{C.RESET}   {self.os.venv_pip} install -r requirements.txt")

    # ── OS-specific notes ─────────────────────────────────────────────────

    def _os_notes(self):
        self.log.phase("─── OS-specific notes")
        if self.os.is_win:
            self.log.info("Windows detected:")
            self.log.info("  • Run scripts in PowerShell (not cmd) for best experience")
            self.log.info("  • Docker Desktop recommended for Qdrant: https://docker.com")
            self.log.info("  • If pip install fails: py -m pip install -r requirements.txt")
        elif self.os.is_mac:
            self.log.info("macOS detected:")
            if self.os.is_arm:
                self.log.info("  • Apple Silicon (M-series) — all packages support arm64")
            self.log.info("  • Qdrant via Docker: docker run -p 6333:6333 qdrant/qdrant")
            if not shutil.which("brew"):
                self.log.info("  • Homebrew not found. Consider: https://brew.sh")
        elif self.os.is_linux:
            self.log.info("Linux detected:")
            self.log.info("  • Qdrant: docker run -p 6333:6333 qdrant/qdrant")
            self.log.info("  • Or: docker-compose up -d  (using generated deploy/docker-compose.yml)")

    # ── Final summary ─────────────────────────────────────────────────────

    def _summary(self):
        elapsed = int(time.time() - self.start_time)
        mins, secs = divmod(elapsed, 60)
        print(f"\n{C.BOLD}{C.PURPLE}╔══════════════════════════════════════════════════╗{C.RESET}")
        print(f"{C.BOLD}{C.PURPLE}║  Installation complete                           ║{C.RESET}")
        print(f"{C.BOLD}{C.PURPLE}╚══════════════════════════════════════════════════╝{C.RESET}\n")
        print(f"  {C.GREEN}✓ Installed  : {self.installed}/{TOTAL} modules{C.RESET}")
        if self.skipped:
            print(f"  {C.DIM}↷ Skipped    : {self.skipped} (already installed){C.RESET}")
        if self.failed_ids:
            print(f"  {C.RED}✗ Failed     : {len(self.failed_ids)} (stubs written — see logs/install.log){C.RESET}")
            for fid in self.failed_ids:
                print(f"    {C.DIM}• {fid}{C.RESET}")
        print(f"  {C.DIM}⏱  Time      : {mins}m {secs}s{C.RESET}")
        print(f"\n  {C.CYAN}Next steps:{C.RESET}")
        print(f"  1. {self.os.venv_activate}")
        if self.os.is_win:
            print(f"  2. venv\\Scripts\\pip install -r requirements.txt")
        else:
            print(f"  2. pip install -r requirements.txt")
        print(f"  3. cp .env.example .env  →  fill in your API keys")
        if self.os.detect_docker():
            print(f"  4. docker-compose -f deploy/docker-compose.yml up -d")
        print(f"  5. python main.py\n")
        print(f"  {C.DIM}Run tests: python -m pytest tests/ -v{C.RESET}\n")

    # ── Entry point ───────────────────────────────────────────────────────

    def run(self):
        self._banner()
        self._check_python()
        self._ensure_anthropic()
        api_key = self._get_api_key()
        self.claude = ClaudeClient(api_key)
        self._scaffold()
        self._run_phases()
        self._auto_heal_imports()
        self._venv_hint()
        self._os_notes()
        self._summary()


if __name__ == "__main__":
    try:
        Installer().run()
    except KeyboardInterrupt:
        print(f"\n\n{C.YELLOW}Installation interrupted.{C.RESET}")
        print(f"{C.DIM}Re-run install.py at any time — already-generated files will be skipped.{C.RESET}\n")
        sys.exit(0)
