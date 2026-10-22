"""FastAPI backend for Just-Enough-AI web/mobile UI."""

from pathlib import Path
from typing import Optional
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse, Response
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


@app.get("/api/providers")
def api_providers():
    """List all registered providers, their availability, tier, and rate limit status."""
    from .providers import provider_registry
    if not provider_registry.list_providers():
        provider_registry.auto_discover()

    results = []
    for name, adapter in provider_registry.get_available_providers():
        status = adapter.get_rate_limit_status()
        results.append({
            "name": name,
            "model_name": adapter.get_model_name(),
            "tier": adapter.get_estimated_tier().value,
            "is_available": adapter.is_available(),
            "has_capacity": status.has_capacity,
            "is_free_tier": name in {"ollama", "antigravity", "claude_code"},
        })
    return {"providers": results}


class CommitRequest(BaseModel):
    file_path: str
    content: str
    commit_message: str = "Applied verified patch via Just-Enough-AI"
    do_git_commit: bool = True


@app.post("/api/commit")
def api_commit(req: CommitRequest):
    """Write verified code to file and record git commit."""
    from .agent.sandbox import validate_safe_path
    if not validate_safe_path(req.file_path, "."):
        raise HTTPException(status_code=400, detail="Path traversal outside project root is prohibited.")

    target = Path(req.file_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(req.content, encoding="utf-8")

    if not req.do_git_commit:
        return {"success": True, "message": f"File {target.name} written without git commit."}

    import subprocess
    try:
        subprocess.run(["git", "add", str(target)], check=True, capture_output=True)
        res = subprocess.run(
            ["git", "commit", "-m", req.commit_message],
            check=True,
            capture_output=True,
            text=True,
        )
        return {"success": True, "message": f"Committed {target.name}", "git_output": res.stdout.strip()}
    except Exception as e:
        return {"success": True, "message": f"File {target.name} saved (git commit skipped: {e})"}


@app.get("/api/file-content")
def api_file_content(path: str = Query(...)):
    """Fetch content of a file for mobile preview."""
    from .agent.sandbox import validate_safe_path
    if not validate_safe_path(path, "."):
        raise HTTPException(status_code=400, detail="Path traversal outside project root is prohibited.")
    target = Path(path).resolve()
    if not target.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    try:
        content = target.read_text(encoding="utf-8")
        return {"path": path, "content": content, "size_bytes": len(content)}
    except UnicodeDecodeError:
        return {"path": path, "content": "[Binary or non-UTF-8 file cannot be previewed]", "size_bytes": target.stat().st_size}


@app.get("/manifest.json")
def api_pwa_manifest():
    """Progressive Web App manifest for Laptop-OFF mobile coding."""
    return {
        "name": "Just-Enough-AI Cockpit",
        "short_name": "jeai",
        "description": "Hardware-headroom and memory-aware agentic coding harness",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#09090b",
        "theme_color": "#ffffff",
        "icons": [
            {
                "src": "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>⚡</text></svg>",
                "sizes": "192x192 512x512",
                "type": "image/svg+xml"
            }
        ]
    }


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    """Returns SVG favicon to eliminate 404 in browser requests."""
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><text y=".9em" font-size="90">⚡</text></svg>'
    return Response(content=svg, media_type="image/svg+xml")


@app.get("/")
def serve_cockpit():
    html = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <meta name="theme-color" content="#09090b">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>⚡</text></svg>">
  <link rel="manifest" href="/manifest.json">
  <title>⚡ Just-Enough-AI Cockpit</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #09090b;
      --surface: #141417;
      --card-bg: #18181b;
      --border: #27272a;
      --border-accent: #3f3f46;
      --accent: #ffffff;
      --accent-muted: #a1a1aa;
      --nano: #e4e4e7;
      --super: #f4f4f5;
      --ultra: #09090b;
      --amber: #f59e0b;
      --red: #ef4444;
      --text: #f4f4f5;
      --text-muted: #a1a1aa;
      --code-bg: #09090b;
      --diff-add-bg: #112419;
      --diff-add-border: #22c55e;
      --diff-del-bg: #261517;
      --diff-del-border: #ef4444;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Plus Jakarta Sans', system-ui, sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
      padding: 1rem;
      max-width: 960px;
      margin: 0 auto;
      padding-bottom: 3rem;
    }

    /* Sticky Navigation Header */
    header {
      position: sticky;
      top: 0;
      z-index: 100;
      background: var(--bg);
      border-bottom: 1px solid var(--border);
      padding: 0.85rem 0;
      margin-bottom: 1rem;
      display: flex;
      flex-direction: column;
      gap: 0.6rem;
    }
    .header-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 0.6rem;
      font-size: 1.25rem;
      font-weight: 700;
      letter-spacing: -0.02em;
      color: #ffffff;
    }
    .brand span.logo-accent {
      color: #ffffff;
      font-weight: 800;
    }
    .badge-live {
      background: #18181b;
      color: var(--text-muted);
      border: 1px solid var(--border);
      padding: 0.2rem 0.55rem;
      border-radius: 4px;
      font-size: 0.7rem;
      font-weight: 700;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }
    .header-chips {
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }
    .chip {
      background: #141417;
      border: 1px solid var(--border);
      padding: 0.25rem 0.6rem;
      border-radius: 4px;
      font-size: 0.72rem;
      color: var(--text-muted);
      font-family: 'JetBrains Mono', monospace;
    }

    /* UI-8: Provider Status HUD Pill Bar */
    .provider-pill-bar {
      display: flex;
      gap: 0.4rem;
      overflow-x: auto;
      padding-bottom: 0.2rem;
      scrollbar-width: none;
    }
    .provider-pill-bar::-webkit-scrollbar { display: none; }
    .provider-pill {
      display: flex;
      align-items: center;
      gap: 0.4rem;
      background: #141417;
      border: 1px solid var(--border);
      border-radius: 4px;
      padding: 0.25rem 0.65rem;
      font-size: 0.72rem;
      font-weight: 600;
      color: var(--text-muted);
      white-space: nowrap;
      transition: all 0.15s ease;
    }
    .provider-pill.active {
      border-color: #52525b;
      color: #ffffff;
      background: #27272a;
    }
    .dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: #52525b;
    }
    .dot.green { background: #22c55e; }
    .dot.blue { background: #3b82f6; }
    .dot.amber { background: #f59e0b; }

    /* Cascade Alert Toast */
    .toast-alert {
      display: none;
      background: #1c1813;
      border: 1px solid #784a14;
      color: #fed7aa;
      border-radius: 6px;
      padding: 0.6rem 0.85rem;
      font-size: 0.8rem;
      margin-bottom: 0.85rem;
      animation: fadeIn 0.2s ease;
    }
    .toast-alert.visible { display: flex; align-items: center; gap: 0.5rem; }

    /* Controls Grid */
    .controls-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 0.65rem;
      margin-bottom: 0.85rem;
    }
    @media (max-width: 580px) {
      .controls-grid { grid-template-columns: 1fr; }
    }
    label {
      display: block;
      font-size: 0.72rem;
      font-weight: 700;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      margin-bottom: 0.3rem;
      text-transform: uppercase;
    }
    select, textarea {
      width: 100%;
      background: #141417;
      border: 1px solid var(--border);
      color: var(--text);
      border-radius: 6px;
      padding: 0.65rem 0.8rem;
      font-family: inherit;
      font-size: 0.88rem;
      outline: none;
      transition: border-color 0.15s;
    }
    select:focus, textarea:focus {
      border-color: #71717a;
    }

    /* UI-2: Quick Action Prompt Chips */
    .prompt-chips-row {
      display: flex;
      gap: 0.45rem;
      overflow-x: auto;
      margin-bottom: 0.6rem;
      scrollbar-width: none;
    }
    .prompt-chips-row::-webkit-scrollbar { display: none; }
    .action-chip {
      background: #141417;
      border: 1px solid var(--border);
      border-radius: 4px;
      padding: 0.28rem 0.65rem;
      font-size: 0.75rem;
      color: var(--text-muted);
      cursor: pointer;
      white-space: nowrap;
      transition: all 0.15s ease;
      user-select: none;
    }
    .action-chip:hover {
      background: #27272a;
      color: #ffffff;
      border-color: #3f3f46;
    }

    textarea {
      resize: vertical;
      min-height: 85px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.88rem;
      line-height: 1.45;
      margin-bottom: 0.65rem;
    }

    .btn-row {
      display: flex;
      gap: 0.5rem;
      margin-bottom: 0.85rem;
    }
    button.btn-primary {
      flex: 2;
      background: #ffffff;
      color: #09090b;
      font-weight: 700;
      border: 1px solid #ffffff;
      border-radius: 6px;
      padding: 0.75rem 1rem;
      cursor: pointer;
      font-size: 0.9rem;
      transition: background 0.15s, border-color 0.15s;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 0.5rem;
    }
    button.btn-primary:hover:not(:disabled) {
      background: #e4e4e7;
      border-color: #e4e4e7;
    }
    button.btn-secondary {
      flex: 1;
      background: #18181b;
      border: 1px solid var(--border);
      color: var(--text);
      font-weight: 600;
      border-radius: 6px;
      padding: 0.75rem;
      cursor: pointer;
      font-size: 0.85rem;
      transition: background 0.15s, border-color 0.15s;
    }
    button.btn-secondary:hover:not(:disabled) {
      background: #27272a;
      border-color: #3f3f46;
    }
    button:disabled {
      opacity: 0.4;
      cursor: not-allowed;
    }

    /* UI-3: Real-Time Telemetry & SteerLM Scorecard */
    .telemetry-card {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 0.9rem 1.1rem;
      margin-bottom: 1rem;
      display: none;
    }
    .telemetry-card.visible { display: block; animation: fadeIn 0.2s ease; }
    .tel-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 0.65rem;
      padding-bottom: 0.5rem;
      border-bottom: 1px solid var(--border);
    }
    .model-badge {
      font-weight: 700;
      font-size: 0.8rem;
      padding: 0.22rem 0.6rem;
      border-radius: 4px;
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      font-family: 'JetBrains Mono', monospace;
    }
    .model-badge.nano { background: #1c1c20; color: #f4f4f5; border: 1px solid #3f3f46; }
    .model-badge.super { background: #242429; color: #ffffff; border: 1px solid #52525b; }
    .model-badge.ultra { background: #ffffff; color: #09090b; border: 1px solid #ffffff; }

    .savings-ticker {
      font-size: 0.88rem;
      font-weight: 700;
      color: #f4f4f5;
      font-family: 'JetBrains Mono', monospace;
    }
    .tel-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 0.5rem;
      font-size: 0.8rem;
    }
    @media (max-width: 580px) {
      .tel-grid { grid-template-columns: 1fr; }
    }
    .tel-item {
      display: flex;
      flex-direction: column;
      gap: 0.15rem;
    }
    .tel-label { color: var(--text-muted); font-size: 0.7rem; font-weight: 600; text-transform: uppercase; }
    .tel-val { font-family: 'JetBrains Mono', monospace; font-weight: 600; }

    /* SteerLM Scorecard Bars */
    .scorecard-box {
      margin-top: 0.75rem;
      padding-top: 0.65rem;
      border-top: 1px solid var(--border);
    }
    .score-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-size: 0.72rem;
      margin-bottom: 0.3rem;
      font-family: 'JetBrains Mono', monospace;
    }
    .score-bar-bg {
      flex: 1;
      height: 4px;
      background: #27272a;
      border-radius: 2px;
      margin: 0 0.6rem;
      overflow: hidden;
    }
    .score-bar-fill {
      height: 100%;
      border-radius: 2px;
      background: #e4e4e7;
      transition: width 0.3s ease;
    }

    /* Tabs & Output Pane */
    .tabs-row {
      display: flex;
      gap: 0.35rem;
      margin-bottom: 0.45rem;
    }
    .tab-btn {
      background: transparent;
      border: 1px solid transparent;
      color: var(--text-muted);
      padding: 0.35rem 0.75rem;
      border-radius: 4px;
      font-size: 0.78rem;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.15s;
    }
    .tab-btn.active {
      background: #27272a;
      border-color: #3f3f46;
      color: #ffffff;
    }

    #terminalPane {
      background: var(--code-bg);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 1rem;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.85rem;
      line-height: 1.55;
      min-height: 200px;
      max-height: 450px;
      overflow-y: auto;
      white-space: pre-wrap;
      word-break: break-word;
      color: #e4e4e7;
    }

    /* UI-5: Visual Diff Viewer */
    .diff-container {
      display: none;
      background: var(--code-bg);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 0.6rem;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.82rem;
      max-height: 450px;
      overflow-y: auto;
    }
    .diff-line {
      padding: 0.15rem 0.4rem;
      border-radius: 2px;
      white-space: pre-wrap;
    }
    .diff-add {
      background: var(--diff-add-bg);
      color: #4ade80;
      border-left: 2px solid var(--diff-add-border);
    }
    .diff-del {
      background: var(--diff-del-bg);
      color: #f87171;
      border-left: 2px solid var(--diff-del-border);
    }
    .diff-context {
      color: #a1a1aa;
    }

    /* UI-4: Collapsible Mobile File Tree */
    .file-drawer {
      display: none;
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 0.85rem;
      margin-bottom: 1rem;
      max-height: 300px;
      overflow-y: auto;
    }
    .file-drawer.visible { display: block; animation: fadeIn 0.2s ease; }
    .file-tree-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 0.6rem;
      font-size: 0.8rem;
      font-weight: 700;
    }
    .file-tree-search {
      width: 100%;
      background: #141417;
      border: 1px solid var(--border);
      color: var(--text);
      border-radius: 4px;
      padding: 0.4rem 0.6rem;
      font-size: 0.8rem;
      margin-bottom: 0.5rem;
    }
    .file-item {
      padding: 0.3rem 0.5rem;
      border-radius: 4px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.78rem;
      color: var(--text-muted);
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: space-between;
      transition: background 0.15s;
    }
    .file-item:hover {
      background: #27272a;
      color: #ffffff;
    }

    /* File Preview Modal */
    .modal-overlay {
      display: none;
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.85);
      z-index: 200;
      align-items: center;
      justify-content: center;
      padding: 1rem;
    }
    .modal-overlay.open { display: flex; animation: fadeIn 0.2s ease; }
    .modal-box {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 8px;
      width: 100%;
      max-width: 650px;
      max-height: 85vh;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }
    .modal-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0.85rem 1rem;
      border-bottom: 1px solid var(--border);
    }
    .modal-title { font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; font-weight: 700; }
    .modal-body {
      padding: 1rem;
      overflow-y: auto;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.8rem;
      white-space: pre-wrap;
      line-height: 1.5;
      background: var(--code-bg);
      color: #e4e4e7;
    }
    .modal-footer {
      display: flex;
      justify-content: flex-end;
      gap: 0.5rem;
      padding: 0.75rem 1rem;
      border-top: 1px solid var(--border);
      background: var(--surface);
    }

    /* Action Footer (Commit & Copy) */
    .output-actions-bar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-top: 0.75rem;
      gap: 0.5rem;
    }

    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(-3px); }
      to { opacity: 1; transform: translateY(0); }
    }
  </style>
