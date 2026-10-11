# Just-Enough-AI — Teammate Onboarding & Context Brief

> **Welcome to the Just-Enough-AI team!**  
> We are competing in the **Nebius × NVIDIA Global AI Hackathon** (*Coding & Agentic Engineering Track*).  
> This document gives you the fast, complete context on what we are building, why it matters, how our system works, and exactly what your individual role is.

---

## 1. Quick Project Context (The 60-Second Pitch)

### The Problem
Commercial AI coding tools (Cursor, GitHub Copilot) cost $10–$60/month, and they burn expensive frontier model tokens on *everything* — even trivial one-line fixes. Other agentic tools like **Google Antigravity** require your physical laptop to stay awake, plugged in, and running locally; if your laptop is closed or out of battery, you cannot code from your phone.

### What We Are Building
**Just-Enough-AI (`jeai`)** is a cost-tiered, hardware- and memory-aware agentic coding harness powered by **NVIDIA Nemotron open models** hosted on **Nebius Token Factory**.

1. **Smart Model Routing:**
   - **Nemotron Nano (Omni):** $0.15 / 1M tokens. Used for grounded, routine tasks when context memory is high. (Saves >90% cost).
   - **Nemotron Super (120B):** $0.375 / 1M tokens. Balanced multi-file refactoring and feature building.
   - **Nemotron Ultra (253B):** $1.80 / 1M tokens. Frontier reasoning reserved for complex architecture overhauls.
2. **The "Antigravity Buster" (Laptop-OFF Mobile Cloud Coding):**
   - All AI models run on Nebius cloud GPUs.
   - You can pull out your smartphone on the subway, open our responsive web app, view the repo files, prompt the Nemotron agent, watch live streaming code generation, and approve commits to GitHub — **while your laptop is 100% powered off at home.**
3. **Verification Layer (Adversarial Fuzzing & Self-Fix):**
   - The agent doesn't blindly trust its own output. It automatically synthesizes hostile boundary test cases (nulls, overflows, edge cases), catches hallucinated bugs in a sandbox, and self-repairs code before presenting it to the user.

---

## 2. Core Repository Files to Read

