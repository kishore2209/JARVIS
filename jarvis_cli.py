import argparse, json
from datetime import datetime, timezone
from core.interface_service import JarvisInterfaceService
from core.automation import AutomationController
from core.observability import Observability
from core.conversation import ConversationRequest,JarvisConversationService
from core.memory import JarvisMemoryService, MemoryRepository
from core.tools import build_tool_service
from core.workflows import WorkflowService
from core.orchestrator import JarvisOrchestrator
from market.providers.mock import MockMarketDataProvider

def main():
 parser=argparse.ArgumentParser();parser.add_argument("command",choices=("status","health","readiness","metrics","diagnostics","chat","market-context","underlying-analysis","full-analysis","portfolio","automation-status","automation-history","automation-tick","risk-validate","paper-execute","backtest","live","memory-list","memory-set","memory-forget","memory-search","tool-list","tool-plan","tool-show","tool-approve","tool-execute","workflow-list","workflow-create","workflow-show","workflow-run","workflow-step-approve","workflow-resume","workflow-cancel"));parser.add_argument("text",nargs="?");parser.add_argument("--symbol",default="JARVIS");parser.add_argument("--exchange",default="NSE");parser.add_argument("--token",default="000001");parser.add_argument("--interval",default="15m");parser.add_argument("--input",default="{}");parser.add_argument("--authorize",action="store_true");args=parser.parse_args()
 observability=Observability();orchestrator=JarvisOrchestrator(MockMarketDataProvider(),observability=observability);service=JarvisInterfaceService(orchestrator,AutomationController(orchestrator));memory=JarvisMemoryService(MemoryRepository());tool_runtime=type("RuntimeView",(),{"observability":observability,"memory":memory,"paper_engine":type("Paper",(),{"account":None})(),"automation":service.automation})();tools=build_tool_service(tool_runtime,observability);workflows=WorkflowService(tools,observability=observability);payload=json.loads(args.input);payload.update({"instrument":args.symbol,"exchange":args.exchange,"token":args.token,"interval":args.interval,"timestamp":datetime.now(timezone.utc),"explicit_user_authorization":args.authorize})
 if args.command=="status": result=service.status()
 elif args.command=="chat": result=JarvisConversationService(orchestrator,observability=observability).handle(ConversationRequest("CLI","CLI",payload["timestamp"],args.text or "",source="CLI")).__dict__
 elif args.command=="health": result=observability.health()
 elif args.command=="readiness": result=observability.readiness()
 elif args.command=="metrics": result=observability.snapshot()
 elif args.command=="diagnostics": result={"health":observability.health(),"metrics":observability.snapshot(),"live_execution_supported":False}
 elif args.command=="automation-status": result=service.automation_jobs()
 elif args.command=="automation-history": result=service.automation_history()
 elif args.command=="automation-tick": result=service.automation_tick(payload["timestamp"])
 elif args.command=="memory-list": result={"status":"OK","memories":[item.__dict__ for item in memory.list()]}
 elif args.command=="memory-search": result={"status":"OK","memories":[item.__dict__ for item in memory.search(args.text or "")]}
 elif args.command=="memory-set": result=memory.create(payload.get("category","PREFERENCE"),payload.get("key",args.text or ""),payload.get("value","" )).__dict__
 elif args.command=="memory-forget": result={"status":"OK","deleted":memory.forget(args.text or "")}
 elif args.command=="tool-list": result={"status":"OK","tools":tools.registry.safe_list()}
 elif args.command=="tool-plan": result={"status":"OK","plan":tools.plan(args.text or "", payload.get("arguments", {}), "CLI").__dict__}
 elif args.command=="tool-show": result={"status":"OK","plan":tools.show(args.text or "").__dict__}
 elif args.command=="tool-approve": result={"status":"OK","approval":tools.approve(args.text or "").__dict__}
 elif args.command=="tool-execute": result={"status":"OK","result":tools.execute(args.text or "").__dict__}
 elif args.command=="workflow-list": result={"status":"OK","workflows":[item.__dict__ for item in workflows.list()]}
 elif args.command=="workflow-create": result={"status":"OK","workflow":workflows.create(args.text or "Workflow", payload.get("steps", []), "CLI").__dict__}
 elif args.command=="workflow-show": result={"status":"OK","workflow":workflows.show(args.text or "").__dict__}
 elif args.command=="workflow-run": result={"status":"OK","result":workflows.run(args.text or "").__dict__}
 elif args.command=="workflow-step-approve":
  workflow_id, step_id = (args.text or ":").split(":", 1); result={"status":"OK","approval":workflows.approve_step(workflow_id, step_id).__dict__}
 elif args.command=="workflow-resume": result={"status":"OK","result":workflows.resume(args.text or "").__dict__}
 elif args.command=="workflow-cancel": result={"status":"OK","workflow":workflows.cancel(args.text or "").__dict__}
 else:
  payload["request_type"]={"market-context":"MARKET_CONTEXT","underlying-analysis":"UNDERLYING_ANALYSIS","full-analysis":"FULL_ANALYSIS","portfolio":"PORTFOLIO_ANALYSIS","risk-validate":"RISK_VALIDATE","paper-execute":"PAPER_EXECUTE","backtest":"BACKTEST","live":"FULL_ANALYSIS"}[args.command];payload["execution_mode"]="LIVE" if args.command=="live" else "PAPER" if args.command=="paper-execute" else "ANALYSIS_ONLY";result=service.request(payload)
 print(json.dumps(result,default=str))
if __name__=="__main__":main()