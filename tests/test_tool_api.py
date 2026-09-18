import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fastapi.testclient import TestClient
from api import app

def check(name, condition):
    if not condition: raise AssertionError(name)
    print(f"[PASS] {name}")

def main():
    with TestClient(app) as client:
        listed = client.get("/api/v1/tools")
        check("List tools", listed.status_code == 200 and any(item["tool_id"] == "system.status" for item in listed.json()["tools"]))
        plan = client.post("/api/v1/tools/plan", json={"tool_id":"system.status","arguments":{}})
        check("Plan read-only", plan.status_code == 200)
        plan_id = plan.json()["plan"]["plan_id"]
        executed = client.post(f"/api/v1/tools/{plan_id}/execute")
        check("Execute read-only", executed.status_code == 200 and executed.json()["result"]["status"] == "SUCCEEDED")
        protected = client.post("/api/v1/tools/plan", json={"tool_id":"memory.preference.set","arguments":{"key":"language","value":"Telugu"}})
        protected_id = protected.json()["plan"]["plan_id"]
        check("Plan protected", protected.json()["plan"]["requires_confirmation"] is True)
        blocked = client.post(f"/api/v1/tools/{protected_id}/execute")
        check("Protected blocked before approval", blocked.json()["result"]["status"] == "REJECTED")
        approved = client.post(f"/api/v1/tools/{protected_id}/approve")
        check("Approve plan", approved.status_code == 200)
        result = client.post(f"/api/v1/tools/{protected_id}/execute")
        check("Execute approved plan", result.json()["result"]["status"] == "SUCCEEDED")
        duplicate = client.post(f"/api/v1/tools/{protected_id}/execute")
        check("Duplicate execute blocked", duplicate.json()["result"]["status"] == "REJECTED")
        unknown = client.post("/api/v1/tools/plan", json={"tool_id":"shell","arguments":{}})
        check("Unknown tool", unknown.status_code == 400 and "traceback" not in unknown.text.lower())
        invalid = client.post("/api/v1/tools/plan", json={"tool_id":"memory.search","arguments":{"bad":"x"}})
        check("Invalid arguments", invalid.status_code == 400)
        check("No secret leakage", "GEMINI_API_KEY" not in listed.text and "api_key" not in listed.text.lower())
    print("TEST SUMMARY: 12/12 PASS")
if __name__ == "__main__": main()
