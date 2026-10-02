"""Durable read-only jobs, local alerts and morning reports.

Handlers are allowlisted deterministic reads. A crashed lease may be retried;
therefore external writes and paper orders are deliberately not job handlers.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import time
from uuid import uuid4
from zoneinfo import ZoneInfo
from core.interface_service import serialize


class JobService:
    def __init__(self, store, personal):
        self.store, self.personal = store, personal
        with store.connection:
            store.connection.execute('CREATE TABLE IF NOT EXISTS scheduled_jobs (id TEXT PRIMARY KEY, kind TEXT NOT NULL, next_at TEXT NOT NULL, interval_seconds INTEGER NOT NULL, enabled INTEGER NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, lease_until TEXT, claim TEXT, last_status TEXT, last_error TEXT)')
            store.connection.execute('CREATE TABLE IF NOT EXISTS job_results (occurrence TEXT PRIMARY KEY, job_id TEXT NOT NULL, payload TEXT NOT NULL, completed_at TEXT NOT NULL)')
            store.connection.execute('CREATE TABLE IF NOT EXISTS local_alerts (id TEXT PRIMARY KEY, event_key TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL)')
        self.handlers = {'DAILY_PLAN': lambda now:self.personal.daily_plan(now), 'MORNING_BRIEF': self.morning_brief}

    def register(self, identifier, kind, next_at, interval_seconds=86400):
        if not isinstance(identifier,str) or not identifier or len(identifier)>100: raise ValueError('Invalid job ID')
        if kind not in self.handlers: raise ValueError('Only allowlisted read-only jobs are supported')
        if next_at.tzinfo is None: raise ValueError('Aware schedule required')
        if type(interval_seconds) is not int or not 60<=interval_seconds<=366*86400: raise ValueError('Invalid job interval')
        with self.store.connection:
            self.store.connection.execute('INSERT INTO scheduled_jobs(id,kind,next_at,interval_seconds,enabled) VALUES (?,?,?,?,1)',(identifier,kind,next_at.astimezone(timezone.utc).isoformat(),interval_seconds))
        return self.list()

    def list(self):
        return [{k:r[k] for k in ('id','kind','next_at','interval_seconds','enabled','attempts','lease_until','last_status','last_error')} for r in self.store.connection.execute('SELECT * FROM scheduled_jobs ORDER BY id')]

    def set_enabled(self,identifier,enabled):
        if type(enabled) is not bool: raise ValueError('Enabled must be boolean')
        with self.store.connection:
            if enabled:
                changed = self.store.connection.execute('UPDATE scheduled_jobs SET enabled=1 WHERE id=?',(identifier,))
            else:
                # Invalidate the running claim. Re-enabling must never revive
                # a result produced by a worker that was cancelled earlier.
                changed = self.store.connection.execute("UPDATE scheduled_jobs SET enabled=0,claim=NULL,lease_until=NULL,attempts=0,last_status='CANCELLED',last_error=NULL WHERE id=?",(identifier,))
            if not changed.rowcount:raise ValueError('Unknown job')
        return self.list()

    def tick(self,now=None):
        now=now or datetime.now(timezone.utc)
        if now.tzinfo is None:raise ValueError('Aware tick required')
        now=now.astimezone(timezone.utc);out=[]
        for _ in range(10):
            claim=uuid4().hex
            with self.store.connection:
                self.store.connection.execute('BEGIN IMMEDIATE')
                row=self.store.connection.execute('SELECT * FROM scheduled_jobs WHERE enabled=1 AND next_at<=? AND (lease_until IS NULL OR lease_until<=?) ORDER BY next_at,id LIMIT 1',(now.isoformat(),now.isoformat())).fetchone()
                if not row:break
                # Exhausted crash/retry attempts are visible and disabled; no infinite loop.
                if row['attempts']>=3:
                    self.store.connection.execute("UPDATE scheduled_jobs SET enabled=0,last_status='FAILED',last_error='RETRY_EXHAUSTED',lease_until=NULL WHERE id=?",(row['id'],));continue
                self.store.connection.execute("UPDATE scheduled_jobs SET claim=?,lease_until=?,attempts=attempts+1,last_status='RUNNING' WHERE id=?",(claim,(now+timedelta(minutes=5)).isoformat(),row['id']))
            occurrence=row['id']+':'+row['next_at']
            started=time.monotonic()
            try:
                result=self.handlers[row['kind']](now)
                encoded=json.dumps(serialize(result),sort_keys=True,allow_nan=False)
                with self.store.connection:
                    self.store.connection.execute('BEGIN IMMEDIATE')
                    current=self.store.connection.execute('SELECT enabled,claim,lease_until FROM scheduled_jobs WHERE id=?',(row['id'],)).fetchone()
                    if current['claim']!=claim or not current['enabled']:continue
                    if now+timedelta(seconds=time.monotonic()-started)>=datetime.fromisoformat(current['lease_until']):
                        continue  # Expired work cannot publish; the lease is recoverable.
                    self.store.connection.execute('INSERT OR IGNORE INTO job_results VALUES (?,?,?,?)',(occurrence,row['id'],encoded,now.isoformat()))
                    due=datetime.fromisoformat(row['next_at']);interval=timedelta(seconds=row['interval_seconds'])
                    next_at=due+(max(0,(now-due)//interval)+1)*interval
                    self.store.connection.execute("UPDATE scheduled_jobs SET next_at=?,attempts=0,lease_until=NULL,claim=NULL,last_status='SUCCEEDED',last_error=NULL WHERE id=? AND claim=?",(next_at.isoformat(),row['id'],claim))
                out.append({'job_id':row['id'],'status':'SUCCEEDED','occurrence':occurrence})
            except Exception as exc:
                permanent=isinstance(exc,(ValueError,PermissionError))
                exhausted=row['attempts']+1>=3 or permanent
                with self.store.connection:
                    changed=self.store.connection.execute('UPDATE scheduled_jobs SET enabled=?,last_status=?,last_error=?,lease_until=?,claim=NULL WHERE id=? AND claim=? AND enabled=1',(0 if exhausted else 1,'FAILED' if exhausted else 'RETRY_PENDING',type(exc).__name__,(now+timedelta(minutes=1)).isoformat(),row['id'],claim))
                    if not changed.rowcount:continue
                out.append({'job_id':row['id'],'status':'FAILED' if exhausted else 'RETRY_PENDING'})
        return out

    def results(self,limit=50):
        if not 1<=limit<=200:raise ValueError('Invalid result limit')
        return [{'occurrence':r['occurrence'],'completed_at':r['completed_at'],'result':json.loads(r['payload'])} for r in self.store.connection.execute('SELECT * FROM job_results ORDER BY completed_at DESC LIMIT ?',(limit,))]

    def morning_brief(self,now):
        return {'generated_at':now.isoformat(),'status':'PARTIAL','sections':{'market_regime':{'status':'DATA_MISSING'},'sectors':{'status':'DATA_MISSING'},'holdings':{'status':'DATA_MISSING'},'news':{'status':'DATA_MISSING'},'fno_setups':{'status':'DATA_MISSING'},'risk':{'status':'DATA_MISSING'},'trade_review':{'status':'DATA_MISSING'},'lesson':{'status':'DATA_MISSING'},'financial_goals':self.personal.finance_summary(now)['goals'],'daily_plan':self.personal.daily_plan(now)},'warnings':['Market sources are not configured for this report. No trade shortlist has been generated.'],'delivery':'LOCAL_ONLY'}

    def alert(self,event_key,message,severity='INFORMATIONAL',now=None,cooldown_seconds=300,quiet_start=22,quiet_end=7,critical_bypass=False):
        if not isinstance(event_key,str) or not event_key or len(event_key)>200 or not isinstance(message,str) or not message or len(message)>2000:raise ValueError('Invalid alert')
        if severity not in {'INFORMATIONAL','ATTENTION','WARNING','CRITICAL'}:raise ValueError('Invalid severity')
        if type(cooldown_seconds) is not int or cooldown_seconds<0 or not 0<=quiet_start<=23 or not 0<=quiet_end<=23:raise ValueError('Invalid alert policy')
        now=now or datetime.now(timezone.utc)
        if now.tzinfo is None:raise ValueError('Aware alert time required')
        now=now.astimezone(timezone.utc)
        hour=now.astimezone(ZoneInfo('Asia/Kolkata')).hour
        quiet=(hour>=quiet_start or hour<quiet_end) if quiet_start>quiet_end else quiet_start<=hour<quiet_end
        payload={'message':message,'severity':severity,'source_timestamp':now.isoformat(),'delivery_status':'DEFERRED_QUIET_HOURS' if quiet and not (severity=='CRITICAL' and critical_bypass) else 'LOCAL_ONLY'}
        with self.store.connection:
            self.store.connection.execute('BEGIN IMMEDIATE')
            old=self.store.connection.execute('SELECT id,created_at FROM local_alerts WHERE event_key=? ORDER BY created_at DESC LIMIT 1',(event_key,)).fetchone()
            if old and now-datetime.fromisoformat(old['created_at'])<timedelta(seconds=cooldown_seconds):return {'id':old['id'],'deduplicated':True}
            identifier=hashlib.sha256((event_key+now.isoformat()).encode()).hexdigest()
            self.store.connection.execute('INSERT OR IGNORE INTO local_alerts VALUES (?,?,?,?)',(identifier,event_key,json.dumps(payload),now.isoformat()))
        return {'id':identifier,'deduplicated':False,**payload}

    def alerts(self):return [{'id':r['id'],'event_key':r['event_key'],**json.loads(r['payload'])} for r in self.store.connection.execute('SELECT * FROM local_alerts ORDER BY created_at DESC LIMIT 100')]
