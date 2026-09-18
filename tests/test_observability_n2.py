import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT))
from core.observability import GuardrailConfig,Observability,validate_configuration
from core.automation import AutomationController,AutomationJob
from core.orchestrator import JarvisOrchestrator,JarvisRequest
from market.providers.mock import MockMarketDataProvider
def main():
 o=Observability();assert o.health(False,False)["persistence"]=="DEGRADED" and o.health(True,True)["system"]=="HEALTHY" and o.readiness("ANALYSIS_ONLY")["ready"] and not o.readiness("REAL_PROVIDER_ANALYSIS")["ready"] and not o.readiness("LIVE")["ready"];print("[PASS] Health Readiness")
 assert validate_configuration()["valid"] and not validate_configuration(GuardrailConfig(max_batch_size=0))["valid"] and not validate_configuration(execution_mode="LIVE")["valid"];print("[PASS] Guardrail Config Validation")
 t=__import__("datetime").datetime(2026,1,2,13,14,tzinfo=__import__("datetime").timezone.utc);telemetry=Observability();controller=AutomationController(JarvisOrchestrator(MockMarketDataProvider()),observability=telemetry,max_jobs_per_tick=1);request=JarvisRequest("G","MARKET_CONTEXT",t,"JARVIS","NSE","000001")
 controller.register(AutomationJob("A","a","MARKET_CONTEXT_REFRESH",True,"ANALYSIS_ONLY","ONCE",request,t));controller.register(AutomationJob("B","b","MARKET_CONTEXT_REFRESH",True,"ANALYSIS_ONLY","ONCE",request,t));assert len(controller.tick(t))==1 and any(event.status=="RATE_LIMITED" for event in telemetry.events);print("[PASS] Max Jobs Guardrail")
 try:controller.register(AutomationJob("BAD","bad","FULL_MARKET_ANALYSIS",True,"ANALYSIS_ONLY","ONCE",request,t,max_instruments_per_run=1,batch_size=2))
 except ValueError:print("[PASS] Batch Instrument Guardrail")
 else:raise AssertionError("invalid batch accepted")
 return 0
if __name__=="__main__":sys.exit(main())