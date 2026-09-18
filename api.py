from datetime import datetime, timezone
from time import perf_counter
from decimal import Decimal
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from core.automation import AutomationController
from core.observability import Observability, configuration_status, validate_configuration
from core.interface_service import JarvisInterfaceService
from core.conversation import ConversationRequest, JarvisConversationService
from core.llm import LLMConfig, build_external_llm_from_env
from core.runtime import RuntimeConfig, create_runtime, JARVIS_VERSION
from core.memory import MemoryCategory, MemoryScope, MemoryValidationError
from core.tools import ToolValidationError
from contextlib import asynccontextmanager
from core.interface_service import serialize
from core.orchestrator import JarvisOrchestrator
from market.backtest import BacktestConfig, HistoricalReplayEngine
from market.paper_trading import PaperAccount, PaperTradingEngine
from market.ohlcv import OHLCV
from market.providers.mock import MockMarketDataProvider
from market.risk import TradeProposal

runtime = create_runtime()
observability = runtime.observability
orchestrator = runtime.orchestrator
paper_engine = runtime.paper_engine
automation = runtime.automation
tools = runtime.tools
workflows = runtime.workflows
connectors = runtime.connectors
projects = runtime.projects
delivery = runtime.delivery
governance = runtime.governance
service = runtime.interface_service
llm_config = runtime.config.llm
conversation = runtime.conversation

@asynccontextmanager
async def lifespan(_app):
	observability.record("RUNTIME", "APPLICATION_READY", "COMPLETED", message="application ready")
	try:
		yield
	finally:
		runtime.close()

app=FastAPI(title="JARVIS API", version=JARVIS_VERSION, lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=list(runtime.config.cors_origins),allow_methods=["GET","POST"],allow_headers=["Content-Type","X-Correlation-ID"])
@app.middleware("http")
async def telemetry(request: Request, call_next):
	started=perf_counter(); correlation=request.headers.get("X-Correlation-ID","")[:128] or "API"
	request.state.correlation_id=correlation
	response=await call_next(request)
	response.headers["X-Content-Type-Options"]="nosniff"
	response.headers["Referrer-Policy"]="no-referrer"
	response.headers["X-Frame-Options"]="DENY"
	observability.record("API","REQUEST","COMPLETED" if response.status_code<400 else "FAILED",request_id=correlation,duration_ms=int((perf_counter()-started)*1000),message=f"{request.method} {request.url.path}")
	return response
@app.exception_handler(ValueError)
async def invalid_request(request: Request, error: ValueError):
	return JSONResponse(status_code=400, content=service._error("INVALID_REQUEST", str(error)))
@app.exception_handler(Exception)
async def internal_error(request: Request, error: Exception):
	return JSONResponse(status_code=500, content={"status":"ERROR","code":"INTERNAL_ERROR","message":"Internal server error.","details":[],"correlation_id":getattr(request.state,"correlation_id","API")})
@app.get("/health")
def health(): return {"status":"OK","version":JARVIS_VERSION,"live_execution_supported":False}
@app.get("/api/v1/status")
def status(): return service.status()
@app.get("/api/v1/metrics")
def metrics(): return observability.snapshot()
@app.get("/api/v1/readiness")
def readiness(workflow: str = "DETERMINISTIC_CHAT"):
	if workflow == "LIVE": return observability.readiness("LIVE")
	if workflow == "LLM_ENHANCED_CHAT": return observability.readiness("REAL_PROVIDER_ANALYSIS", bool(conversation.external_llm and conversation.external_llm.is_configured() and llm_config.enabled))
	return observability.readiness("ANALYSIS_ONLY")
@app.get("/api/v1/diagnostics")
def diagnostics():
	github = next((item for item in connectors.registry.safe_list() if item["connector_id"] == "github"), {})
	jira = next((item for item in connectors.registry.safe_list() if item["connector_id"] == "jira"), {})
	return {"health":observability.health(runtime.store is not None,False),"readiness":observability.readiness(),"configuration":{**runtime.config.safe_status(bool(conversation.external_llm and conversation.external_llm.is_configured())),**configuration_status(),"github_enabled":bool(github.get("enabled",False)),"github_configured":bool(github.get("configured",False)),"github_write_enabled":bool(github.get("write_enabled",False)),"jira_enabled":bool(jira.get("enabled",False)),"jira_configured":bool(jira.get("configured",False))},"guardrails":validate_configuration(db_path=runtime.config.db_path,timezone_name=runtime.config.timezone_name),"persistence_enabled":runtime.store is not None,"live_execution_supported":False,"events":observability.snapshot()["recent_events"]}
