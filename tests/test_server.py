"""Tests for FastAPI backend server endpoints."""

from pathlib import Path
from fastapi.testclient import TestClient
from just_enough_ai.server import app

client = TestClient(app)


def test_api_profile():
    res = client.get("/api/profile")
    assert res.status_code == 200
    data = res.json()
    assert "hardware" in data
    assert "execution_mode" in data


def test_api_pricing():
    res = client.get("/api/pricing")
    assert res.status_code == 200
    data = res.json()
    assert "nano" in data
    assert "super" in data
    assert "ultra" in data
    assert data["nano"]["input_per_1m_usd"] == 0.06


def test_api_route():
    res = client.post("/api/route", json={"task": "Fix a small typo", "mode": "remote", "force_tier": "nano"})
    assert res.status_code == 200
    data = res.json()
    assert data["selected_tier"] == "nano"
    assert data["execution_mode"] == "remote"
    assert data["force_tier"] == "nano"


def test_api_files():
    res = client.get("/api/files")
    assert res.status_code == 200
    data = res.json()
    assert "files" in data
    assert isinstance(data["files"], list)


def test_cockpit_html():
    res = client.get("/")
    assert res.status_code == 200
    assert "Just-Enough-AI Cockpit" in res.text


def test_api_run_sse_stream():
    res = client.post("/api/run", json={"task": "Write binary search", "mode": "remote", "force_tier": "nano"})
    assert res.status_code == 200
    assert "text/event-stream" in res.headers["content-type"]
    body = res.text
    assert "data: [ROUTING]" in body
    assert "data: [METADATA]" in body
    assert "data: [DONE]" in body


def test_api_speculative_endpoint():
    res = client.post("/api/speculative", json={"task": "Add currency formatting helper", "fallback_tier": "super"})
    assert res.status_code == 200
    data = res.json()
    assert "status" in data
    assert "final_tier" in data
    assert "gate_report" in data
    assert "total_cost_usd" in data


def test_api_kv_budget_endpoint():
    res = client.get("/api/kv-budget?tokens=5000&tier=nano")
    assert res.status_code == 200
    data = res.json()
    assert data["active_tokens"] == 5000
    assert "kv_cache_used_mb" in data
    assert "governor_action" in data


def test_api_loop_sse_stream():
    res = client.post("/api/loop", json={"task": "Refactor timestamp helper", "mode": "remote"})
    assert res.status_code == 200
    assert "text/event-stream" in res.headers["content-type"]
    body = res.text
    assert "data: [EVENT]" in body
    assert "data: [METADATA]" in body
    assert "data: [DONE]" in body


def test_api_providers():
    res = client.get("/api/providers")
    assert res.status_code == 200
    data = res.json()
    assert "providers" in data
    assert len(data["providers"]) >= 1
    names = [p["name"] for p in data["providers"]]
    assert "nebius" in names


def test_api_commit_path_traversal_blocked():
    res = client.post(
        "/api/commit",
        json={"file_path": "../../evil.py", "content": "print(1)"},
    )
    assert res.status_code == 400


def test_api_commit_success():
    scratch_file = Path("tests/scratch_commit_test.py")
    try:
        res = client.post(
            "/api/commit",
            json={
                "file_path": str(scratch_file),
                "content": "def hello(): return 'world'",
                "do_git_commit": False,
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert scratch_file.exists()
        assert scratch_file.read_text(encoding="utf-8") == "def hello(): return 'world'"
    finally:
        if scratch_file.exists():
            scratch_file.unlink()


def test_api_file_content():
    res = client.get("/api/file-content?path=README.md")
    assert res.status_code == 200
    data = res.json()
    assert "content" in data
    assert "Just-Enough-AI" in data["content"]
    assert data["path"] == "README.md"


def test_api_file_content_traversal_blocked():
    res = client.get("/api/file-content?path=../../etc/passwd")
    assert res.status_code == 400


def test_api_manifest():
    res = client.get("/manifest.json")
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "Just-Enough-AI Cockpit"
    assert data["display"] == "standalone"



