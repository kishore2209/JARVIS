import sys
from datetime import datetime,time,timedelta,timezone
from pathlib import Path
PROJECT_ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(PROJECT_ROOT))
from core.automation import AutomationController,AutomationJob,MarketSession
from core.orchestrator import JarvisOrchestrator,JarvisRequest
from market.providers.mock import MockMarketDataProvider
class Result:
 def __init__(self,status="COMPLETED"):self.status=status;self.is_fresh=True
class StubOrchestrator:
 def __init__(self,statuses=()):self.statuses=list(statuses);self.calls=[]
 def handle(self,request):self.calls.append(request);return Result(self.statuses.pop(0) if self.statuses else "COMPLETED")
def main():
 now=datetime(2026,1,2,10,tzinfo=timezone.utc);o=JarvisOrchestrator(MockMarketDataProvider());c=AutomationController(o);template=JarvisRequest("AUTO","FULL_ANALYSIS",now,"JARVIS","NSE","000001")
 once=AutomationJob("ONE","once","FULL_MARKET_ANALYSIS",True,"ANALYSIS_ONLY","ONCE",template,now);c.register(once);runs=c.tick(now);assert runs[0].status=="COMPLETED" and not c.tick(now);print("[PASS] Once Idempotency")
 interval=AutomationJob("INT","interval","FULL_MARKET_ANALYSIS",True,"ANALYSIS_ONLY","INTERVAL",template,now,interval=timedelta(minutes=5),max_instruments_per_run=2);c.register(interval);assert len(c.tick(now))==1 and not c.tick(now+timedelta(minutes=1)) and c.tick(now+timedelta(minutes=5));print("[PASS] Interval Schedule")
 daily_controller=AutomationController(o);daily=AutomationJob("DAY","daily","MARKET_CONTEXT_REFRESH",True,"ANALYSIS_ONLY","DAILY_TIME",template,now,daily_time=time(16));daily_controller.register(daily);assert not daily_controller.tick(now) and daily_controller.tick(now+timedelta(hours=6));print("[PASS] Daily Schedule")
 session_controller=AutomationController(o);closed=AutomationJob("CLOSED","closed","FULL_MARKET_ANALYSIS",True,"ANALYSIS_ONLY","ONCE",template,now,requires_market_hours=True);session_controller.register(closed);assert session_controller.tick(now+timedelta(hours=12))[0].status=="SKIPPED";print("[PASS] Market Hours")
 live=AutomationJob("LIVE","live","FULL_MARKET_ANALYSIS",True,"LIVE","ONCE",template,now)
 try:c.register(live)
 except ValueError:print("[PASS] Live Rejected")
 else:raise AssertionError("LIVE job accepted")
 disabled_controller=AutomationController(o);disabled=AutomationJob("DIS","disabled","FULL_MARKET_ANALYSIS",False,"ANALYSIS_ONLY","ONCE",template,now);disabled_controller.register(disabled);assert not disabled_controller.tick(now+timedelta(days=1));print("[PASS] Disabled Job")
 open_session=MarketSession(open_time=time(0),close_time=time(23,59));open_controller=AutomationController(o,open_session);allowed=AutomationJob("OPEN","open","FULL_MARKET_ANALYSIS",True,"ANALYSIS_ONLY","ONCE",template,now,requires_market_hours=True);open_controller.register(allowed);assert open_controller.tick(now)[0].status=="COMPLETED";print("[PASS] Market Hours Allowed")
 stub=StubOrchestrator(["COMPLETED","FAILED","COMPLETED"]);batch_controller=AutomationController(stub);batch_template=JarvisRequest("BATCH","FULL_ANALYSIS",now,"JARVIS","NSE","000001",parameters={"instruments":("ONE","BAD","TWO")});batch=AutomationJob("BATCH","batch","FNO_ANALYSIS",True,"ANALYSIS_ONLY","ONCE",batch_template,now,max_instruments_per_run=2,continue_on_error=True);batch_controller.register(batch);run=batch_controller.tick(now)[0];assert run.status=="FAILED" and len(run.item_results)==2 and len(stub.calls)==2;print("[PASS] Batch Partial Failure Limit Continue")
 auth_controller=AutomationController(o);auth=AutomationJob("AUTH","auth","PAPER_POSITION_MONITOR",True,"PAPER","ONCE",template,now,requires_user_authorization=True);auth_controller.register(auth);assert auth_controller.tick(now)[0].status=="AUTHORIZATION_REQUIRED";print("[PASS] Authorization Gate")
 class Failing:
  def handle(self,request):raise ConnectionError("offline")
 retry_controller=AutomationController(Failing());retry=AutomationJob("RETRY","retry","FNO_UNIVERSE_REFRESH",True,"ANALYSIS_ONLY","ONCE",template,now,max_retries=1);retry_controller.register(retry);assert retry_controller.tick(now)[0].status=="RETRY_PENDING" and retry_controller.tick(now)[0].status=="FAILED";print("[PASS] Bounded Retry")
 assert batch_controller.history and all("000001" not in " ".join(item.warnings+item.errors) for item in batch_controller.history);print("[PASS] Run History Secret Safe")
 overlap_controller=AutomationController(o);overlap=AutomationJob("OVER","overlap","FULL_MARKET_ANALYSIS",True,"ANALYSIS_ONLY","ONCE",template,now);overlap_controller.register(overlap);overlap_controller._running.add("OVER");assert not overlap_controller.tick(now);print("[PASS] Overlap Prevention")
 class Invalid:
  def handle(self,request):raise ValueError("invalid")
 invalid_controller=AutomationController(Invalid());invalid=AutomationJob("INVALID","invalid","FNO_UNIVERSE_REFRESH",True,"ANALYSIS_ONLY","ONCE",template,now,max_retries=3);invalid_controller.register(invalid);assert invalid_controller.tick(now)[0].status=="FAILED";print("[PASS] Non Retryable Failure")
 successful_stub=StubOrchestrator(["COMPLETED","COMPLETED"]);success_controller=AutomationController(successful_stub);success_job=AutomationJob("SUCCESS","success","FNO_ANALYSIS",True,"ANALYSIS_ONLY","ONCE",batch_template,now,max_instruments_per_run=2);success_controller.register(success_job);assert success_controller.tick(now)[0].status=="COMPLETED" and len(successful_stub.calls)==2;print("[PASS] Batch Success")
 stop_stub=StubOrchestrator(["FAILED","COMPLETED"]);stop_controller=AutomationController(stop_stub);stop_job=AutomationJob("STOP","stop","FNO_ANALYSIS",True,"ANALYSIS_ONLY","ONCE",batch_template,now,max_instruments_per_run=2,continue_on_error=False);stop_controller.register(stop_job);assert len(stop_controller.tick(now)[0].item_results)==1;print("[PASS] Batch Stop On Error")
 routing_stub=StubOrchestrator();routing_controller=AutomationController(routing_stub)
 for job_id,job_type,request_type in (("FNO","FNO_UNIVERSE_REFRESH","MARKET_CONTEXT"),("PORT","PORTFOLIO_SNAPSHOT","PORTFOLIO_ANALYSIS"),("MON","PAPER_POSITION_MONITOR","PAPER_EXECUTE")):
  routing_controller.register(AutomationJob(job_id,job_id,job_type,True,"PAPER" if job_id=="MON" else "ANALYSIS_ONLY","ONCE",JarvisRequest(job_id,request_type,now,"JARVIS",parameters={}),now,requires_user_authorization=job_id=="MON"))
 routed=routing_controller.tick(now);assert len(routing_stub.calls)==2 and any(run.status=="AUTHORIZATION_REQUIRED" for run in routed);print("[PASS] FNO Portfolio Paper Routing")
 assert {event.status for event in c.history[0].orchestrator_result.audit_events}>={"STARTED","COMPLETED"} and run.status=="FAILED";print("[PASS] Delegated Audit Statuses")
 return 0
if __name__=="__main__":sys.exit(main())