| File | What It Contains | Who Should Read It |
|---|---|---|
| [`README.md`](file:///d:/python/Nvidia%20Hackathon/README.md) | Technical architecture diagram, CLI commands, Nebius pricing table, and setup guide. | **Everyone** |
| [`ROADMAP.md`](file:///d:/python/Nvidia%20Hackathon/ROADMAP.md) | The Master Engineering Roadmap. Contains task groups (TG 0 to TG 7), done-gates, and role breakdowns. | **Everyone** |
| [`.env.example`](file:///d:/python/Nvidia%20Hackathon/.env.example) | Environment variables template (`NEBIUS_API_KEY`, model names, mock mode toggle). | **Everyone** |
| [`pyproject.toml`](file:///d:/python/Nvidia%20Hackathon/pyproject.toml) / [`requirements.txt`](file:///d:/python/Nvidia%20Hackathon/requirements.txt) | Python project dependencies and setup configuration. | **Everyone** |
| [`src/just_enough_ai/models.py`](file:///d:/python/Nvidia%20Hackathon/src/just_enough_ai/models.py) | Data contracts (`ModelTier`, `HardwareHeadroom`, `MemoryContext`, `RoutingDecision`). | **Lead & Mayank** |
| [`src/just_enough_ai/cli.py`](file:///d:/python/Nvidia%20Hackathon/src/just_enough_ai/cli.py) | Current Typer & Rich terminal interface. | **Manjiri** |

---

## 3. Team Roles & Clear Ownership

```
                       ┌────────────────────────────────────────┐
                       │          Lead (You)                    │
                       │  • Core Routing Matrix (engine.py)     │
                       │  • Nebius Runner & Agent Loop          │
                       │  • FastAPI Backend (server.py)         │
                       └────┬──────────────┬───────────────┬────┘
                            │              │               │
        ┌───────────────────▼──┐   ┌───────▼───────────┐   └───▼──────────────────┐
        │  Mayank (Cybersec)   │   │  Manjiri (UI/UX)  │       │ Data Teammate (Evals)│
        │  • Process Sandbox   │   │  • Mobile Web App │       │ • 50-Task Benchmark  │
        │  • Adversarial Fuzz  │   │  • Live SSE Stream│       │ • Cost Comparison    │
        │  • AST Linter/Safety │   │  • Diff Viewer/CLI│       │ • Edge-Case Corpus   │
        └──────────────────────┘   └───────────────────┘       └──────────────────────┘
```

### 🛡️ Mayank — The Sentinel (Cybersecurity Lead)
* **Your Mission:** Make our agent execution completely safe, bulletproof, and self-verifying.
* **Key Tasks:**
  1. **Subprocess Sandbox (`agent/sandbox.py`):** Wrap agent tool calls and test executions in an isolated process with strict execution timeouts (e.g. 10s) and path validation to prevent unauthorized directory access.
  2. **Adversarial Fuzzing (`security/fuzzer.py`):** Parse generated code, synthesize hostile inputs (None, boundary integers, edge-case types), and catch runtime crashes before delivery.
  3. **AST Security Invariant Linter (`security/linter.py`):** Scan generated diffs to block hardcoded credentials, banned `eval()` calls, or dangerous imports.
  4. **Credential Isolation:** Ensure API keys and `.env` secrets are never leaked into logs or telemetry.

### 🎨 Manjiri — The Interface (UI/UX Lead)
* **Your Mission:** Build the user-facing interfaces, especially the mobile experience that proves our "Laptop-OFF" capability.
* **Key Tasks:**
  1. **Mobile-First Responsive Web Cockpit:** Build a modern, clean web interface (Vite/Tailwind or lightweight HTML/CSS) that works smoothly on mobile phone browsers:
     - Live Model Status Badge (active Nemotron tier + real-time cost meter).
     - Task input box with one-tap quick prompts.
     - Real-time streaming output pane (powered by Server-Sent Events / SSE from the backend).
  2. **Mobile Repo Explorer & Diff Viewer:** Allow users to browse repository files on their phone and review side-by-side or unified green/red diffs before approving commits.
  3. **CLI Polish (`cli.py`):** Add `--tier nano|super|ultra` override flags and Rich animated spinners.
  4. *(Desktop packaging via Electron is scheduled for the final phase).*

### 📊 Data Teammate — The Evaluator (Data & Benchmarks Lead)
* **Your Mission:** Deliver the empirical data, evaluation suites, and cost comparison proof that convinces the hackathon judges.
* **Key Tasks:**
  1. **Benchmark Task Suite (`data/benchmarks/tasks_v1.json`):** Curate 50 real-world developer tasks:
     - 20 Simple (docstrings, syntax errors, typos) → Nano targets.
     - 20 Moderate (function refactors, writing unit tests) → Super targets.
     - 10 Complex (cross-module architecture redesign) → Ultra targets.
  2. **Cost & Latency Comparison Tables:** Record token counts, latency, and costs across Nemotron tiers vs. standard flat-rate models (GPT-4o / Claude 3.5 Sonnet / pure Ultra) to prove our 70–90% cost savings claim.
  3. **Hallucination Test Corpus (`data/edge_cases/`):** Collect 15 subtle coding edge cases (off-by-one errors, null pointer traps) to evaluate Mayank's adversarial fuzzer.
  4. **Presentation Metrics:** Produce data tables and charts for the project README and presentation slides.

### 🧠 Lead — The Brain & Systems Architect
* **Mission:** Core routing engine, live Nebius streaming runner, multi-step agentic loop, devmind memory bridge, and FastAPI backend endpoints (`/api/profile`, `/api/route`, `/api/run`).

---

## 4. How to Get Started Locally (Step-by-Step)

```bash
# 1. Clone the repository
git clone https://github.com/Anishp-cell/Just-Enough-AI.git
cd Just-Enough-AI

# 2. Create and activate a virtual environment (using uv or venv)
uv venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

# 3. Install dependencies
uv pip install -r requirements.txt
uv pip install -e ".[dev]"

# 4. Set up environment variables
cp .env.example .env

# 5. Run test suite to verify baseline
pytest -q

# 6. Test the CLI in mock mode (no API key required!)
python -m just_enough_ai.cli profile
python -m just_enough_ai.cli pricing
python -m just_enough_ai.cli route "Write a binary search algorithm in Python"
python -m just_enough_ai.cli run "Write a binary search algorithm in Python"
```

---

## 5. Hackathon Submission Criteria

* **Models:** NVIDIA open-source models (Nemotron-3 Nano, Super-120B, Ultra-253B).
* **Infrastructure:** Nebius Token Factory on high-performance cloud GPUs.
* **Track:** Coding and Agentic Engineering.
* **Deliverable:** Working repository, mobile-first web app, CLI harness, benchmark data report, and a 3-minute video demo.
