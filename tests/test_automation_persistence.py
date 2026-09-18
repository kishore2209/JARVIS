import os,sys,tempfile
from datetime import datetime,time,timedelta,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT))
from core.automation import AutomationController,AutomationJob
from core.orchestrator import JarvisOrchestrator,JarvisRequest
from market.persistence import AutomationJobRepository,AutomationOccurrenceRepository,AutomationRunRepository,PersistenceRestoreService,SQLiteStore
from market.providers.mock import MockMarketDataProvider
def main():
 path=tempfile.mktemp(suffix=".db");t=datetime(2026,1,2,13,14,tzinfo=timezone.utc);request=JarvisRequest("A","FULL_ANALYSIS",t,"JARVIS","NSE","000001")
 jobs=(AutomationJob("ONCE","once","FULL_MARKET_ANALYSIS",True,"ANALYSIS_ONLY","ONCE",request,t),AutomationJob("INT","interval","FULL_MARKET_ANALYSIS",True,"ANALYSIS_ONLY","INTERVAL",request,t,interval=timedelta(minutes=5),max_retries=2),AutomationJob("DAY","daily","MARKET_CONTEXT_REFRESH",False,"ANALYSIS_ONLY","DAILY_TIME",request,t,daily_time=time(15,30)))
 store=SQLiteStore(path);repository=AutomationJobRepository(store)
 for job in jobs:repository.save(job.job_id,job)
 key=f"ONCE:{t.isoformat()}";retry_key=f"INT:{t.isoformat()}";AutomationOccurrenceRepository(store).save(key,{"key":key});AutomationOccurrenceRepository(store).save(retry_key,{"key":retry_key,"retry_pending":True,"retry_count":1});run={"run_id":"RUN-1","job_id":"ONCE","occurrence":t,"started_at":t,"completed_at":t,"status":"COMPLETED","warnings":[],"errors":[],"retry_count":0,"execution_mode":"ANALYSIS_ONLY","source":"AUTOMATION","is_fresh":True};AutomationRunRepository(store).save("RUN-1",run);store.close()
 store=SQLiteStore(path);controller=AutomationController(JarvisOrchestrator(MockMarketDataProvider()));PersistenceRestoreService(store).restore_automation(controller)
 assert len(controller.jobs)==3 and controller.jobs["DAY"].enabled is False and controller.jobs["INT"].interval==timedelta(minutes=5) and controller.jobs["DAY"].daily_time==time(15,30) and len(controller.history)==1;print("[PASS] Typed Jobs Runs Schedules Restore")
 assert key in controller._occurrences and retry_key not in controller._occurrences and controller._retries[retry_key]==1
 runs=controller.tick(t);assert retry_key in controller._occurrences and all(run.job_id!="ONCE" for run in runs);print("[PASS] Occurrence Retry Restart Idempotency")
 try:AutomationJobRepository(store).save("ONCE",jobs[0]);AutomationRunRepository(store).save("RUN-1",run);AutomationOccurrenceRepository(store).save(key,{"key":key})
 except ValueError:print("[PASS] Duplicate Database Protection")
 else:raise AssertionError("duplicate accepted")
 store.connection.execute("INSERT INTO automation_jobs VALUES ('BAD','{}')");store.connection.commit()
 try:PersistenceRestoreService(store).restore_automation(AutomationController(JarvisOrchestrator(MockMarketDataProvider())))
 except (ValueError,KeyError):print("[PASS] Malformed Automation Rejected")
 else:raise AssertionError("malformed state accepted")
 store.close();os.remove(path)
 path=tempfile.mktemp(suffix=".db");store=SQLiteStore(path);base=JarvisOrchestrator(MockMarketDataProvider());interval=AutomationJob("I","interval","FULL_MARKET_ANALYSIS",True,"ANALYSIS_ONLY","INTERVAL",request,t,interval=timedelta(minutes=5),last_run_at=t,next_run_at=t+timedelta(minutes=5));daily=AutomationJob("D","daily","MARKET_CONTEXT_REFRESH",True,"ANALYSIS_ONLY","DAILY_TIME",request,t,daily_time=time(18),last_run_at=t);disabled=AutomationJob("X","disabled","FULL_MARKET_ANALYSIS",False,"ANALYSIS_ONLY","ONCE",request,t)
 for job in (interval,daily,disabled):AutomationJobRepository(store).save(job.job_id,job)
 interval_key=f"I:{t.isoformat()}";daily_time=t.replace(hour=12,minute=30);daily_key=f"D:{daily_time.isoformat()}";AutomationOccurrenceRepository(store).save(interval_key,{"key":interval_key});AutomationOccurrenceRepository(store).save(daily_key,{"key":daily_key});store.close()
 store=SQLiteStore(path);restored=AutomationController(base);PersistenceRestoreService(store).restore_automation(restored);before=len(restored.history);assert not restored.tick(t) and len(restored.history)==before;assert restored.tick(t+timedelta(minutes=5));next_daily=t+timedelta(days=1,hours=5,minutes=30);assert restored.tick(next_daily) and not restored.tick(next_daily);print("[PASS] Interval Daily Disabled Restart")
 run_a={"run_id":"R-A","job_id":"I","occurrence":t,"started_at":t,"completed_at":t,"status":"COMPLETED","warnings":[],"errors":[],"retry_count":0,"execution_mode":"ANALYSIS_ONLY","source":"AUTO","is_fresh":True};run_b={**run_a,"run_id":"R-B","status":"RETRY_PENDING","retry_count":1};AutomationRunRepository(store).save("R-A",run_a);AutomationRunRepository(store).save("R-B",run_b);store.close();store=SQLiteStore(path);history_controller=AutomationController(base);PersistenceRestoreService(store).restore_automation(history_controller);assert [run.run_id for run in history_controller.history]==["R-A","R-B"] and history_controller.history[1].retry_count==1;print("[PASS] Run History Restore")
 store.close();os.remove(path)
 class Transient:
  def handle(self,request):raise ConnectionError("offline")
 path=tempfile.mktemp(suffix=".db");store=SQLiteStore(path);retry_job=AutomationJob("RETRY","retry","FNO_UNIVERSE_REFRESH",True,"ANALYSIS_ONLY","ONCE",request,t,max_retries=2);AutomationJobRepository(store).save("RETRY",retry_job);first=AutomationController(Transient());first.register(retry_job);first_run=first.tick(t)[0];retry_key=f"RETRY:{t.isoformat()}";assert first_run.status=="RETRY_PENDING" and first._retries[retry_key]==1;AutomationOccurrenceRepository(store).save(retry_key,{"key":retry_key,"retry_pending":True,"retry_count":1});store.close()
 store=SQLiteStore(path);second=AutomationController(Transient());PersistenceRestoreService(store).restore_automation(second);assert second._retries[retry_key]==1;second_run=second.tick(t)[0];assert second_run.status=="RETRY_PENDING" and second._retries[retry_key]==2;AutomationOccurrenceRepository(store).update(retry_key,{"key":retry_key,"retry_pending":True,"retry_count":2});store.close()
 store=SQLiteStore(path);third=AutomationController(Transient());PersistenceRestoreService(store).restore_automation(third);terminal=third.tick(t)[0];assert terminal.status=="FAILED" and third._retries[retry_key]==3;AutomationOccurrenceRepository(store).update(retry_key,{"key":retry_key,"retry_count":2});store.close()
 store=SQLiteStore(path);fourth=AutomationController(Transient());PersistenceRestoreService(store).restore_automation(fourth);assert not fourth.tick(t);print("[PASS] Retry Exhaustion Across Restart")
 store.close();os.remove(path);return 0


if __name__=="__main__":main()