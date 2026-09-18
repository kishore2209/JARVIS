from dataclasses import dataclass, replace
from datetime import datetime, time, timedelta, timezone

from core.orchestrator import JarvisRequest

IST = timezone(timedelta(hours=5, minutes=30), "Asia/Kolkata")

@dataclass(frozen=True)
class MarketSession:
    timezone: object = IST
    open_time: time = time(9, 15)
    close_time: time = time(15, 30)
    weekdays: tuple = (0, 1, 2, 3, 4)
    def is_open(self, timestamp):
        local = timestamp.astimezone(self.timezone)
        return local.weekday() in self.weekdays and self.open_time <= local.time() <= self.close_time

@dataclass(frozen=True)
class AutomationJob:
    job_id: str; name: str; job_type: str; enabled: bool; execution_mode: str; schedule_type: str; request_template: JarvisRequest; created_at: datetime; interval: timedelta | None = None; daily_time: time | None = None; last_run_at: datetime | None = None; next_run_at: datetime | None = None; max_retries: int = 0; timeout_seconds: int = 30; requires_market_hours: bool = False; requires_user_authorization: bool = False; source: str = "AUTOMATION"; max_instruments_per_run: int = 1; batch_size: int = 1; continue_on_error: bool = True

@dataclass(frozen=True)
class AutomationRunResult:
    run_id: str; job_id: str; occurrence: datetime; started_at: datetime; completed_at: datetime; status: str; orchestrator_result: object | None; item_results: tuple; warnings: tuple; errors: tuple; retry_count: int; execution_mode: str; source: str; is_fresh: bool | None