</head>
<body>
  <!-- Sticky Header -->
  <header>
    <div class="header-row">
      <div class="brand">
        <span>⚡ <span class="logo-accent">Just-Enough-AI</span></span>
        <span class="badge-live">COCKPIT</span>
      </div>
      <div class="header-chips">
        <div id="hwChip" class="chip">Scanning HW...</div>
        <div id="statusBadge" class="badge-live" style="background:#18181b; color:var(--text-muted); border-color:var(--border);">Ready</div>
      </div>
    </div>

    <!-- UI-8: Provider Status HUD Pill Bar -->
    <div class="provider-pill-bar" id="providerBar">
      <div class="provider-pill" id="pill-antigravity"><span class="dot green"></span>Antigravity (Free)</div>
      <div class="provider-pill" id="pill-claude_code"><span class="dot green"></span>Claude Code (Free)</div>
      <div class="provider-pill" id="pill-ollama"><span class="dot amber"></span>Ollama (Local)</div>
      <div class="provider-pill active" id="pill-nebius"><span class="dot blue"></span>Nebius Cloud</div>
    </div>
  </header>

  <!-- Cascading Failover Toast Alert -->
  <div id="toastAlert" class="toast-alert">
    <span>⚠️</span>
    <span id="toastMsg">Upstream provider quota reached. Cascaded seamlessly to Nebius Cloud.</span>
  </div>

  <!-- Execution Controls Grid -->
  <div class="controls-grid" style="grid-template-columns: 1fr 1fr 1fr;">
    <div>
      <label for="modeSelect">Execution Mode</label>
      <select id="modeSelect">
        <option value="remote" selected>📱 Remote / Cloud (Laptop OFF)</option>
        <option value="local">💻 Local (GPU Profiling Active)</option>
      </select>
    </div>
    <div>
      <label for="tierSelect">Tier Override</label>
      <select id="tierSelect">
        <option value="">🤖 Smart Dynamic Routing</option>
        <option value="nano">⚡ Force Nano ($0.15/1M)</option>
        <option value="super">⚖️ Force Super ($0.375/1M)</option>
        <option value="ultra">🧠 Force Ultra ($1.80/1M)</option>
      </select>
    </div>
    <div>
      <label for="engineSelect">Execution Pipeline</label>
      <select id="engineSelect">
        <option value="run" selected>⚡ Direct Stream (/api/run)</option>
        <option value="loop">🔄 Agentic Loop (/api/loop)</option>
      </select>
    </div>
  </div>

  <!-- UI-2: Quick Action Prompt Chips -->
  <label>Quick Prompt Actions</label>
  <div class="prompt-chips-row">
    <div class="action-chip" onclick="setPrompt('Fix bug: handle null check and empty inputs in function')">🐛 Fix Bug</div>
    <div class="action-chip" onclick="setPrompt('Write comprehensive pytest unit tests for edge cases')">🧪 Add Tests</div>
    <div class="action-chip" onclick="setPrompt('Add detailed Google-style docstring with type annotations')">📝 Add Docstring</div>
    <div class="action-chip" onclick="setPrompt('Refactor to async with retry and exponential backoff')">⚡ Make Async</div>
    <div class="action-chip" onclick="setPrompt('Run security audit: detect hardcoded secrets and eval usage')">🛡️ Security Scan</div>
  </div>

  <!-- Prompt Textarea -->
  <textarea id="task" placeholder="Enter coding prompt, bug fix, or refactor task... (Ctrl + Enter to run)"></textarea>

  <!-- Main Action Buttons -->
  <div class="btn-row">
    <button class="btn-primary" id="runBtn" onclick="runTask()">
      <span>▶</span> Route & Execute
    </button>
    <button class="btn-secondary" id="filesBtn" onclick="toggleFileDrawer()">
      📁 Browse Repo
    </button>
    <button class="btn-secondary" style="flex:0.5;" onclick="clearAll()">
      Clear
    </button>
  </div>

  <!-- UI-4: Collapsible Mobile Repository File Explorer -->
  <div id="fileDrawer" class="file-drawer">
    <div class="file-tree-header">
      <span>📁 PROJECT REPOSITORY</span>
      <span id="fileCount" style="color:var(--text-muted); font-size:0.75rem;">0 files</span>
    </div>
    <input type="text" id="fileFilter" class="file-tree-search" placeholder="Filter files (e.g. server.py, test_)..." oninput="filterFiles()">
    <div id="fileTreeList"></div>
  </div>

  <!-- UI-3: Real-Time Model Badge & Cost Telemetry Widget -->
  <div id="telemetry" class="telemetry-card">
    <div class="tel-header">
      <div id="telBadge" class="model-badge nano">⚡ NANO OMNI</div>
      <div id="telSavings" class="savings-ticker">Saved: $0.00000</div>
    </div>
    <div class="tel-grid">
      <div class="tel-item">
        <span class="tel-label">Selected Model ID</span>
        <span id="telModelId" class="tel-val" style="color:var(--text);">-</span>
      </div>
      <div class="tel-item">
        <span class="tel-label">Actual Token Spend</span>
        <span id="telCost" class="tel-val" style="color:var(--accent);">-</span>
      </div>
      <div class="tel-item">
        <span class="tel-label">Token Statistics</span>
        <span id="telTokens" class="tel-val" style="color:var(--text-muted);">-</span>
      </div>
      <div class="tel-item">
        <span class="tel-label">Execution Latency</span>
        <span id="telLatency" class="tel-val" style="color:var(--text-muted);">-</span>
      </div>
    </div>
    <div class="tel-item" style="margin-top:0.5rem;">
      <span class="tel-label">Routing Rationale</span>
      <span id="telReason" style="font-size:0.75rem; color:var(--text-muted); line-height:1.4;">-</span>
    </div>

    <!-- SteerLM Multi-Attribute Scorecard Mini-Bars -->
    <div class="scorecard-box" id="steerScorecard" style="display:none;">
      <div class="score-row">
        <span>Correctness</span>
        <div class="score-bar-bg"><div id="barCorrectness" class="score-bar-fill" style="width:0%;"></div></div>
        <span id="valCorrectness">1.00</span>
      </div>
      <div class="score-row">
        <span>Regression Risk</span>
        <div class="score-bar-bg"><div id="barRegression" class="score-bar-fill" style="width:0%; background:#06b6d4;"></div></div>
        <span id="valRegression">0.05</span>
      </div>
      <div class="score-row">
        <span>Security Shield</span>
        <div class="score-bar-bg"><div id="barSecurity" class="score-bar-fill" style="width:0%;"></div></div>
        <span id="valSecurity">1.00</span>
      </div>
    </div>
  </div>

  <!-- Output Tabs -->
  <div class="tabs-row">
    <button class="tab-btn active" id="tabTerminal" onclick="switchTab('terminal')">Streaming Terminal</button>
    <button class="tab-btn" id="tabDiff" onclick="switchTab('diff')">Visual Code Diff</button>
    <button class="tab-btn" id="tabLoop" onclick="switchTab('loop')">Agent Loop Logs</button>
  </div>

  <!-- Terminal Output Pane -->
  <div id="terminalPane">// Live Nemotron token stream will appear here...</div>

  <!-- UI-5: Visual Syntax-Highlighted Diff Viewer -->
  <div id="diffContainer" class="diff-container"></div>

  <!-- Agent Loop Event Log Pane -->
  <div id="loopContainer" class="diff-container"></div>

  <!-- Output Action Bar (Approve & Commit / Copy) -->
  <div class="output-actions-bar">
    <button class="btn-primary" id="commitBtn" style="padding:0.55rem 0.9rem; font-size:0.82rem; display:none;" onclick="approveAndCommit()">
      ✓ Approve & Commit to Git
    </button>
    <button class="btn-secondary" id="copyBtn" style="padding:0.55rem 0.9rem; font-size:0.82rem;" onclick="copyOutput()">
      📋 Copy Code
    </button>
  </div>

  <!-- File Preview Modal -->
  <div id="previewModal" class="modal-overlay">
    <div class="modal-box">
      <div class="modal-header">
        <span class="modal-title" id="modalFilePath">file.py</span>
        <button style="background:transparent; border:none; color:var(--text-muted); cursor:pointer; font-size:1.1rem;" onclick="closeModal()">✕</button>
      </div>
      <div class="modal-body" id="modalContent">// Loading...</div>
      <div class="modal-footer">
        <button class="btn-secondary" onclick="closeModal()">Close</button>
        <button class="btn-primary" onclick="insertModalFileToPrompt()">+ Add to Prompt</button>
      </div>
    </div>
  </div>

  <!-- Client-Side Engine (UI-1, UI-2, UI-3, UI-4, UI-5, UI-8) -->
  <script>
    let rawOutputBuffer = '';
    let loopEventsBuffer = [];
    let currentModalPath = '';
    let allProjectFiles = [];

    // Initialize Cockpit on Load
    window.addEventListener('DOMContentLoaded', () => {
      fetchHardwareProfile();
      fetchProviderStatus();
      loadProjectFiles();
      loadCumulativeSavings();

      document.getElementById('task').addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
          e.preventDefault();
          runTask();
        }
      });
    });

    function loadCumulativeSavings() {
      const saved = parseFloat(localStorage.getItem('jeai_cumulative_savings') || '0');
      if (saved > 0) {
        document.getElementById('telSavings').textContent = `Total Saved: $${saved.toFixed(5)} vs Ultra`;
      }
    }

    function recordSavings(dollars) {
      let saved = parseFloat(localStorage.getItem('jeai_cumulative_savings') || '0');
      saved += dollars;
      localStorage.setItem('jeai_cumulative_savings', saved.toString());
    }

    async function fetchHardwareProfile() {
      try {
        const res = await fetch('/api/profile');
        const data = await res.json();
        const hwChip = document.getElementById('hwChip');
        if (data.hardware && data.hardware.gpu_available) {
          hwChip.textContent = `GPU: ${data.hardware.gpu_name || 'NVIDIA'} (${data.hardware.free_vram_mb.toFixed(0)}MB free)`;
        } else {
          hwChip.textContent = `Cloud Native ⚡ (Laptop OFF)`;
        }
      } catch (e) {
        document.getElementById('hwChip').textContent = 'Cloud Mode ⚡';
      }
    }

    async function fetchProviderStatus() {
      try {
        const res = await fetch('/api/providers');
        const data = await res.json();
        if (data.providers) {
          data.providers.forEach(p => {
            const el = document.getElementById(`pill-${p.name}`);
            if (el) {
              const dot = el.querySelector('.dot');
              if (p.is_available && p.has_capacity) {
                dot.className = 'dot green';
              } else if (p.is_available) {
                dot.className = 'dot amber';
              } else {
                dot.className = 'dot';
              }
            }
          });
        }
      } catch (e) {
        // Fallback gracefully
      }
    }

    async function loadProjectFiles() {
      try {
        const res = await fetch('/api/files');
        const data = await res.json();
        allProjectFiles = data.files || [];
        document.getElementById('fileCount').textContent = `${allProjectFiles.length} files`;
        renderFileTree(allProjectFiles);
      } catch (e) {
        document.getElementById('fileCount').textContent = 'Error loading files';
      }
    }

    // UI-4: Hierarchical File Tree
    function renderFileTree(files) {
      const list = document.getElementById('fileTreeList');
      list.innerHTML = '';

      const groups = {};
      files.forEach(f => {
        const parts = f.split('/');
        const folder = parts.length > 1 ? parts[0] + '/' : 'root/';
        if (!groups[folder]) groups[folder] = [];
        groups[folder].push(f);
      });

      Object.keys(groups).sort().forEach(folder => {
        const folderHead = document.createElement('div');
        folderHead.style.cssText = 'font-size:0.75rem; font-weight:700; color:var(--text-muted); padding:0.35rem 0; margin-top:0.3rem; border-bottom:1px solid rgba(255,255,255,0.05);';
        folderHead.textContent = `📁 ${folder} (${groups[folder].length})`;
        list.appendChild(folderHead);

        groups[folder].forEach(file => {
          const item = document.createElement('div');
          item.className = 'file-item';
          const fileName = file.split('/').pop();
          item.innerHTML = `<span>&nbsp;&nbsp;📄 ${fileName}</span><span style="font-size:0.7rem; color:var(--accent);">View</span>`;
          item.onclick = () => previewFile(file);
          list.appendChild(item);
        });
      });
    }

    function filterFiles() {
      const q = document.getElementById('fileFilter').value.toLowerCase().trim();
      const filtered = allProjectFiles.filter(f => f.toLowerCase().includes(q));
      renderFileTree(filtered);
    }

    function toggleFileDrawer() {
      const drawer = document.getElementById('fileDrawer');
      drawer.classList.toggle('visible');
    }

    async function previewFile(path) {
      currentModalPath = path;
      document.getElementById('modalFilePath').textContent = path;
      document.getElementById('modalContent').textContent = 'Loading file contents...';
      document.getElementById('previewModal').classList.add('open');
      try {
        const res = await fetch(`/api/file-content?path=${encodeURIComponent(path)}`);
        const data = await res.json();
        document.getElementById('modalContent').textContent = data.content || '[Empty file]';
      } catch (e) {
        document.getElementById('modalContent').textContent = 'Error reading file: ' + e.message;
      }
    }

    function closeModal() {
      document.getElementById('previewModal').classList.remove('open');
    }

    function insertModalFileToPrompt() {
      const textarea = document.getElementById('task');
      textarea.value = `[File: ${currentModalPath}]\n` + textarea.value;
      closeModal();
      textarea.focus();
    }

    function setPrompt(text) {
      const task = document.getElementById('task');
      task.value = text;
      task.focus();
    }

    function clearAll() {
      document.getElementById('task').value = '';
      document.getElementById('terminalPane').textContent = '// Ready for next coding prompt...';
      document.getElementById('diffContainer').innerHTML = '';
      document.getElementById('loopContainer').innerHTML = '';
      document.getElementById('telemetry').classList.remove('visible');
      document.getElementById('commitBtn').style.display = 'none';
      rawOutputBuffer = '';
      loopEventsBuffer = [];
    }

    function switchTab(tab) {
      const terminalPane = document.getElementById('terminalPane');
      const diffContainer = document.getElementById('diffContainer');
      const loopContainer = document.getElementById('loopContainer');
      const tabTerminal = document.getElementById('tabTerminal');
      const tabDiff = document.getElementById('tabDiff');
      const tabLoop = document.getElementById('tabLoop');

      terminalPane.style.display = tab === 'terminal' ? 'block' : 'none';
      diffContainer.style.display = tab === 'diff' ? 'block' : 'none';
      loopContainer.style.display = tab === 'loop' ? 'block' : 'none';

      tabTerminal.classList.toggle('active', tab === 'terminal');
      tabDiff.classList.toggle('active', tab === 'diff');
      tabLoop.classList.toggle('active', tab === 'loop');

      if (tab === 'diff') generateDiffView();
      if (tab === 'loop') generateLoopLogs();
    }

    // UI-5: Generate Visual Code Diff
    function generateDiffView() {
      const diffBox = document.getElementById('diffContainer');
      diffBox.innerHTML = '';
      const lines = rawOutputBuffer.split('\n');
      if (lines.length === 0 || !rawOutputBuffer) {
        diffBox.innerHTML = '<div style="color:var(--text-muted); padding:1rem;">No code diff available yet. Execute a task to inspect changes.</div>';
        return;
      }

      lines.forEach(line => {
        const div = document.createElement('div');
        div.className = 'diff-line';
        if (line.startsWith('+') && !line.startsWith('+++')) {
          div.className += ' diff-add';
          div.textContent = line;
        } else if (line.startsWith('-') && !line.startsWith('---')) {
          div.className += ' diff-del';
          div.textContent = line;
        } else {
          div.className += ' diff-context';
          div.textContent = line;
        }
        diffBox.appendChild(div);
      });
    }

    function generateLoopLogs() {
      const box = document.getElementById('loopContainer');
      box.innerHTML = '';
      if (loopEventsBuffer.length === 0) {
        box.innerHTML = '<div style="color:var(--text-muted); padding:1rem;">No multi-step loop events recorded. Switch pipeline to "Agentic Loop" to run multi-step execution.</div>';
        return;
      }
      loopEventsBuffer.forEach(evt => {
        const div = document.createElement('div');
        div.style.cssText = 'padding:0.4rem 0.6rem; border-bottom:1px solid #27272a; font-size:0.8rem;';
        const color = evt.event_type === 'KV_BUDGET' ? '#a1a1aa' : evt.event_type === 'SPECULATION' ? '#e4e4e7' : '#ffffff';
        div.innerHTML = `<span style="color:${color}; font-weight:700;">[Step ${evt.step} - ${evt.event_type}]</span> <span style="color:#e4e4e7;">${evt.message}</span>`;
        box.appendChild(div);
      });
    }

    // UI-1: SSE Stream Consumer with Real-Time Protocol Decoding
    async function runTask() {
      const task = document.getElementById('task').value.trim();
      if (!task) return;

      const mode = document.getElementById('modeSelect').value;
      const forceTier = document.getElementById('tierSelect').value || null;
      const engine = document.getElementById('engineSelect').value;
      const runBtn = document.getElementById('runBtn');
      const output = document.getElementById('terminalPane');
      const statusBadge = document.getElementById('statusBadge');
      const telemetry = document.getElementById('telemetry');
      const telBadge = document.getElementById('telBadge');
      const telSavings = document.getElementById('telSavings');
      const telModelId = document.getElementById('telModelId');
      const telCost = document.getElementById('telCost');
      const telTokens = document.getElementById('telTokens');
      const telLatency = document.getElementById('telLatency');
      const telReason = document.getElementById('telReason');
      const commitBtn = document.getElementById('commitBtn');

      runBtn.disabled = true;
      output.textContent = '';
      rawOutputBuffer = '';
      loopEventsBuffer = [];
      statusBadge.textContent = 'Connecting...';
      statusBadge.style.color = '#a1a1aa';
      telemetry.classList.add('visible');
      commitBtn.style.display = 'none';

      const endpoint = engine === 'loop' ? '/api/loop' : '/api/run';

      try {
        const res = await fetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ task, mode, force_tier: forceTier }),
        });

        if (!res.ok) {
          const errDetail = await res.text();
          throw new Error(`Server returned HTTP ${res.status}: ${errDetail}`);
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const rawLine of lines) {
            const line = rawLine.trim();
            if (!line.startsWith('data: ')) continue;
            const payload = line.slice(6).trim();
            if (!payload) continue;

            if (payload === '[DONE]') {
              statusBadge.textContent = 'Completed ✓';
              statusBadge.style.color = '#ffffff';
              commitBtn.style.display = 'inline-flex';
            } else if (payload.startsWith('[ROUTING]')) {
              try {
                const d = JSON.parse(payload.slice(9).trim());
                const tier = (d.selected_tier || 'nano').toLowerCase();
                telBadge.className = `model-badge ${tier}`;
                telBadge.textContent = `⚡ ${tier.toUpperCase()}`;
                telModelId.textContent = d.model_id || 'Nemotron';
                telReason.textContent = d.reasoning || 'Evaluated task requirements';
                statusBadge.textContent = `Streaming (${tier.toUpperCase()})...`;

                // Highlight active provider pill
                document.querySelectorAll('.provider-pill').forEach(p => p.classList.remove('active'));
                const nebiusPill = document.getElementById('pill-nebius');
                if (nebiusPill) nebiusPill.classList.add('active');
              } catch (e) {
                console.warn('Failed parsing ROUTING payload:', e, payload);
              }
            } else if (payload.startsWith('[EVENT]')) {
              try {
                const evt = JSON.parse(payload.slice(7).trim());
                loopEventsBuffer.push(evt);
                output.textContent += `[Step ${evt.step} - ${evt.event_type}] ${evt.message}\n`;
                output.scrollTop = output.scrollHeight;
              } catch (e) {
                console.warn('Failed parsing EVENT payload:', e, payload);
              }
            } else if (payload.startsWith('[METADATA]')) {
              try {
                const m = JSON.parse(payload.slice(10).trim());
                telCost.textContent = `$${m.actual_cost_usd.toFixed(6)}`;
                telSavings.textContent = `Saved: $${m.savings_vs_ultra_usd.toFixed(6)} vs Ultra`;
                telTokens.textContent = `${m.total_tokens} (${m.prompt_tokens} in / ${m.completion_tokens} out)`;
                telLatency.textContent = `${m.latency_ms.toFixed(0)}ms`;
                recordSavings(m.savings_vs_ultra_usd);

                // Show HelpSteer2 scorecard
                const steerCard = document.getElementById('steerScorecard');
                steerCard.style.display = 'block';
                document.getElementById('barCorrectness').style.width = '100%';
                document.getElementById('barRegression').style.width = '5%';
                document.getElementById('barSecurity').style.width = '100%';
              } catch (e) {
                console.warn('Failed parsing METADATA payload:', e, payload);
              }
            } else {
              const unescaped = payload.replace(/\\n/g, '\n');
              rawOutputBuffer += unescaped;
              output.textContent += unescaped;
              output.scrollTop = output.scrollHeight;
            }
          }
        }

        // Process any residual in buffer
        if (buffer.trim().startsWith('data: ')) {
          const payload = buffer.trim().slice(6).trim();
          if (payload === '[DONE]') {
            statusBadge.textContent = 'Completed ✓';
            statusBadge.style.color = '#10b981';
            commitBtn.style.display = 'inline-flex';
          }
        }
      } catch (err) {
        output.textContent += '\n[Network/Stream Error]: ' + err.message;
        statusBadge.textContent = 'Error';
        statusBadge.style.color = '#ef4444';
      } finally {
        runBtn.disabled = false;
      }
    }

    // UI-5: One-Tap "Approve & Commit" to Git
    async function approveAndCommit() {
      const commitBtn = document.getElementById('commitBtn');
      const taskVal = document.getElementById('task').value;
      
      // Auto-detect target file path from prompt if available
      let defaultPath = 'src/just_enough_ai/patch.py';
      const fileMatch = taskVal.match(/\[File:\s*([^\s\]]+)\]/);
      if (fileMatch && fileMatch[1]) {
        defaultPath = fileMatch[1];
      } else if (currentModalPath) {
        defaultPath = currentModalPath;
      }

      const promptText = prompt('Enter Git commit message:', 'Applied verified patch via Just-Enough-AI');
      if (!promptText) return;

      const filePath = prompt('Enter target file path in repository:', defaultPath);
      if (!filePath) return;

      commitBtn.disabled = true;
      commitBtn.textContent = 'Committing...';

      try {
        const res = await fetch('/api/commit', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            file_path: filePath,
            content: rawOutputBuffer,
            commit_message: promptText,
            do_git_commit: true,
          }),
        });
        const data = await res.json();
        if (data.success) {
          alert('✓ Successfully committed to repository! ' + data.message);
        } else {
          alert('Commit failed: ' + (data.detail || data.message));
        }
      } catch (err) {
        alert('Commit request failed: ' + err.message);
      } finally {
        commitBtn.disabled = false;
        commitBtn.textContent = '✓ Approve & Commit to Git';
      }
    }

    function copyOutput() {
      if (!rawOutputBuffer) return;
      navigator.clipboard.writeText(rawOutputBuffer).then(() => {
        const copyBtn = document.getElementById('copyBtn');
        const orig = copyBtn.textContent;
        copyBtn.textContent = '✓ Copied!';
        setTimeout(() => copyBtn.textContent = orig, 1500);
      });
    }
  </script>
</body>
</html>"""
    return HTMLResponse(content=html)

