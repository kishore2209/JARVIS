from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal

from core.orchestrator import JarvisRequest

SECRET_NAMES = ("ANGEL_ONE_API_KEY", "ANGEL_ONE_CLIENT_CODE", "ANGEL_ONE_PIN", "ANGEL_ONE_TOTP")

def serialize(value):
    if is_dataclass(value): return {key: serialize(item) for key, item in asdict(value).items()}
    if isinstance(value, (datetime, date)): return value.isoformat()
    if isinstance(value, Decimal): return str(value)
    if isinstance(value, dict): return {str(key): serialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)): return [serialize(item) for item in value]
    return value

class JarvisInterfaceService:
    """Thin input validation and serialization adapter over JarvisOrchestrator."""
    def __init__(self, orchestrator, automation=None): self.orchestrator=orchestrator;self.automation=automation
    def request(self, payload):
        try:
            mode=payload.get("execution_mode","ANALYSIS_ONLY")
            if mode=="LIVE": return self._error("LIVE_EXECUTION_UNSUPPORTED","LIVE execution is unsupported.")
            if mode not in {"ANALYSIS_ONLY","PAPER","HISTORICAL_REPLAY"}: return self._error("INVALID_REQUEST","Unsupported execution mode.")
            kind=payload.get("request_type")
            if not kind: return self._error("INVALID_REQUEST","request_type is required.")
            timestamp=payload.get("timestamp") or datetime.now().astimezone()
            if isinstance(timestamp,str): timestamp=datetime.fromisoformat(timestamp)
            if timestamp.tzinfo is None: return self._error("INVALID_REQUEST","timestamp must be timezone-aware.")
            request=JarvisRequest(payload.get("request_id","INTERFACE"),kind,timestamp,payload.get("instrument"),payload.get("exchange","NSE"),payload.get("token"),payload.get("interval","15m"),payload.get("data_source","PROVIDER"),mode,payload.get("parameters"),payload.get("explicit_user_authorization",False),payload.get("source","INTERFACE"))
            result=self.orchestrator.handle(request)
            if result.status in {"AUTHORIZATION_REQUIRED","RISK_REJECTED","LIVE_EXECUTION_UNSUPPORTED"}: return self._error(result.status,result.status,result)
            return {"status":"OK","result":serialize(result)}
        except (ValueError, TypeError) as error: return self._error("INVALID_REQUEST",str(error))
        except Exception as error: return self._error("INTERNAL_ERROR",self._safe(str(error)))
    def status(self): return {"status":"OK","application_status":"ONLINE","orchestrator_available":self.orchestrator is not None,"automation_available":self.automation is not None,"paper_engine_available":True,"live_execution_supported":False}
    def automation_jobs(self): return {"status":"OK","jobs":serialize(tuple(self.automation.jobs.values())) if self.automation else []}
    def automation_history(self): return {"status":"OK","history":serialize(tuple(self.automation.history)) if self.automation else []}
    def automation_tick(self, timestamp):
        if self.automation is None:return self._error("DATA_NOT_AVAILABLE","Automation is not configured.")
        return {"status":"OK","runs":serialize(self.automation.tick(timestamp))}
    def _error(self,code,message,result=None): return {"status":"ERROR","code":code,"message":self._safe(message),"details":[],"result":serialize(result) if result else None}
    @staticmethod
    def _safe(message):
        for name in SECRET_NAMES:
            message=message.replace(name,"<redacted>")
        return message