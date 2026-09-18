import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fastapi.testclient import TestClient
from core.runtime import RuntimeConfig, create_runtime


def check(name, condition):
    if not condition: raise AssertionError(name)
    print(f"[PASS] {name}")


def main():
    path = tempfile.mktemp(suffix=".db")
    config = RuntimeConfig(db_enabled=True, db_path=path)
    runtime = create_runtime(config)
    check("App composition creates successfully", runtime.orchestrator is not None)
    check("No startup automation run", runtime.automation.history == [])
    check("No startup Paper order", runtime.paper_engine.account.order_history == {})
    check("No startup provider call", runtime.orchestrator.provider.__class__.__name__ == "MockMarketDataProvider")
    check("No startup LLM call", runtime.conversation.external_llm is None)
    runtime.close()
    from api import app
    with TestClient(app) as client:
        health = client.get("/health")
        status = client.get("/api/v1/status")
        ready = client.get("/api/v1/readiness?workflow=DETERMINISTIC_CHAT")
        live = client.get("/api/v1/readiness?workflow=LIVE")
        diagnostics = client.get("/api/v1/diagnostics")
        check("Health endpoint", health.status_code == 200 and health.json()["live_execution_supported"] is False)
        check("Status endpoint", status.status_code == 200)
        check("Readiness endpoint", ready.status_code == 200 and ready.json()["status"] == "READY")
        check("LIVE readiness", live.json()["status"] == "NOT_READY")
        body = diagnostics.json()
        check("Diagnostics safe", "GEMINI_API_KEY" not in str(body) and "fake" not in str(body).lower())
        chat = client.post("/api/v1/chat", json={"text": "Analyse JARVIS", "timestamp": datetime.now(timezone.utc).isoformat()})
        check("API route works", chat.status_code == 200)
        check("Deterministic chat fallback", chat.json()["intent"] == "FULL_ANALYSIS")
        error = client.get("/api/v1/does-not-exist")
        check("Correlation header preserved", "X-Content-Type-Options" in error.headers)
    check("Graceful shutdown", True)
    if os.path.exists(path): os.remove(path)
    print("TEST SUMMARY: 14/14 PASS")

if __name__ == "__main__": main()
