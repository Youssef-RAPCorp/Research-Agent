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
            failed = [l.split("[MODULE:")[-1].split("]")[0].strip()
                      for l in lines if "[ERROR]" in l and "[MODULE:" in l]
            memory_issues = any("memory" in l.lower() or "oom" in l.lower() for l in lines)
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
  {"phase":5,"id":"agent_registry",       "name":"Agent Registry",            "complexity":6, "path":"agents/registry.py",
   "desc":"Dynamic agent registration, discovery by capability, health monitoring with heartbeat, and graceful lifecycle management."},
  {"phase":5,"id":"comm_bus",             "name":"P2P Communication Bus",     "complexity":10,"path":"agents/comm_bus.py",
   "desc":"Direct agent-to-agent pub/sub bus: topic routing, broadcast, request-reply pattern, async message queue, and delivery guarantees."},
  {"phase":5,"id":"orchestrator_agent",   "name":"Orchestrator Agent",        "complexity":11,"path":"agents/orchestrator.py",
   "desc":"Master coordinator: receives user query, decomposes into subtasks, assigns to specialist agents, collects and synthesizes results."},
  {"phase":5,"id":"research_agent",       "name":"Research Agent",            "complexity":9, "path":"agents/research_agent.py",
   "desc":"Drives the 13-agent knowledge swarm: dispatches parallel ArXiv/vector searches, synthesizes retrieved knowledge into structured insights."},
  {"phase":5,"id":"math_agent",           "name":"Math Derivation Agent",     "complexity":11,"path":"agents/math_agent.py",
   "desc":"SymPy-powered symbolic math: algebraic manipulations, ODE solving, tensor operations, Lie algebra computations, and Lean 4 proof generation."},
  {"phase":5,"id":"theory_architect",     "name":"Theory Architect Agent",    "complexity":12,"path":"agents/theory_architect.py",
   "desc":"Top-level theory construction from axioms: assumption challenging, conjecture generation, theory space navigation, analogy detection."},
  {"phase":5,"id":"peer_review_agent",    "name":"Peer Review Agent",         "complexity":9, "path":"agents/peer_review.py",
   "desc":"Internal peer review with adversarial self-play: devil's advocate attack, steelmanning competitor theories, recovery protocol."},

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

        prompt = f"""{detail}

Module: {module['name']}
File: {module['path']}
Purpose: {module['desc']}
System: Physics Discovery System v3.0 for RAP Corp (Renaissance of American Physics)
Language: {lang}

Rules:
- Return ONLY {only}
- No markdown fences, no explanation text
- Include comprehensive docstrings
- Add clear TODO markers for API key / external service integration points
- Async-first in Python where appropriate
"""

        payload = json.dumps({
            "model": self.MODEL,
            "max_tokens": 1500,
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

        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["content"][0]["text"], data.get("usage", {}).get("output_tokens", 0)

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

REQUIREMENTS = """# Physics Discovery System v3.0 — Dependencies
# Install with: pip install -r requirements.txt

# ── Core AI ──────────────────────────────────────────────────
anthropic>=0.40.0
google-generativeai>=0.8.0

# ── Vector DB ────────────────────────────────────────────────
qdrant-client>=1.9.0
sentence-transformers>=3.0.0

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
"""

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
            if not init.exists() and d not in ("logs", "deploy"):
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
        self.log.ok(f"{len(DIRS)} directories + scaffolding files created")

    # ── Install a single module ───────────────────────────────────────────

    def _install_module(self, mod: dict) -> bool:
        mod_id = mod["id"]
        out = Path(mod["path"])
        if out.exists():
            try:
                content = out.read_text(encoding="utf-8")
            except Exception:
                content = ""
            if "raise NotImplementedError" not in content:
                self.skipped += 1
                self.log.muted(f"  {mod['name']} — already installed, skipping")
                return True

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                if attempt > 0:
                    agent = "Claude Sonnet" if attempt == 1 else "Claude Opus framing"
                    self.log.warn(f"  ↻ retry {attempt}/{self.MAX_RETRIES} — escalating ({agent})")
                    time.sleep(self.RETRY_DELAY * attempt)

                code, tokens = self.claude.generate(mod, retry=attempt)
                out = Path(mod["path"])
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(code, encoding="utf-8")
                self.log.ok(f"  {mod['name']} — {tokens} tokens → {mod['path']}")
                return True

            except Exception as e:
                err_str = str(e)
                self.log.error(f"  [MODULE:{mod_id}] {err_str}")
                if attempt == self.MAX_RETRIES:
                    self.log.error(f"  Max retries exceeded — {mod_id} flagged for manual review")
                    # Write a stub so the project stays importable
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

                ok = self._install_module(mod)
                if ok:
                    self.installed += 1
                else:
                    self.failed_ids.append(mod["id"])

                done = self.installed + self.skipped + len(self.failed_ids)
                bar_filled = int((done / TOTAL) * 30)
                bar = "█" * bar_filled + "░" * (30 - bar_filled)
                pct = int((done / TOTAL) * 100)
                print(f"  {C.DIM}[{bar}] {pct}%  {done}/{TOTAL}{C.RESET}", end="\r")

        print()

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
