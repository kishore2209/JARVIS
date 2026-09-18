import sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fastapi.testclient import TestClient
from api import app


def check(name, condition):
    if not condition: raise AssertionError(name)
    print(f"[PASS] {name}")


def main():
    with TestClient(app) as client:
        key = "api_test_preference"
        created = client.post("/api/v1/memory", json={"category":"PREFERENCE","key":key,"value":"concise","scope":"DURABLE"})
        check("Create API", created.status_code == 200 and created.json()["memory"]["key"] == key)
        memory_id = created.json()["memory"]["memory_id"]
        listed = client.get("/api/v1/memory?category=PREFERENCE")
        check("List API", listed.status_code == 200 and any(item["memory_id"] == memory_id for item in listed.json()["memories"]))
        fetched = client.get(f"/api/v1/memory/{memory_id}")
        check("Get API", fetched.status_code == 200 and fetched.json()["memory"]["value"] == "concise")
        edited = client.patch(f"/api/v1/memory/{memory_id}", json={"value":"detailed"})
        check("Edit API", edited.status_code == 200 and edited.json()["memory"]["value"] == "detailed")
        rejected = client.post("/api/v1/memory", json={"category":"PREFERENCE","key":"api_key","value":"secret"})
        check("Secret value rejected", rejected.status_code == 400 and "stack" not in rejected.text.lower())
        deleted = client.delete(f"/api/v1/memory/{memory_id}")
        check("Forget API", deleted.status_code == 200 and deleted.json()["deleted"] is True)
        check("Safe serialization", "secret" not in listed.text)
    print("TEST SUMMARY: 7/7 PASS")

if __name__ == "__main__": main()
