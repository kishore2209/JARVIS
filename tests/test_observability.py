import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT))
from core.observability import Observability,configuration_status,sanitize
from core.orchestrator import JarvisOrchestrator,JarvisRequest
from market.providers.mock import MockMarketDataProvider
def main():
 o=Observability();e=o.record("API","REQUEST","COMPLETED",request_id="R1",duration_ms=2,metadata={"access_token":"secret","nested":[{"ANGEL_ONE_PIN":"1234"}]});assert e.request_id=="R1" and e.duration_ms==2 and "secret" not in str(e);print("[PASS] Structured Event Correlation Sanitization")
 o.record("API","REQUEST","FAILED",message="Bearer secret");assert o.snapshot()["counters"]=={"requests_failed":1,"requests_total":2};print("[PASS] Metrics Failure Counter")
 assert o.health(True,True)["system"]=="HEALTHY" and o.readiness("ANALYSIS_ONLY")["status"]=="READY" and o.readiness("LIVE")["status"]=="NOT_READY" and all(isinstance(v,bool) for v in configuration_status().values());print("[PASS] Health Readiness Config")
 enabled=Observability();base=JarvisOrchestrator(MockMarketDataProvider());instrumented=JarvisOrchestrator(MockMarketDataProvider(),observability=enabled);request=JarvisRequest("TRACE-1","FULL_ANALYSIS",__import__("datetime").datetime(2026,1,2,13,14,tzinfo=__import__("datetime").timezone.utc),"JARVIS","NSE","000001");assert base.handle(request)==instrumented.handle(request) and enabled.events[0].request_id=="TRACE-1" and enabled.events[0].duration_ms is not None;print("[PASS] Orchestrator Correlation Domain Equivalence")
 event=enabled.provider_error("MOCK","get_candles","JARVIS",RuntimeError("Bearer secret"));assert event.metadata["provider"]=="MOCK" and "secret" not in str(event) and enabled.counters["provider_errors"]==1;print("[PASS] Provider Error Telemetry")
 from fastapi.testclient import TestClient
 from api import app,observability
 client=TestClient(app);client.get("/health",headers={"X-Correlation-ID":"TRACE-API"});assert client.get("/api/v1/metrics").status_code==200 and client.get("/api/v1/diagnostics").status_code==200 and any(event.request_id=="TRACE-API" for event in observability.events);print("[PASS] API Telemetry Diagnostics")
 from core.automation import AutomationController,AutomationJob
 from market.persistence import SQLiteStore
 import tempfile,subprocess
 auto=Observability();controller=AutomationController(JarvisOrchestrator(MockMarketDataProvider()),observability=auto);job=AutomationJob("AUTO","auto","FULL_MARKET_ANALYSIS",True,"ANALYSIS_ONLY","ONCE",request,request.timestamp);controller.register(job);controller.tick(request.timestamp);assert auto.counters["automation_runs_total"]==1;print("[PASS] Automation Counter")
 path=tempfile.mktemp(suffix=".db");store=SQLiteStore(path,auto);store.save("orders","ONE",{});
 try:store.save("orders","ONE",{})
 except ValueError:assert auto.counters["persistence_errors"]==1
 else:raise AssertionError("persistence failure missing")
 store.close();__import__("os").remove(path);print("[PASS] Persistence Error Counter")
 for command in ("health","metrics","diagnostics"):
  output=subprocess.run([sys.executable,"-m","jarvis_cli",command],capture_output=True,text=True).stdout;assert "secret" not in output.lower()
 print("[PASS] CLI Observability Commands")
 from market.risk import RiskConfig,TradeProposal
 from market.backtest import BacktestConfig,HistoricalReplayEngine
 metrics=Observability();orchestrator=JarvisOrchestrator(MockMarketDataProvider(),observability=metrics);proposal=TradeProposal("JARVIS","LONG","100","98","104","100000","1",25,125,request.timestamp,"MOCK",True)
 orchestrator.handle(JarvisRequest("RISK-OK","RISK_VALIDATE",request.timestamp,"JARVIS",parameters={"proposal":proposal,"risk_config":RiskConfig(require_fresh_data=False)}));bad=TradeProposal("JARVIS","LONG","100","101","104","100000","1",25,125,request.timestamp,"MOCK",True);orchestrator.handle(JarvisRequest("RISK-BAD","RISK_VALIDATE",request.timestamp,"JARVIS",parameters={"proposal":bad,"risk_config":RiskConfig(require_fresh_data=False)}));assert metrics.counters["risk_approved_total"]==1 and metrics.counters["risk_rejected_total"]==1;print("[PASS] Risk Counter Matrix")
 candles=MockMarketDataProvider().get_candles("JARVIS","NSE","000001",240);orchestrator.handle(JarvisRequest("BACK","BACKTEST",request.timestamp,"JARVIS",execution_mode="HISTORICAL_REPLAY",parameters={"backtest_engine":HistoricalReplayEngine(BacktestConfig(warmup_candles=200)),"candles":candles}));assert metrics.counters["backtests_total"]==1;print("[PASS] Backtest Counter")
 from market.paper_trading import PaperAccount,PaperTradingEngine
 decision=orchestrator.handle(JarvisRequest("RISK-PAPER","RISK_VALIDATE",request.timestamp,"JARVIS",parameters={"proposal":proposal,"risk_config":RiskConfig(require_fresh_data=False)})).risk_decision;paper=PaperTradingEngine(PaperAccount("100000"));approved=orchestrator.handle(JarvisRequest("PAPER","PAPER_EXECUTE",request.timestamp,"JARVIS",execution_mode="PAPER",parameters={"proposal":proposal,"risk_decision":decision,"paper_engine":paper},explicit_user_authorization=True));assert approved.paper_execution_result and metrics.counters["paper_orders_total"]==1;blocked=orchestrator.handle(JarvisRequest("BLOCK","PAPER_EXECUTE",request.timestamp,"JARVIS",execution_mode="PAPER",parameters={"proposal":proposal,"risk_decision":decision,"paper_engine":paper}));assert blocked.status=="AUTHORIZATION_REQUIRED" and metrics.counters["paper_orders_total"]==1;print("[PASS] Paper Order Counter Negative Cases")
 class Transient:
  def handle(self,request):raise ConnectionError("Bearer secret")
 retry_metrics=Observability();retry=AutomationController(Transient(),observability=retry_metrics);retry_job=AutomationJob("RETRY","retry","FULL_MARKET_ANALYSIS",True,"ANALYSIS_ONLY","ONCE",request,request.timestamp,max_retries=1);retry.register(retry_job);run=retry.tick(request.timestamp)[0];event=retry_metrics.events[-1];assert run.status=="RETRY_PENDING" and event.status=="RETRY_PENDING" and event.job_id=="RETRY" and event.metadata["retry_count"]==0 and "secret" not in str(event);print("[PASS] Retry Pending Telemetry")
 baseline=observability.counters.get("requests_failed",0);failure=client.post("/api/v1/analysis/full",json={"execution_mode":"LIVE","timestamp":"2026-01-02T13:14:00+00:00"},headers={"X-Correlation-ID":"FAIL-TRACE"}).json();assert failure["code"]=="LIVE_EXECUTION_UNSUPPORTED" and observability.counters["requests_failed"]==baseline+1 and any(event.status=="LIVE_EXECUTION_UNSUPPORTED" for event in observability.events) and "traceback" not in str(failure).lower();print("[PASS] API Failure Telemetry")
 suppressed=AutomationController(JarvisOrchestrator(MockMarketDataProvider()),observability=auto);suppressed._occurrences.add("AUTO:"+request.timestamp.isoformat());suppressed.register(job);before=auto.counters["automation_runs_total"];assert not suppressed.tick(request.timestamp) and auto.counters["automation_runs_total"]==before;print("[PASS] Negative Counter Cases")
 return 0
if __name__=="__main__":sys.exit(main())