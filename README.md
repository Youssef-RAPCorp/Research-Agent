# Physics Discovery System v3.0 — AI Installer
**RAP Corp | Renaissance of American Physics**

---

## What this installer does

Runs `install.py` once and it will:

1. **Detect your OS** (Windows / macOS / Linux / Apple Silicon) and adapt paths, hints, and commands accordingly
2. **Check Python** — requires 3.10+
3. **Install the `anthropic` SDK** automatically if missing
4. **Ask for your Claude API key** — or reads it from `ANTHROPIC_API_KEY` env var or a `.env` file
5. **Create the full project directory tree** — 9 packages, scaffolding files, tests
6. **Generate all 54 modules** by calling the Claude API for each one:
   - Real production Python code with type hints and docstrings
   - Self-healing: up to 3 retries per module with escalating prompt complexity
   - Stubs written on permanent failure so the project stays importable
7. **Guide you through venv setup** and next steps

---

## Quick start

```bash
# 1 — unzip
unzip physics_discovery_v3_installer.zip
cd physics_discovery_v3_installer

# 2 — run (Python 3.10+ required)
python install.py
```

The installer will prompt for your API key if it is not already set.

---

## Setting your API key in advance (optional)

**Environment variable (recommended):**
```bash
# macOS / Linux
export ANTHROPIC_API_KEY=sk-ant-...

# Windows PowerShell
$env:ANTHROPIC_API_KEY="sk-ant-..."
```

**Or create a `.env` file:**
```
ANTHROPIC_API_KEY=sk-ant-...
```

Get a key at: https://console.anthropic.com/settings/keys

---

## Project structure after install

```
physics_discovery_v3/
├── install.py                  ← this installer
├── main.py                     ← entry point (generated)
├── requirements.txt            ← all Python deps
├── .env.example                ← fill in and rename to .env
│
├── config/                     ← Phase 1: Foundation
│   ├── settings.py
│   ├── logger.py               ← self-aware logger
│   ├── errors.py
│   └── firebase.py
│
├── knowledge/                  ← Phase 2: Knowledge Swarm (13 agents)
│   ├── qdrant_store.py
│   ├── embedder.py
│   ├── arxiv_fetcher.py
│   ├── retrieval.py            ← hybrid dense+sparse+rerank
│   └── ...
│
├── memory/                     ← Phase 3: Real-time Memory
│   ├── episodic.py             ← per-agent episodic store
│   ├── semantic.py             ← long-term facts with decay
│   ├── working.py              ← active context window
│   ├── reflexion_store.py      ← verbal RL memory
│   └── ...
│
├── thinking/                   ← Phase 4: All 8 Thinking Patterns
│   ├── self_refine.py
│   ├── reflexion_vrl.py        ← verbal RL (Shinn et al. 2023)
│   ├── tree_of_thoughts.py     ← BFS/DFS (Yao et al. 2023)
│   ├── lats_mcts.py            ← Monte Carlo Tree Search
│   ├── mad.py                  ← Multi-Agent Debate
│   ├── down_adaptive.py        ← 6x efficiency gating
│   └── ...
│
├── agents/                     ← Phase 5: Agent Framework
│   ├── base_agent.py
│   ├── comm_bus.py             ← P2P agent communication
│   ├── orchestrator.py
│   ├── math_agent.py           ← SymPy + Lean 4
│   ├── theory_architect.py
│   └── ...
│
├── physics/                    ← Phase 6: Physics Core
│   ├── first_principles.py
│   ├── sympy_engine.py
│   ├── dimensional.py          ← dimensional firewall
│   ├── tensors.py
│   ├── quantum.py
│   └── ...
│
├── discovery/                  ← Phase 7: Discovery & Overnight Loop
│   ├── discovery_mode.py       ← abductive reasoning
│   ├── continuous_loop.py      ← overnight engine
│   ├── scheduler.py            ← APScheduler cron
│   └── ...
│
├── interface/                  ← Phase 8: API & Deployment
│   ├── conversation.py
│   └── api.py                  ← FastAPI + SSE streaming
│
├── deploy/
│   ├── docker-compose.yml
│   └── deploy.sh
│
├── tests/
│   └── test_system.py
│
└── logs/
    └── install.log             ← installer reads this for self-healing
```

---

## After install

```bash
# Activate virtual environment
source venv/bin/activate          # macOS / Linux
venv\Scripts\activate             # Windows

# Install all dependencies
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your API keys

# Start Qdrant (requires Docker)
docker-compose -f deploy/docker-compose.yml up -d

# Run
python main.py

# Run overnight discovery
python main.py --overnight

# Run tests
python -m pytest tests/ -v
```

---

## System requirements

| Component | Minimum |
|-----------|---------|
| Python | 3.10+ |
| RAM | 4 GB |
| Disk | 500 MB |
| Anthropic API key | Required |
| Docker | Recommended (for Qdrant) |

---

*Built for RAP Corp — Renaissance of American Physics and Astronomy*

---

## License

Released under the [MIT License](LICENSE). All direct dependencies in
`requirements.txt` use permissive licenses (MIT, BSD, or Apache-2.0); none are copyleft.
