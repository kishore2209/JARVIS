from dataclasses import dataclass
from datetime import datetime, timezone
import os
import re

SECRET_WORDS=("angel_one_api_key","angel_one_client_code","angel_one_pin","angel_one_totp","access_token","refresh_token","authorization","session_token","auth_header","password")
def sanitize(value):
    if isinstance(value,dict):return {key:("<redacted>" if key.lower() in SECRET_WORDS else sanitize(item)) for key,item in value.items()}
    if isinstance(value,(list,tuple)):return [sanitize(item) for item in value]
    if isinstance(value,str) and ("bearer " in value.lower() or any(key+"=" in value.lower() for key in SECRET_WORDS)):return "<redacted>"
    return value
@dataclass(frozen=True)
class OperationalEvent:
    timestamp:datetime;level:str;component:str;event_type:str;request_id:str|None;job_id:str|None;run_id:str|None;instrument:str|None;execution_mode:str|None;status:str;duration_ms:int|None;message:str;metadata:dict
class Observability:
    def __init__(self):self.events=[];self.counters={}
    def record(self,component,event_type,status="COMPLETED",request_id=None,job_id=None,run_id=None,instrument=None,execution_mode=None,duration_ms=None,message="",metadata=None):
        event=OperationalEvent(datetime.now(timezone.utc),"INFO" if status=="COMPLETED" else "ERROR",component,event_type,request_id,job_id,run_id,instrument,execution_mode,status,duration_ms,sanitize(message),sanitize(metadata or {}));self.events.append(event);self.counters["requests_total"]=self.counters.get("requests_total",0)+1
        if event.level=="ERROR":self.counters["requests_failed"]=self.counters.get("requests_failed",0)+1
        return event
    def snapshot(self):return {"counters":dict(sorted(self.counters.items())),"recent_events":[sanitize(event.__dict__) for event in self.events[-10:] ]}
    def provider_error(self,provider,operation,instrument,error,retryable=False):
        self.counters["provider_errors"]=self.counters.get("provider_errors",0)+1
        return self.record("PROVIDER","ERROR","FAILED",instrument=instrument,message=type(error).__name__,metadata={"provider":provider,"operation":operation,"retryable":retryable})
    def health(self,persistence_enabled=False,provider_configured=False):return {"system":"HEALTHY","orchestrator":"HEALTHY","automation":"HEALTHY","persistence":"HEALTHY" if persistence_enabled else "DEGRADED","provider":"CONFIGURED" if provider_configured else "DEGRADED","live_execution_supported":False}
    def readiness(self,workflow="ANALYSIS_ONLY",provider_configured=False):
        if workflow=="LIVE":return {"workflow":workflow,"ready":False,"status":"NOT_READY","requirements":{},"reasons":["LIVE_EXECUTION_UNSUPPORTED"]}
        ready=workflow!="REAL_PROVIDER_ANALYSIS" or provider_configured
        return {"workflow":workflow,"ready":ready,"status":"READY" if ready else "NOT_READY","requirements":{"provider_configured":provider_configured,"persistence_optional":True},"reasons":[] if ready else ["provider configuration missing"]}
def configuration_status():return {name.lower()+"_configured":bool(os.getenv(name)) for name in ("ANGEL_ONE_API_KEY","ANGEL_ONE_CLIENT_CODE","ANGEL_ONE_PIN","ANGEL_ONE_TOTP")}

@dataclass(frozen=True)
class GuardrailConfig:
    max_instruments_per_run:int=100;max_batch_size:int=25;max_jobs_per_tick:int=25;max_retries:int=5;max_request_items:int=500;max_correlation_id_length:int=128
def validate_configuration(config=GuardrailConfig(),db_path=None,timezone_name="Asia/Kolkata",execution_mode="ANALYSIS_ONLY"):
    errors=[]
    if any(value<=0 for value in (config.max_instruments_per_run,config.max_batch_size,config.max_jobs_per_tick,config.max_request_items,config.max_correlation_id_length)):errors.append("guardrail limits must be positive")
    if config.max_retries<0:errors.append("max_retries cannot be negative")
    if timezone_name!="Asia/Kolkata":errors.append("unsupported timezone")
    if execution_mode not in {"ANALYSIS_ONLY","PAPER","HISTORICAL_REPLAY"}:errors.append("unsupported execution mode")
    if db_path is not None and not isinstance(db_path,str):errors.append("invalid database path")
    return {"valid":not errors,"errors":errors,"limits":{"max_instruments_per_run":config.max_instruments_per_run,"max_batch_size":config.max_batch_size,"max_jobs_per_tick":config.max_jobs_per_tick,"max_retries":config.max_retries,"max_request_items":config.max_request_items,"max_correlation_id_length":config.max_correlation_id_length}}