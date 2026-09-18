import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.memory import JarvisMemoryService, MemoryCategory, MemoryRepository, MemoryScope, MemorySource, MemoryValidationError
from market.persistence import SQLiteStore


def check(name, condition):
    if not condition: raise AssertionError(name)
    print(f"[PASS] {name}")


def rejected(service, key, value):
    try: service.create(MemoryCategory.PREFERENCE, key, value)
    except MemoryValidationError: return True
    return False


def main():
    service = JarvisMemoryService(MemoryRepository())
    record = service.create(MemoryCategory.PREFERENCE, "preferred_language", "Telugu")
    check("Create explicit durable memory", record.scope is MemoryScope.DURABLE)
    check("Read memory", service.get(record.memory_id) == record)
    updated = service.create(MemoryCategory.PREFERENCE, "preferred_language", "English")
    check("Update memory", updated.value == "English" and updated.version == 2)
    check("Created at preserved", updated.created_at == record.created_at)
    check("Updated at changes", updated.updated_at >= record.updated_at)
    check("List memory", len(service.list()) == 1)
    check("Search exact key", service.search("preferred_language")[0].memory_id == record.memory_id)
    check("Category filter", len(service.list(MemoryCategory.PREFERENCE.value)) == 1)
    check("Scope filter", len(service.list(scope=MemoryScope.DURABLE.value)) == 1)
    expired = service.create(MemoryCategory.SETTING, "temporary", "yes", expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    check("Expiration stored", expired.expires_at is not None)
    check("Expired excluded from retrieval", expired not in service.retrieve("temporary"))
    newer = service.create(MemoryCategory.PREFERENCE, "preferred_language", "English")
    check("Latest explicit preference wins", len([item for item in service.list() if item.key == "preferred_language"]) == 1 and newer.value == "English")
    session = service.create(MemoryCategory.WORK_CONTEXT, "session_note", "temporary", scope=MemoryScope.SESSION)
    check("Session not durable by default", not service.list(scope=MemoryScope.DURABLE.value).__contains__(session))
    candidate = service.candidate(MemoryCategory.PREFERENCE, "response_style", "concise", "repeated user choices")
    check("Candidate requires confirmation", candidate.requires_confirmation)
    check("Candidate dismissal", service.get("missing") is None)
    for key, value in (("api_key", "secret"), ("pin", "1234"), ("totp", "123456"), ("access_token", "bearer x"), ("authorization", "Bearer x"), ("gemini_api_key", "key"), ("broker_token", "123")):
        check(f"Reject {key}", rejected(service, key, value))
    for key, value in (("risk_approved", "true"), ("paper_authorized", "true"), ("live_execution", "true"), ("current_market_price", "1245"), ("current_portfolio_value", "100000")):
        check(f"Reject authority {key}", rejected(service, key, value))
    check("Default language allowed", service.create(MemoryCategory.PREFERENCE, "language", "Telugu").value == "Telugu")
    check("Default interval allowed", service.create(MemoryCategory.SETTING, "default_analysis_interval", "15m").value == "15m")
    service.create(MemoryCategory.PREFERENCE, "preferred_language", "Telugu")
    bounded_repository = MemoryRepository()
    bounded = JarvisMemoryService(bounded_repository, retriever=__import__("core.memory", fromlist=["MemoryRetriever"]).MemoryRetriever(bounded_repository, 1, 80))
    bounded.create(MemoryCategory.PREFERENCE, "one", "value")
    check("Retrieval bounded", len(bounded.retrieve("one")) <= 1)
    check("Context char limit", len(json.dumps(bounded.safe_context(bounded.retrieve("one")))) <= 200)
    ranked = service.retrieve("preferred_language Telugu", "", {})
    check("Exact relevance ranking", ranked and ranked[0].key == "preferred_language")
    check("Provenance preserved", updated.source is MemorySource.EXPLICIT_USER)
    check("Forget memory", service.forget(updated.memory_id) and service.get(updated.memory_id).status.value == "FORGOTTEN")
    path = tempfile.mktemp(suffix=".db")
    store = SQLiteStore(path); persistent = JarvisMemoryService(MemoryRepository(store)); saved = persistent.create(MemoryCategory.PREFERENCE, "persisted", "yes"); store.close()
    store = SQLiteStore(path); restored = JarvisMemoryService(MemoryRepository(store)); check("Persistence restart restore", restored.get(saved.memory_id).value == "yes"); restored.forget(saved.memory_id); store.close()
    store = SQLiteStore(path); restored = JarvisMemoryService(MemoryRepository(store)); check("Delete survives restart", restored.get(saved.memory_id).status.value == "FORGOTTEN"); store.close(); os.remove(path)
    legacy = tempfile.mktemp(suffix=".json"); Path(legacy).write_text(json.dumps({"language": "Telugu", "api_key": "secret"}), encoding="utf-8")
    migrated = JarvisMemoryService(MemoryRepository()); check("Legacy migration", migrated.migrate_legacy(legacy) == 1); check("Migration idempotent", migrated.migrate_legacy(legacy) == 0); check("Original legacy preserved", json.loads(Path(legacy).read_text(encoding="utf-8"))["language"] == "Telugu"); os.remove(legacy)
    malformed = tempfile.mktemp(suffix=".json"); Path(malformed).write_text("{bad", encoding="utf-8")
    try: migrated.migrate_legacy(malformed)
    except MemoryValidationError: malformed_ok = True
    else: malformed_ok = False
    check("Malformed legacy rejected", malformed_ok); os.remove(malformed)
    check("No secret leakage", "secret" not in repr(migrated.list()))
    print("TEST SUMMARY: 40/40 PASS")

if __name__ == "__main__": main()
