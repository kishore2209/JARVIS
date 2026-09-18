import sys
from dataclasses import dataclass
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path
PROJECT_ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(PROJECT_ROOT))
from core.interface_service import JarvisInterfaceService,serialize
from core.orchestrator import JarvisOrchestrator
from market.providers.mock import MockMarketDataProvider
def main():
 t=datetime(2026,1,2,13,14,tzinfo=timezone.utc);s=JarvisInterfaceService(JarvisOrchestrator(MockMarketDataProvider()))
 assert s.status()["live_execution_supported"] is False;print("[PASS] Status")
 full=s.request({"request_type":"FULL_ANALYSIS","instrument":"JARVIS","exchange":"NSE","token":"000001","timestamp":t});assert full["status"]=="OK" and full["result"]["confluence_analysis"];print("[PASS] Analysis Serialization")
 assert s.request({"request_type":"FULL_ANALYSIS","execution_mode":"LIVE","timestamp":t})["code"]=="LIVE_EXECUTION_UNSUPPORTED";assert s.request({"timestamp":t})["code"]=="INVALID_REQUEST";print("[PASS] Request Validation")
 @dataclass
 class Nested: value:Decimal;when:datetime;optional:object=None
 assert serialize(Nested(Decimal("1.25"),t))["value"]=="1.25";print("[PASS] Decimal Datetime Optional")
 return 0
if __name__=="__main__":sys.exit(main())