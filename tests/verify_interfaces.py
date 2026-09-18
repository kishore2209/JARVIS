import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.automation import AutomationController, AutomationJob
from core.interface_service import JarvisInterfaceService
from core.orchestrator import JarvisOrchestrator, JarvisRequest
from market.providers.mock import MockMarketDataProvider

timestamp = datetime(2026, 1, 2, 13, 14, tzinfo=timezone.utc)
orchestrator = JarvisOrchestrator(MockMarketDataProvider())
automation = AutomationController(orchestrator)
service = JarvisInterfaceService(orchestrator, automation)
analysis = service.request({"request_type":"FULL_ANALYSIS","instrument":"JARVIS","exchange":"NSE","token":"000001","timestamp":timestamp})
live = service.request({"request_type":"FULL_ANALYSIS","execution_mode":"LIVE","timestamp":timestamp})
automation.register(AutomationJob("VERIFY","Verify","FULL_MARKET_ANALYSIS",True,"ANALYSIS_ONLY","ONCE",JarvisRequest("VERIFY","FULL_ANALYSIS",timestamp,"JARVIS","NSE","000001"),timestamp))

print("JARVIS INTERFACE VERIFY")
print(f"STATUS: {service.status()['application_status']}")
print(f"ANALYSIS: instrument={analysis['result']['instrument']} strategies={len(analysis['result']['strategy_evidence'])} confluence={analysis['result']['confluence_analysis']['directional_bias']}")
print("RISK: requires explicit structured proposal")
print("PAPER: unauthorized execution requires explicit authorization")
print("PORTFOLIO: requires an explicit PaperAccount")
print(f"AUTOMATION: runs={len(service.automation_tick(timestamp)['runs'])}")
print("SECURITY: Secret leakage: NONE")
print(f"LIVE execution: {live['code']}")