@app.get("/api/v1/governance/connectors")
def governance_list(): return {"status":"OK","profiles":governance.safe_list()}
@app.get("/api/v1/governance/connectors/{connector_id}")
def governance_show(connector_id: str): return {"status":"OK","profiles":[item for item in governance.safe_list() if item["connector_id"] == connector_id]}
@app.post("/api/v1/governance/connectors/{connector_id}/profiles")
def governance_create(connector_id: str, payload: dict):
	allowed={"allowed_capabilities","allowed_resources","environment","enabled","profile_id"}
	if set(payload)-allowed: raise ValueError("Unsupported governance field")
	return {"status":"OK","profile":_governance_payload(governance.create_profile(connector_id,payload.get("allowed_capabilities",()),payload.get("allowed_resources",()),payload.get("environment"),payload.get("enabled",True),payload.get("profile_id")))}
@app.patch("/api/v1/governance/connectors/{connector_id}/profiles/{profile_id}")
def governance_update(connector_id: str, profile_id: str, payload: dict): return {"status":"OK","profile":_governance_payload(governance.update_profile(profile_id,payload.get("allowed_capabilities"),payload.get("allowed_resources"),payload.get("enabled")))}
@app.delete("/api/v1/governance/connectors/{connector_id}/profiles/{profile_id}")
def governance_delete(connector_id: str, profile_id: str):
	if profile_id not in governance.profiles: return {"status":"ERROR","code":"PROFILE_NOT_FOUND","message":"Profile not found.","details":[]}
	del governance.profiles[profile_id]
	return {"status":"OK","deleted":True}
@app.get("/api/v1/projects")
def project_list(): return {"status":"OK","workspaces":[_project_workspace_payload(item) for item in projects.list()]}
@app.post("/api/v1/projects")
def project_create(payload: dict): return {"status":"OK","workspace":_project_workspace_payload(projects.create(payload.get("name","Project"),payload.get("jira_project_key",""),payload.get("github_owner",""),payload.get("github_repo",""),payload.get("workspace_id")))}
@app.get("/api/v1/projects/{workspace_id}")
def project_show(workspace_id: str): return {"status":"OK","workspace":_project_workspace_payload(projects.show(workspace_id))}
@app.post("/api/v1/projects/{workspace_id}/snapshot")
def project_snapshot(workspace_id: str): return {"status":"OK","snapshot":_project_snapshot_payload(projects.snapshot(workspace_id))}
@app.get("/api/v1/projects/{workspace_id}/delivery")
def project_delivery(workspace_id: str): return {"status":"OK","analysis":_delivery_payload(delivery.analyze(workspace_id))}
@app.get("/api/v1/projects/{workspace_id}/brief")
def project_brief(workspace_id: str): return {"status":"OK","brief":delivery.brief(delivery.analyze(workspace_id))}
@app.get("/api/v1/memory")
def memory_list(category: str | None = None, scope: str | None = None, q: str | None = None): return {"status":"OK","memories":serialize(runtime.memory.search(q) if q else runtime.memory.list(category, scope))}
@app.get("/api/v1/memory/{memory_id}")
def memory_get(memory_id: str):
	record = runtime.memory.get(memory_id)
	if record is None: return {"status":"ERROR","code":"NOT_FOUND","message":"Memory not found.","details":[]}
	return {"status":"OK","memory":serialize(record)}
@app.post("/api/v1/memory")
def memory_create(payload: dict):
	record = runtime.memory.create(payload.get("category", MemoryCategory.PREFERENCE.value), payload.get("key", ""), payload.get("value", ""), payload.get("scope", MemoryScope.DURABLE.value), payload.get("source", "EXPLICIT_USER"), payload.get("expires_at"), payload.get("tags", ()), payload.get("provenance", ""))
	return {"status":"OK","memory":serialize(record)}
@app.patch("/api/v1/memory/{memory_id}")
def memory_update(memory_id: str, payload: dict):
	old = runtime.memory.get(memory_id)
	if old is None: return {"status":"ERROR","code":"NOT_FOUND","message":"Memory not found.","details":[]}
	record = runtime.memory.create(old.category, old.key, payload.get("value", old.value), old.scope, old.source, old.expires_at, old.tags, old.provenance)
	return {"status":"OK","memory":serialize(record)}
