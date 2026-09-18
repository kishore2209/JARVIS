import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.automation import AutomationController, AutomationJob
from core.orchestrator import JarvisRequest, JarvisOrchestrator
from market.persistence import AutomationJobRepository, AutomationOccurrenceRepository, PersistenceRestoreService, SQLiteStore
from market.providers.mock import MockMarketDataProvider


def check(name, condition):
    if not condition: raise AssertionError(name)
    print(f"[PASS] {name}")


def main():
    path = tempfile.mktemp(suffix=".db")
    timestamp = datetime(2026, 1, 2, 13, 14, tzinfo=timezone.utc)
    request = JarvisRequest("R", "FULL_ANALYSIS", timestamp, "JARVIS")
    job = AutomationJob("ONCE", "once", "FULL_MARKET_ANALYSIS", True, "ANALYSIS_ONLY", "ONCE", request, timestamp)
    first = SQLiteStore(path)
    AutomationJobRepository(first).save("ONCE", job)
    key = f"ONCE:{timestamp.isoformat()}"
    AutomationOccurrenceRepository(first).save(key, {"key": key})
    first.close()
    second = SQLiteStore(path)
    controller = AutomationController(JarvisOrchestrator(MockMarketDataProvider()))
    PersistenceRestoreService(second).restore_automation(controller)
    check("DB opens cleanly", second.version() == 1)
    check("State persisted", len(second.read_all("automation_jobs")) == 1)
    check("State restored", "ONCE" in controller.jobs and key in controller._occurrences)
    history_before = len(controller.history)
    check("Duplicate occurrence not rerun", controller.tick(timestamp) == () and len(controller.history) == history_before)
    check("Restart creates no action", len(controller.history) == 0)
    second.close()
    os.remove(path)
    print("TEST SUMMARY: 5/5 PASS")

if __name__ == "__main__": main()
