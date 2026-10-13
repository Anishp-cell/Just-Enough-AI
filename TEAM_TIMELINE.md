# Just-Enough-AI — Team Task Timeline & Progress Tracker

> **Last Updated:** Current Session  
> **Target Milestone:** Nebius × NVIDIA Global AI Hackathon Submission  
> **Status Summary:** 🟢 Phase 1 Core Architecture 85% Complete. Ready for teammate handoffs.

---

## 📊 Live Progress Snapshot

| Teammate | Strategic Role | Tasks Completed | In Progress | Pending | Overall % |
|---|---|---|---|---|---|
| **Lead (You)** | The Brain & Systems Architect | 11 / 11 | 0 | 0 | **100%** |
| **Mayank** | The Sentinel (Cybersec Lead) | 0 / 6 | 0 | 6 | **0%** (Ready to start) |
| **Manjiri** | The Interface & Client Integration | 0 / 6 | 0 | 6 | **0%** (Ready to start) |
| **Data Lead** | The Evaluator (Benchmarks & Evals) | 1 / 4 | 0 | 3 | **25%** (Tasks V1 scaffolded) |

---

## 🗓️ Phase-by-Phase Timeline

```
PHASE 1: Foundation & Telemetry ───► PHASE 2: Grounding & Verification ───► PHASE 3: Breakthrough Upgrades ──► PHASE 4: Polish & Video
(Days 1 - 2)                        (Days 2 - 3)                            (Days 3 - 4)                     (Day 5)
• Core Routing & Enums [DONE]       • Local AST Memory Bridge [DONE]        • Speculative Agent Draft [DONE] • Benchmark Tables in README
• Nebius Streaming Runner [DONE]    • Mayank Subprocess Sandbox (M-1)       • NVML KV-Cache Governor [DONE]  • 3-Min Hackathon Demo Video
• FastAPI Backend & SSE [DONE]      • Mayank Adversarial Fuzzer (M-4)       • Nemotron SteerLM Gate [DONE]   • Slide Deck & Pitch
• Teammate Stubs [DONE]             • Self-Fix Escalation Loop [DONE]       • Diff AST Scope Lock (M-6)      • Final Git Tag & Submit
```

---

## 👤 Individual Member Task Breakdown

---

### 🧠 Lead — The Brain & Systems Architect

