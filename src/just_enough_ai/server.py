"""FastAPI backend for Just-Enough-AI web/mobile UI."""

from pathlib import Path
from typing import Optional
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse
from pydantic import BaseModel

from .models import ExecutionMode, RunMetadata, ModelTier
from .profiler import get_gpu_headroom, assess_kv_headroom, NEMOTRON_SPECS
from .bridge import query_codebase_memory
from .router import determine_route, PRICING_TABLE
from .agent import run_task, run_speculative_draft, execute_agent_loop, AgentLoopEvent

app = FastAPI(title="Just-Enough-AI API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class RouteRequest(BaseModel):
    task: str
    mode: ExecutionMode = ExecutionMode.LOCAL
    force_tier: Optional[ModelTier] = None


class RunRequest(BaseModel):
    task: str
    mode: ExecutionMode = ExecutionMode.LOCAL
    force_tier: Optional[ModelTier] = None


def _detect_mode(requested: ExecutionMode) -> ExecutionMode:
    """Auto-elevate to REMOTE_CLOUD if explicitly requested or if no local GPU is detected."""
    if requested == ExecutionMode.REMOTE_CLOUD:
        return ExecutionMode.REMOTE_CLOUD
    headroom = get_gpu_headroom()
    return ExecutionMode.REMOTE_CLOUD if not headroom.gpu_available else ExecutionMode.LOCAL


@app.get("/api/profile")
def api_profile():
    headroom = get_gpu_headroom()
    mode = ExecutionMode.REMOTE_CLOUD if not headroom.gpu_available else ExecutionMode.LOCAL
    return {"hardware": headroom.model_dump(), "execution_mode": mode.value}


@app.post("/api/route")
def api_route(req: RouteRequest):
    mode = _detect_mode(req.mode)
    headroom = get_gpu_headroom()
    memory = query_codebase_memory(req.task)
    decision = determine_route(req.task, headroom, memory, mode=mode, force_tier=req.force_tier)
    return decision.model_dump()


@app.post("/api/run")
def api_run(req: RunRequest):
    mode = _detect_mode(req.mode)
    headroom = get_gpu_headroom()
    memory = query_codebase_memory(req.task)
    decision = determine_route(req.task, headroom, memory, mode=mode, force_tier=req.force_tier)

    def event_stream():
        yield f"data: [ROUTING] {decision.model_dump_json()}\n\n"
        for chunk in run_task(req.task, decision):
            if isinstance(chunk, RunMetadata):
                yield f"data: [METADATA] {chunk.model_dump_json()}\n\n"
            else:
                safe = chunk.replace("\n", "\\n")
                yield f"data: {safe}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


class SpeculativeRequest(BaseModel):
    task: str
    fallback_tier: ModelTier = ModelTier.SUPER


@app.post("/api/speculative")
def api_speculative(req: SpeculativeRequest):
    """Execute speculative agent drafting: Nano draft -> SteerLM Gate -> Warm-Start Promotion."""
    result = run_speculative_draft(
        task_description=req.task,
        preferred_fallback_tier=req.fallback_tier,
    )
    return result.model_dump()


@app.get("/api/kv-budget")
def api_kv_budget(tokens: int = Query(default=4000), tier: ModelTier = Query(default=ModelTier.NANO)):
    """Assess real-time GPU VRAM headroom and KV-cache footprint via NVML."""
    headroom = get_gpu_headroom()
    budget = assess_kv_headroom(active_tokens=tokens, tier=tier, headroom=headroom)
    return budget.model_dump()


@app.post("/api/loop")
def api_loop(req: RunRequest):
    """Execute multi-step agent tool loop with live SSE streaming events."""
    mode = _detect_mode(req.mode)

    def loop_stream():
        for event in execute_agent_loop(task_description=req.task, execution_mode=mode):
            if isinstance(event, AgentLoopEvent):
                yield f"data: [EVENT] {event.model_dump_json()}\n\n"
            elif isinstance(event, RunMetadata):
                yield f"data: [METADATA] {event.model_dump_json()}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(loop_stream(), media_type="text/event-stream")


@app.get("/api/pricing")
def api_pricing():
    return {
        tier.value: {
            "model_id": info["model_id"],
            "input_per_1m_usd": info["input_per_1m"],
            "output_per_1m_usd": info["output_per_1m"],
            "blended_per_1m_usd": info["blended_per_1m"],
        }
        for tier, info in PRICING_TABLE.items()
    }


@app.get("/api/files")
def api_files(root: str = Query(default=".")):
    ignore = {".venv", ".git", "__pycache__", "node_modules", ".ua"}
    root_path = Path(root).resolve()
    files = []
    for path in root_path.rglob("*"):
        if any(part in ignore for part in path.parts):
            continue
        if path.is_file():
            files.append(str(path.relative_to(root_path)).replace("\\", "/"))
    return {"root": str(root_path), "files": sorted(files)}


@app.get("/")
def serve_cockpit():
    html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>⚡ Just-Enough-AI Cockpit</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Plus+Jakarta+Sans:wght@400;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #090d16;
      --card-bg: #131b2e;
      --border: #23304c;
      --accent: #10b981;
      --accent-glow: rgba(16, 185, 129, 0.25);
      --text: #f1f5f9;
      --text-muted: #94a3b8;
      --code-bg: #0b1120;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Plus Jakarta Sans', sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
      padding: 1.25rem;
      max-width: 900px;
      margin: 0 auto;
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 1.5rem;
      padding-bottom: 1rem;
      border-bottom: 1px solid var(--border);
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 0.6rem;
      font-size: 1.4rem;
      font-weight: 700;
    }
    .badge-live {
      background: rgba(16, 185, 129, 0.15);
      color: var(--accent);
      border: 1px solid var(--accent);
      padding: 0.2rem 0.6rem;
      border-radius: 999px;
      font-size: 0.75rem;
      font-weight: 600;
    }
    .controls-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 0.75rem;
      margin-bottom: 1rem;
    }
    label {
      display: block;
      font-size: 0.8rem;
      font-weight: 600;
      color: var(--text-muted);
      margin-bottom: 0.35rem;
    }
    select, textarea {
      width: 100%;
      background: var(--card-bg);
      border: 1px solid var(--border);
      color: var(--text);
      border-radius: 8px;
      padding: 0.65rem 0.85rem;
      font-family: inherit;
      font-size: 0.95rem;
      outline: none;
      transition: border-color 0.2s;
    }
    select:focus, textarea:focus {
      border-color: var(--accent);
    }
    textarea {
      resize: vertical;
      min-height: 90px;
      margin-bottom: 0.75rem;
    }
    .btn-row {
      display: flex;
      gap: 0.5rem;
    }
    button {
      flex: 1;
      background: var(--accent);
      color: #042f1f;
      font-weight: 700;
      border: none;
      border-radius: 8px;
      padding: 0.75rem;
      cursor: pointer;
      font-size: 0.95rem;
      transition: transform 0.1s, box-shadow 0.2s;
      box-shadow: 0 4px 14px var(--accent-glow);
    }
    button:hover {
      transform: translateY(-1px);
    }
    button:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }
    .telemetry-card {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 0.85rem 1rem;
      margin-top: 1rem;
      display: none;
      font-size: 0.85rem;
    }
    .telemetry-card.visible { display: block; }
    .telemetry-row {
      display: flex;
      justify-content: space-between;
      margin-bottom: 0.35rem;
    }
    .telemetry-row:last-child { margin-bottom: 0; }
    .val-accent { color: var(--accent); font-weight: 600; }
    #output {
      margin-top: 1rem;
      background: var(--code-bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 1rem;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.85rem;
      line-height: 1.5;
      white-space: pre-wrap;
      min-height: 180px;
      max-height: 400px;
      overflow-y: auto;
    }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <span>⚡ Just-Enough-AI</span>
      <span class="badge-live">COCKPIT</span>
    </div>
    <div id="statusBadge" style="font-size: 0.8rem; color: var(--text-muted);">Ready</div>
  </header>

  <div class="controls-grid">
    <div>
      <label for="modeSelect">EXECUTION MODE</label>
      <select id="modeSelect">
        <option value="local">💻 Local (GPU profiling active)</option>
        <option value="remote" selected>📱 Remote / Cloud (Phone / Laptop off)</option>
      </select>
    </div>
    <div>
      <label for="tierSelect">FORCE TIER OVERRIDE</label>
      <select id="tierSelect">
        <option value="">🤖 Smart Dynamic Routing</option>
        <option value="nano">⚡ Force Nano (Omni)</option>
        <option value="super">⚖️ Force Super (120B)</option>
        <option value="ultra">🧠 Force Ultra (253B)</option>
      </select>
    </div>
  </div>

  <label for="task">CODING PROMPT / TASK</label>
  <textarea id="task" placeholder="Enter coding prompt, bug fix, or refactor task..."></textarea>

  <div class="btn-row">
    <button id="runBtn" onclick="runTask()">▶ Route & Execute</button>
  </div>

  <div id="telemetry" class="telemetry-card">
    <div class="telemetry-row">
      <span style="color:var(--text-muted);">Assigned Model:</span>
      <span id="telModel" class="val-accent">-</span>
    </div>
    <div class="telemetry-row">
      <span style="color:var(--text-muted);">Routing Reason:</span>
      <span id="telReason" style="font-size:0.75rem; text-align:right; max-width:65%;">-</span>
    </div>
    <div class="telemetry-row">
      <span style="color:var(--text-muted);">Actual Cost / Savings:</span>
      <span id="telCost" class="val-accent">-</span>
    </div>
    <div class="telemetry-row">
      <span style="color:var(--text-muted);">Tokens / Latency:</span>
      <span id="telTokens" style="color:var(--text-muted);">-</span>
    </div>
  </div>

  <div id="output">// Stream output will appear here...</div>

  <script>
    async function runTask() {
      const task = document.getElementById('task').value.trim();
      if (!task) return;

      const mode = document.getElementById('modeSelect').value;
      const forceTier = document.getElementById('tierSelect').value || null;
      const runBtn = document.getElementById('runBtn');
      const output = document.getElementById('output');
      const statusBadge = document.getElementById('statusBadge');
      const telemetry = document.getElementById('telemetry');
      const telModel = document.getElementById('telModel');
      const telReason = document.getElementById('telReason');
      const telCost = document.getElementById('telCost');
      const telTokens = document.getElementById('telTokens');

      runBtn.disabled = true;
      output.textContent = '';
      statusBadge.textContent = 'Connecting...';
      telemetry.classList.add('visible');
      telCost.textContent = 'Calculating...';
      telTokens.textContent = '-';

      try {
        const res = await fetch('/api/run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ task, mode, force_tier: forceTier }),
        });

        const reader = res.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;

          const text = decoder.decode(value);
          const lines = text.split('\\n');

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            const payload = line.slice(6);

            if (payload === '[DONE]') {
              statusBadge.textContent = 'Completed ✓';
            } else if (payload.startsWith('[ROUTING]')) {
              const d = JSON.parse(payload.slice(9));
              telModel.textContent = `${d.selected_tier.toUpperCase()} (${d.model_id})`;
              telReason.textContent = d.reasoning;
              statusBadge.textContent = `Streaming from ${d.selected_tier.toUpperCase()}...`;
            } else if (payload.startsWith('[METADATA]')) {
              const m = JSON.parse(payload.slice(10));
              telCost.textContent = `$${m.actual_cost_usd.toFixed(5)} (Saved $${m.savings_vs_ultra_usd.toFixed(5)} vs Ultra)`;
              telTokens.textContent = `${m.total_tokens} tokens (${m.prompt_tokens} in / ${m.completion_tokens} out) in ${m.latency_ms}ms`;
            } else {
              output.textContent += payload.replace(/\\\\n/g, '\\n');
              output.scrollTop = output.scrollHeight;
            }
          }
        }
      } catch (err) {
        output.textContent += '\\n[Error]: ' + err.message;
        statusBadge.textContent = 'Error';
      } finally {
        runBtn.disabled = false;
      }
    }
  </script>
</body>
</html>"""
    return HTMLResponse(content=html)
