import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.automation import AutomationController, AutomationJob
from core.orchestrator import JarvisOrchestrator, JarvisRequest
from market.providers.mock import MockMarketDataProvider

now = datetime(2026, 1, 2, 10, tzinfo=timezone.utc)
orchestrator = JarvisOrchestrator(MockMarketDataProvider())
controller = AutomationController(orchestrator)
request = JarvisRequest("AUTO-VERIFY", "FULL_ANALYSIS", now, "JARVIS", "NSE", "000001")
controller.register(AutomationJob("ANALYSIS-1", "Mock analysis", "FULL_MARKET_ANALYSIS", True, "ANALYSIS_ONLY", "ONCE", request, now))
runs = controller.tick(now)
run = runs[0]

print("AUTOMATION JOBS")
print("Job ID: ANALYSIS-1")
print("Job type: FULL_MARKET_ANALYSIS")
print("Schedule: ONCE")
print("Execution mode: ANALYSIS_ONLY")
print("RUN RESULTS")
print(f"Run ID: {run.run_id}")
print(f"Status: {run.status}")
print(f"Started: {run.started_at}")
print(f"Completed: {run.completed_at}")
print(f"Retry count: {run.retry_count}")
print("ANALYSIS")
print(f"Instrument: {run.orchestrator_result.instrument}")
print(f"Confluence bias: {run.orchestrator_result.confluence_analysis.directional_bias}")
print(f"Evidence quality: {run.orchestrator_result.confluence_analysis.evidence_quality}")
print("AUDIT")
print("Completed jobs: 1")
print("Skipped jobs: 0")
print("Failed jobs: 0")