@app.delete("/api/v1/memory/{memory_id}")
def memory_delete(memory_id: str): return {"status":"OK","deleted":runtime.memory.forget(memory_id)}
@app.get("/api/v1/tools")
def tool_list(): return {"status":"OK","tools":tools.registry.safe_list()}
@app.post("/api/v1/tools/plan")
def tool_plan(payload: dict): return {"status":"OK","plan":_tool_plan_payload(tools.plan(payload.get("tool_id", ""), payload.get("arguments", {}), payload.get("source", "API"), payload.get("correlation_id", "API")))}
@app.get("/api/v1/tools/{plan_id}")
def tool_show(plan_id: str): return {"status":"OK","plan":_tool_plan_payload(tools.show(plan_id))}
@app.post("/api/v1/tools/{plan_id}/approve")
def tool_approve(plan_id: str): return {"status":"OK","approval":_tool_approval_payload(tools.approve(plan_id))}
@app.post("/api/v1/tools/{plan_id}/execute")
def tool_execute(plan_id: str): return {"status":"OK","result":_tool_result_payload(tools.execute(plan_id))}
@app.get("/api/v1/workflows")
def workflow_list(): return {"status":"OK","workflows":[_workflow_payload(item) for item in workflows.list()]}
@app.post("/api/v1/workflows")
def workflow_create(payload: dict): return {"status":"OK","workflow":_workflow_payload(workflows.create(payload.get("title", "Workflow"), payload.get("steps", []), payload.get("source", "API"), payload.get("correlation_id", "API")))}
@app.get("/api/v1/workflows/{workflow_id}")
def workflow_show(workflow_id: str): return {"status":"OK","workflow":_workflow_payload(workflows.show(workflow_id))}
@app.post("/api/v1/workflows/{workflow_id}/run")
def workflow_run(workflow_id: str): return {"status":"OK","result":_workflow_result_payload(workflows.run(workflow_id))}
@app.post("/api/v1/workflows/{workflow_id}/resume")
def workflow_resume(workflow_id: str): return {"status":"OK","result":_workflow_result_payload(workflows.resume(workflow_id))}
@app.post("/api/v1/workflows/{workflow_id}/cancel")
def workflow_cancel(workflow_id: str): return {"status":"OK","workflow":_workflow_payload(workflows.cancel(workflow_id))}
@app.post("/api/v1/workflows/{workflow_id}/steps/{step_id}/approve")
def workflow_approve(workflow_id: str, step_id: str): return {"status":"OK","approval":_tool_approval_payload(workflows.approve_step(workflow_id, step_id))}
@app.get("/api/v1/connectors")
def connector_list(): return {"status":"OK","connectors":connectors.registry.safe_list()}
@app.get("/api/v1/connectors/{connector_id}")
def connector_show(connector_id: str):
	connector = next((item for item in connectors.registry.safe_list() if item["connector_id"] == connector_id), None)
	if connector is None: raise ValueError("CONNECTOR_UNKNOWN")
	return {"status":"OK","connector":connector}
@app.get("/api/v1/connectors/{connector_id}/capabilities")
def connector_capabilities(connector_id: str): return {"status":"OK","capabilities":connectors.registry.safe_capabilities(connector_id)}
@app.post("/api/v1/connectors/{connector_id}/read")
def connector_read(connector_id: str, payload: dict):
	from core.connectors import ConnectorRequest
	result = connectors.read(ConnectorRequest(payload.get("request_id", "CONNECTOR"), connector_id, payload.get("capability_id", ""), payload.get("arguments", {}), payload.get("correlation_id", "API")))
	return {"status":"OK" if result.status == "SUCCEEDED" else "ERROR","result":_connector_result_payload(result)}
@app.post("/api/v1/chat")
def chat(payload:dict):
	request=ConversationRequest(payload.get("conversation_id","API"),payload.get("request_id","CHAT"),_timestamp(payload.get("timestamp")),payload.get("text",""),payload.get("language","en"),payload.get("context"),"API",payload.get("explicit_user_authorization",False))
	response=conversation.handle(request)
	return {"request_id":response.request_id,"conversation_id":request.conversation_id,"status":response.status,"intent":response.intent,"execution_mode":response.execution_mode,"message":response.message,"follow_up_required":response.follow_up_required,"missing_fields":list(response.missing_fields),"warnings":list(response.warnings),"structured_result":serialize(response.structured_result)}
@app.post("/api/v1/analysis/market-context")
def market_context(payload:dict): payload["request_type"]="MARKET_CONTEXT";return service.request(payload)
@app.post("/api/v1/analysis/underlying")
def underlying(payload:dict): payload["request_type"]="UNDERLYING_ANALYSIS";return service.request(payload)
@app.post("/api/v1/analysis/full")
def full(payload:dict, request: Request):
	payload["request_type"]="FULL_ANALYSIS"; result=service.request(payload)
	if result.get("status")=="ERROR":observability.record("API","REQUEST",result["code"],request_id=request.state.correlation_id,message="POST /api/v1/analysis/full")
	return result
