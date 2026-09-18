import subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT))
from core.conversation import ConversationRequest,JarvisConversationService
from core.conversation import DeterministicIntentAdapter
from core.observability import Observability
from core.orchestrator import JarvisOrchestrator
from market.providers.mock import MockMarketDataProvider
def main():
 t=datetime(2026,1,2,13,14,tzinfo=timezone.utc);obs=Observability();service=JarvisConversationService(JarvisOrchestrator(MockMarketDataProvider()),observability=obs)
 full=service.handle(ConversationRequest("C","R1",t,"Analyse JARVIS"));assert full.intent=="FULL_ANALYSIS" and full.structured_result and "trend" in full.message;print("[PASS] English Analysis Composition")
 telugu=service.handle(ConversationRequest("C","R2",t,"నా portfolio చూపించు",language="te"));mixed=service.handle(ConversationRequest("C","R3",t,"JARVIS analysis cheyyi",language="te"));assert telugu.intent=="PORTFOLIO_ANALYSIS" and telugu.follow_up_required and mixed.intent=="FULL_ANALYSIS";print("[PASS] Telugu Mixed Followup")
 live=service.handle(ConversationRequest("C","R4",t,"Buy RELIANCE live"));assert live.status=="LIVE_EXECUTION_UNSUPPORTED" and not live.structured_result;print("[PASS] Live Paper Safety")
 adapter=DeterministicIntentAdapter();expected={"market context JARVIS":"MARKET_CONTEXT","underlying JARVIS":"UNDERLYING_ANALYSIS","fno analysis JARVIS":"FNO_ANALYSIS","validate trade risk":"RISK_VALIDATE","paper trade JARVIS":"PAPER_EXECUTE","Run backtest":"BACKTEST","Show automation status":"AUTOMATION_STATUS","Help":"HELP"};assert all(adapter.interpret(ConversationRequest("C","X",t,text))[0]==intent for text,intent in expected.items());assert service.handle(ConversationRequest("C","R5",t,"Analyse")).missing_fields==("instrument",);print("[PASS] Intent Followup Coverage")
 from fastapi.testclient import TestClient
 from api import app
 chat=TestClient(app).post("/api/v1/chat",json={"conversation_id":"API-C","request_id":"API-R","text":"Analyse JARVIS","timestamp":t.isoformat()}).json();assert chat["intent"]=="FULL_ANALYSIS" and chat["structured_result"]["request_id"]=="API-R" and not chat["follow_up_required"];print("[PASS] Chat API Structured Once")
 assert obs.events[0].request_id=="R1" and subprocess.run([sys.executable,"-m","jarvis_cli","chat","Analyse JARVIS"],cwd=ROOT,capture_output=True,text=True).returncode==0;print("[PASS] Telemetry CLI")
 return 0
if __name__=="__main__":sys.exit(main())