class AutomationController:
    """Explicit-tick, in-memory scheduler. It never loops or creates authorization."""
    def __init__(self, orchestrator, market_session=None, observability=None, max_jobs_per_tick=None):
        self.orchestrator = orchestrator; self.market_session = market_session or MarketSession(); self.observability=observability; self.max_jobs_per_tick=max_jobs_per_tick; self.jobs = {}; self.history = []; self._occurrences = set(); self._running = set(); self._retries = {}
    def register(self, job):
        if job.execution_mode == "LIVE": raise ValueError("LIVE automation is unsupported.")
        if job.schedule_type not in {"ONCE", "INTERVAL", "DAILY_TIME"}: raise ValueError("Unsupported schedule type.")
        if job.schedule_type == "INTERVAL" and not job.interval: raise ValueError("INTERVAL jobs require an interval.")
        if job.schedule_type == "DAILY_TIME" and not job.daily_time: raise ValueError("DAILY_TIME jobs require daily_time.")
        if job.max_instruments_per_run <= 0 or job.batch_size <= 0 or job.batch_size > job.max_instruments_per_run: raise ValueError("Invalid automation batch limits.")
        if job.max_retries < 0: raise ValueError("max_retries cannot be negative.")
        self.jobs[job.job_id] = job
    def hydrate_state(self, jobs=(), history=(), occurrences=(), retries=()):
        """Hydrates persisted state only; callers must explicitly invoke tick()."""
        self.jobs.update({job.job_id:job for job in jobs}); self.history.extend(history); self._occurrences.update(occurrences); self._retries.update(dict(retries))
    def set_enabled(self, job_id, enabled): self.jobs[job_id] = replace(self.jobs[job_id], enabled=enabled)
    def due_jobs(self, now): return [job for job in self.jobs.values() if self._due(job, now)]
    def tick(self, now):
        due=self.due_jobs(now)
        if self.max_jobs_per_tick is not None and len(due)>self.max_jobs_per_tick:
            if self.observability:self.observability.record("AUTOMATION","GUARDRAIL","RATE_LIMITED",message="max_jobs_per_tick exceeded")
            due=due[:self.max_jobs_per_tick]
        return tuple(self._run(job, now) for job in due)
    def _due(self, job, now):
        if not job.enabled or job.job_id in self._running: return False
        occurrence = self._occurrence(job, now)
        if f"{job.job_id}:{occurrence.isoformat()}" in self._occurrences: return False
        if job.schedule_type == "ONCE": return job.last_run_at is None and now >= job.created_at
        if job.schedule_type == "INTERVAL": return now >= (job.next_run_at or job.created_at)
        local = now.astimezone(self.market_session.timezone); scheduled = datetime.combine(local.date(), job.daily_time, self.market_session.timezone)
        return local >= scheduled and (job.last_run_at is None or job.last_run_at.astimezone(self.market_session.timezone).date() != local.date())
    def _run(self, job, now):
        occurrence = self._occurrence(job, now); run_id = f"{job.job_id}:{occurrence.isoformat()}"
        if run_id in self._occurrences or job.job_id in self._running: return self._record(job, occurrence, now, "SKIPPED", None, (), ("Duplicate or overlapping occurrence.",), ())
        if job.requires_market_hours and not self.market_session.is_open(now): return self._record(job, occurrence, now, "SKIPPED", None, (), ("Outside configured market session; holiday calendar not modeled.",), ())
        if job.requires_user_authorization and not job.request_template.explicit_user_authorization: return self._record(job, occurrence, now, "AUTHORIZATION_REQUIRED", None, (), ("Explicit user authorization required.",), ())
        self._running.add(job.job_id); self._occurrences.add(run_id)
        try:
            results = self._execute(job, now); failures = [result for result in results if result.status != "COMPLETED"]
            status = "COMPLETED" if not failures else "FAILED"
            return self._record(job, occurrence, now, status, results[0] if results else None, results, (), tuple(result.status for result in failures))
        except Exception as error:
            retry = self._retries.get(run_id, 0)
            self._retries[run_id] = retry + 1
            status = "RETRY_PENDING" if retry < job.max_retries and type(error).__name__ not in {"ValueError", "PermissionError"} else "FAILED"
            if status == "RETRY_PENDING":
                self._occurrences.discard(run_id)
            return self._record(job, occurrence, now, status, None, (), (), (f"{type(error).__name__}: {error}",), retry)
        finally: self._running.discard(job.job_id)
    def _execute(self, job, now):
        template = job.request_template
        instruments = (template.parameters or {}).get("instruments", (template.instrument,))
        results = []
        for instrument in tuple(instruments)[:job.max_instruments_per_run]:
            request = replace(template, request_id=f"{template.request_id}:{instrument}:{now.isoformat()}", timestamp=now, instrument=instrument)
            result = self.orchestrator.handle(request); results.append(result)
            if result.status != "COMPLETED" and not job.continue_on_error: break
        return tuple(results)
    def _record(self, job, occurrence, now, status, result, items, warnings, errors, retry_count=0):
        run = AutomationRunResult(f"{job.job_id}:{occurrence.isoformat()}", job.job_id, occurrence, now, now, status, result, tuple(items), tuple(warnings), tuple(errors), retry_count, job.execution_mode, job.source, getattr(result, "is_fresh", None))
        self.history.append(run)
        if self.observability and status != "SKIPPED":
            self.observability.record("AUTOMATION","RUN",status,job_id=job.job_id,run_id=run.run_id,execution_mode=job.execution_mode,message="automation run",metadata={"retry_count":retry_count})
            self.observability.counters["automation_runs_total"]=self.observability.counters.get("automation_runs_total",0)+1
            if status in {"FAILED","RETRY_PENDING"}:self.observability.counters["automation_failures"]=self.observability.counters.get("automation_failures",0)+1
        if status in {"COMPLETED", "FAILED", "AUTHORIZATION_REQUIRED", "SKIPPED"}: self.jobs[job.job_id] = replace(job, last_run_at=now, next_run_at=now + job.interval if job.interval else None)
        return run
    def _occurrence(self, job, now):
        if job.schedule_type == "DAILY_TIME": return now.astimezone(self.market_session.timezone).replace(hour=job.daily_time.hour, minute=job.daily_time.minute, second=0, microsecond=0).astimezone(timezone.utc)
        return job.next_run_at or job.created_at