@app.post("/api/v1/risk/validate")
def risk(payload:dict):
	proposal = _proposal(payload)
	return service.request({"request_type":"RISK_VALIDATE","instrument":proposal.instrument,"timestamp":proposal.timestamp,"parameters":{"proposal":proposal}})
@app.post("/api/v1/paper/execute")
def paper(payload:dict):
	proposal = _proposal(payload)
	decision = service.orchestrator.handle(type("Request", (), {"request_id":"API-RISK","request_type":"RISK_VALIDATE","timestamp":proposal.timestamp,"instrument":proposal.instrument,"exchange":"NSE","token":None,"interval":"15m","data_source":"API","execution_mode":"PAPER","parameters":{"proposal":proposal},"explicit_user_authorization":False,"source":"API"})()).risk_decision
	return service.request({"request_type":"PAPER_EXECUTE","instrument":proposal.instrument,"timestamp":proposal.timestamp,"execution_mode":"PAPER","explicit_user_authorization":payload.get("explicit_user_authorization",False),"parameters":{"proposal":proposal,"risk_decision":decision,"paper_engine":paper_engine}})
@app.get("/api/v1/automation/jobs")
def jobs(): return service.automation_jobs()
@app.get("/api/v1/automation/history")
def history(): return service.automation_history()
@app.post("/api/v1/automation/tick")
def tick(payload:dict): return service.automation_tick(_timestamp(payload.get("timestamp")))
@app.get("/api/v1/portfolio")
def portfolio(): return service.request({"request_type":"PORTFOLIO_ANALYSIS","timestamp":datetime.now(timezone.utc),"parameters":{"account":paper_engine.account}})
@app.post("/api/v1/backtest")
def backtest(payload:dict):
	if len(payload.get("candles",()))>500: return {"status":"ERROR","code":"RATE_LIMITED","message":"Historical candle request exceeds the maximum item limit.","details":[]}
	candles = tuple(_historical_candle(item) for item in payload.get("candles", ()))
	if not candles: raise ValueError("At least one historical candle is required.")
	timestamps = [candle.timestamp for candle in candles]
	if timestamps != sorted(timestamps) or len(set(timestamps)) != len(timestamps): raise ValueError("Historical candles must be chronological with unique timestamps.")
	engine = HistoricalReplayEngine(BacktestConfig(warmup_candles=payload.get("warmup_candles", 200)))
	return service.request({"request_type":"BACKTEST","execution_mode":"HISTORICAL_REPLAY","timestamp":candles[-1].timestamp if candles else _timestamp(payload.get("timestamp")),"parameters":{"backtest_engine":engine,"candles":candles}})

def _timestamp(value):
	if value is None: return datetime.now(timezone.utc)
	timestamp = datetime.fromisoformat(value) if isinstance(value,str) else value
	if timestamp.tzinfo is None: raise ValueError("timestamp must be timezone-aware.")
	return timestamp
def _proposal(payload):
	required=("instrument","direction","proposed_entry","proposed_stop","proposed_target","capital_available","risk_per_trade_percent","lot_size")
	missing=[name for name in required if name not in payload]
	if missing: raise ValueError(f"Missing proposal fields: {', '.join(missing)}.")
	return TradeProposal(payload["instrument"],payload["direction"],payload["proposed_entry"],payload["proposed_stop"],payload["proposed_target"],payload["capital_available"],payload["risk_per_trade_percent"],int(payload["lot_size"]),payload.get("quantity_requested"),_timestamp(payload.get("timestamp")),"API",True)
def _historical_candle(payload):
	required=("symbol","exchange","timestamp","open","high","low","close","volume","source")
	missing=[name for name in required if name not in payload]
	if missing: raise ValueError(f"Missing candle fields: {', '.join(missing)}.")
	timestamp=_timestamp(payload["timestamp"])
	candle=OHLCV(payload["symbol"],payload["exchange"],timestamp,float(payload["open"]),float(payload["high"]),float(payload["low"]),float(payload["close"]),int(payload["volume"]),payload["source"],True)
	if candle.low>candle.high or min(candle.open,candle.high,candle.low,candle.close)<0 or candle.volume<0: raise ValueError("Invalid historical OHLCV values.")
	return candle

def create_app(config: RuntimeConfig | None = None):
	"""Return the composed FastAPI app; import-time composition remains backward compatible."""
	if config is not None and config != runtime.config:
		raise RuntimeError("The module app is already composed; construct a fresh process for alternate runtime config.")
	return app