| # | Task | Target File(s) | Status | Est. Time | Notes / Acceptance Criteria |
|---|---|---|---|---|---|
| **L-1** | Define `ExecutionMode`, `RunMetadata`, update `RoutingDecision` | `models.py` | ✅ **DONE** | 15m | Pydantic models validated |
| **L-2** | Cloud-aware routing matrix + `--tier` force override | `router/engine.py` | ✅ **DONE** | 30m | No GPU penalty in remote mode; tested |
| **L-3** | Live Nebius streaming runner + exact token cost tracking | `agent/runner.py`, `agent/mock.py` | ✅ **DONE** | 25m | Captures usage, computes USD savings vs Ultra |
| **L-4** | FastAPI headless backend (`/api/profile`, `/api/route`, `/api/run` SSE) | `server.py` | ✅ **DONE** | 60m | Full REST + SSE server tested & verified |
| **L-5** | CLI telemetry panel & force flags | `cli.py` | ✅ **DONE** | 20m | Rich Run Summary card with cost & savings |
| **L-6** | AST & Symbol Codebase Memory Fallback Bridge | `bridge/devmind.py` | ✅ **DONE** | 25m | Local symbol indexer: grounded tasks auto-route to Nano (0.95 conf) |
| **L-7** | Multi-Step Agent Tool Loop (`read`, `write`, `test`) | `agent/loop.py` | ✅ **DONE** | 45m | Coordinates tool calls and state with silent json-repair hygiene |
| **L-8** | Agent Self-Fix & Dynamic Escalation (Nano → Super) | `agent/loop.py` | ✅ **DONE** | 30m | Auto-repairs code when gate/fuzzer detects crashes |
| **L-9** | **[Breakthrough #1]** Speculative Agentic Drafting Across Tiers | `agent/speculative.py` | ✅ **DONE** | 45m | Concurrent Nano draft (300ms) → AST check → Contrastive warm-start for Super/Ultra |
| **L-10** | **[Breakthrough #2]** Hardware-Headroom KV-Cache Governor | `profiler/kv_governor.py` | ✅ **DONE** | 45m | `pynvml` real-time VRAM budget + semantic AST KV pruning + cloud offload |
| **L-11** | **[Breakthrough #3]** In-Harness Nemotron SteerLM Multi-Attribute Verifier | `agent/steer_critic.py` | ✅ **DONE** | 40m | HelpSteer2 rubric runtime PR gate: Correctness, Regression, Safety scoring |

---

### 🛡️ Mayank — The Sentinel (Cybersecurity Lead)

| # | Task | Target File(s) | Status | Est. Time | Notes / Acceptance Criteria |
|---|---|---|---|---|---|
| **M-1** | Subprocess Sandbox (`run_in_sandbox`) | `src/just_enough_ai/agent/sandbox.py` | ⏳ **PENDING** | 45m | Hard 10s execution timeout; terminates infinite loops |
| **M-2** | Path Traversal Guard (`validate_safe_path`) | `src/just_enough_ai/agent/sandbox.py` | ⏳ **PENDING** | 20m | Blocks `../` and symlink escapes from project root |
| **M-3** | AST Security Invariant Linter | `src/just_enough_ai/security/linter.py` | ⏳ **PENDING** | 45m | Disallows `eval()`, `exec()`, hardcoded secrets/keys |
| **M-4** | Adversarial Boundary Fuzzer (`fuzz_generated_code`) | `src/just_enough_ai/security/fuzzer.py` | ⏳ **PENDING** | 60m | Synthesizes nulls, max integers, boundary cases |
| **M-5** | Telemetry Secret Masking | `src/just_enough_ai/telemetry/logger.py` | ⏳ **PENDING** | 25m | Redacts API keys & tokens from stdout and logs |
| **M-6** | **[Breakthrough #4]** Differential AST Scope Lock & Blast-Radius Guard | `src/just_enough_ai/security/ast_lock.py` | ⏳ **PENDING** | 45m | Freezes out-of-scope AST nodes; auto-reverts unauthorized mutations |

---

### 🎨 Manjiri — The Interface & Client Integration Lead

| # | Task | Target File(s) | Status | Est. Time | Notes / Acceptance Criteria |
|---|---|---|---|---|---|
| **UI-1** | Client-Side API Service & SSE Stream Consumer | Frontend repository / `web/` | ⏳ **PENDING** | 40m | `fetch('/api/run')`, decodes `[ROUTING]` & `[METADATA]` |
| **UI-2** | Mobile-First Responsive Cockpit UI | Frontend repository / `web/` | ⏳ **PENDING** | 60m | Mobile viewport layout, prompt bar, live output stream |
| **UI-3** | Real-Time Model Badge & Cost Telemetry Widget | Frontend repository / `web/` | ⏳ **PENDING** | 30m | Animated ticker showing "$0.003 spent / $0.021 saved" |
| **UI-4** | Mobile Repository File Explorer | Frontend repository / `web/` | ⏳ **PENDING** | 45m | Consumes `GET /api/files`, collapsible tree for phone |
| **UI-5** | Visual Code Diff Viewer | Frontend repository / `web/` | ⏳ **PENDING** | 45m | Syntax-highlighted green/red unified diff component |
| **UI-6** | Rich CLI Spinners & Status Polish | `src/just_enough_ai/cli.py` | ⏳ **PENDING** | 20m | Polished terminal output for desktop developers |

---

### 📊 Data Teammate — The Evaluator (Data & Benchmarks Lead)

| # | Task | Target File(s) | Status | Est. Time | Notes / Acceptance Criteria |
|---|---|---|---|---|---|
| **D-1** | Benchmark Task Dataset V1 (Initial Scaffold) | `data/benchmarks/tasks_v1.json` | ✅ **DONE** | 20m | 7 starter tasks across Nano, Super, Ultra |
| **D-2** | Expand Benchmark Suite to 50 Real-World Tasks | `data/benchmarks/tasks_v1.json` | ⏳ **PENDING** | 60m | 20 Simple (Nano), 20 Moderate (Super), 10 Complex (Ultra) |
| **D-3** | Collect 15 Boundary Edge-Cases for Fuzzing | `data/edge_cases/` | ⏳ **PENDING** | 45m | Off-by-one errors, null checks, overflow traps |
| **D-4** | Cost & Latency Benchmark Comparison Tables | `data/results/benchmark_report.md` | ⏳ **PENDING** | 60m | Records actual tokens & $ saved vs GPT-4o & pure Ultra |

---

## 🚦 Dependency Map (Who Unblocks Whom)

1. **Lead (L-4 FastAPI Server) ──► UNBLOCKS ──► Manjiri (UI-1, UI-2, UI-3)**  
   *Manjiri can build against `http://localhost:8000/api/run` immediately.*

2. **Lead (L-1 Models & Stubs) ──► UNBLOCKS ──► Mayank (M-1, M-2, M-4, M-6)**  
   *Mayank has exact function signatures in `sandbox.py`, `fuzzer.py`, and `ast_lock.py`.*

3. **Mayank (M-4 Fuzzer, M-6 AST Lock) + Lead (L-6 Memory) ──► UNBLOCKS ──► Lead (L-8 Self-Fix, L-9 Speculative Draft, L-11 SteerLM Gate)**  
   *The breakthrough agent execution engine uses Mayank's security primitives to provide verifiable, blast-radius-free code.*

4. **Data Lead (D-2 50 Tasks) + All Systems ──► UNBLOCKS ──► Benchmark Evaluation (D-4)**  
   *Final data runs to generate hackathon presentation charts.*

---

## 🎯 Daily Checkpoints

- **Checkpoint 1 (Today):** Backend core working, mobile cockpit prototype live, teammate contracts published.
- **Checkpoint 2 (Tomorrow):** Memory grounding active, Mayank's sandbox & fuzzer working, Manjiri's mobile UI streaming live tokens.
- **Checkpoint 3 (Day 3):** Full self-fix loop operational, 4 breakthrough upgrades implemented, 50-task benchmark suite evaluated.
- **Checkpoint 4 (Submission Eve):** 3-minute video demonstration recorded, repository polished, final submission submitted.