def _tool_plan_payload(plan):
	return {"plan_id":plan.plan_id,"tool_id":plan.tool_id,"validated_arguments":dict(plan.validated_arguments),"risk_class":plan.risk_class.value,"requires_confirmation":plan.requires_confirmation,"status":plan.status.value,"created_at":plan.created_at.isoformat(),"expires_at":plan.expires_at.isoformat(),"preview":plan.preview,"source":plan.source,"correlation_id":plan.correlation_id,"argument_fingerprint":plan.argument_fingerprint}
def _tool_approval_payload(approval): return {"plan_id":approval.plan_id,"tool_id":approval.tool_id,"argument_fingerprint":approval.argument_fingerprint,"approved_at":approval.approved_at.isoformat(),"source":approval.source}
def _tool_result_payload(result): return {"plan_id":result.plan_id,"tool_id":result.tool_id,"status":result.status,"result":serialize(result.result),"warnings":list(result.warnings),"error_category":result.error_category,"started_at":result.started_at.isoformat() if result.started_at else None,"completed_at":result.completed_at.isoformat() if result.completed_at else None,"correlation_id":result.correlation_id}
def _workflow_payload(workflow): return {"workflow_id":workflow.workflow_id,"title":workflow.title,"source":workflow.source,"status":workflow.status.value,"steps":[{"step_id":step.step_id,"order":step.order,"tool_id":step.tool_id,"arguments":dict(step.arguments),"risk_class":step.risk_class.value,"requires_confirmation":step.requires_confirmation,"status":step.status.value,"tool_plan_id":step.tool_plan_id,"result_reference":step.result_reference} for step in workflow.steps],"created_at":workflow.created_at.isoformat(),"updated_at":workflow.updated_at.isoformat(),"expires_at":workflow.expires_at.isoformat(),"correlation_id":workflow.correlation_id,"version":workflow.version}
def _workflow_result_payload(result): return {"workflow_id":result.workflow_id,"status":result.status.value,"steps":[{"step_id":step.step_id,"tool_id":step.tool_id,"status":step.status.value,"result_reference":step.result_reference} for step in result.steps],"results":serialize(dict(result.results)),"warnings":list(result.warnings)}
def _connector_result_payload(result): return {"request_id":result.request_id,"connector_id":result.connector_id,"capability_id":result.capability_id,"status":result.status,"data":serialize(result.data),"warnings":list(result.warnings),"error_category":result.error_category,"started_at":result.started_at.isoformat() if result.started_at else None,"completed_at":result.completed_at.isoformat() if result.completed_at else None,"correlation_id":result.correlation_id,"source_metadata":dict(result.source_metadata)}
def _governance_payload(profile): return {'profile_id':profile.profile_id,'connector_id':profile.connector_id,'environment':profile.environment.value,'enabled':profile.enabled,'allowed_capabilities':sorted(profile.allowed_capabilities),'allowed_resources':sorted(profile.allowed_resources),'version':profile.version,'source':profile.source}
def _project_workspace_payload(item): return {'workspace_id':item.workspace_id,'name':item.name,'jira_project_key':item.jira_project_key,'github_owner':item.github_owner,'github_repo':item.github_repo,'enabled':item.enabled,'created_at':item.created_at.isoformat() if item.created_at else None,'updated_at':item.updated_at.isoformat() if item.updated_at else None,'version':item.version}
def _project_snapshot_payload(snapshot): return {'snapshot_id':snapshot.snapshot_id,'workspace_id':snapshot.workspace_id,'retrieved_at':snapshot.retrieved_at.isoformat(),'jira_available':snapshot.jira_available,'github_available':snapshot.github_available,'partial_result':snapshot.partial_result,'jira_issues':list(snapshot.jira_issues),'github_prs':list(snapshot.github_prs),'github_commits':list(snapshot.github_commits),'links':[item.__dict__ for item in snapshot.links],'unlinked_jira':list(snapshot.unlinked_jira),'unlinked_prs':list(snapshot.unlinked_prs),'warnings':list(snapshot.warnings)}
def _delivery_payload(analysis): return {'analysis_id':analysis.analysis_id,'workspace_id':analysis.workspace_id,'snapshot_id':analysis.snapshot_id,'retrieved_at':analysis.retrieved_at.isoformat(),'signals':[item.__dict__ for item in analysis.signals],'metrics':analysis.metrics,'activity':list(analysis.activity),'warnings':list(analysis.warnings),'completeness':analysis.completeness}