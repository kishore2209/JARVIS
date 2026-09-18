import sys
from datetime import datetime,timezone
from pathlib import Path
PROJECT_ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(PROJECT_ROOT))
from core.orchestrator import JarvisOrchestrator,JarvisRequest
from market.backtest import BacktestConfig,HistoricalReplayEngine
from market.paper_trading import PaperAccount,PaperTradingEngine
from market.providers.mock import MockMarketDataProvider
from market.risk import RiskConfig,RiskFirewall,TradeProposal
def main():
 t=datetime(2026,1,2,13,14,tzinfo=timezone.utc);o=JarvisOrchestrator(MockMarketDataProvider());base=lambda i,k,**p:JarvisRequest(i,k,t,"JARVIS","NSE","000001",parameters=p or None)
 context=o.handle(base("REQ-1","MARKET_CONTEXT"));underlying=o.handle(base("REQ-2","UNDERLYING_ANALYSIS"));full=o.handle(base("REQ-3","FULL_ANALYSIS"));assert context.market_context and underlying.underlying_analysis and full.confluence_analysis and len(full.strategy_evidence)==7 and "FNO_INTELLIGENCE" in full.stages_skipped and full.is_fresh;print("[PASS] Analysis Workflows")
 proposal=TradeProposal("JARVIS","LONG","100","98","104","100000","1",25,125,t,"MOCK",True);config=RiskConfig(require_fresh_data=False);approved=RiskFirewall(config,clock=lambda:t).evaluate(proposal);risk=o.handle(base("REQ-4","RISK_VALIDATE",proposal=proposal,risk_config=config));assert risk.risk_decision.approved;print("[PASS] Risk Validate Approved")
 rejected=TradeProposal("JARVIS","LONG","100","101","104","100000","1",25,125,t,"MOCK",True);assert not o.handle(base("REQ-5","RISK_VALIDATE",proposal=rejected)).risk_decision.approved;print("[PASS] Risk Validate Rejected")
 paper=PaperTradingEngine(PaperAccount("100000"));no_auth=o.handle(base("REQ-6","PAPER_EXECUTE",proposal=proposal,risk_decision=approved,paper_engine=paper));assert no_auth.status=="AUTHORIZATION_REQUIRED";yes=o.handle(JarvisRequest("REQ-7","PAPER_EXECUTE",t,"JARVIS","NSE","000001",execution_mode="PAPER",parameters={"proposal":proposal,"risk_decision":approved,"paper_engine":paper},explicit_user_authorization=True));assert yes.paper_execution_result.status=="PENDING";print("[PASS] Paper Authorization")
 assert o.handle(base("REQ-8","PAPER_EXECUTE",proposal=proposal,risk_decision=None,paper_engine=paper)).status=="AUTHORIZATION_REQUIRED";live=o.handle(JarvisRequest("REQ-9","FULL_ANALYSIS",t,"JARVIS",execution_mode="LIVE"));assert live.status=="LIVE_EXECUTION_UNSUPPORTED";print("[PASS] Live And Rejected Paper")
 portfolio=o.handle(base("REQ-10","PORTFOLIO_ANALYSIS",account=PaperAccount("100000")));candles=MockMarketDataProvider().get_candles("JARVIS","NSE","000001",240);backtest=o.handle(base("REQ-11","BACKTEST",backtest_engine=HistoricalReplayEngine(BacktestConfig(warmup_candles=200)),candles=candles));assert portfolio.portfolio_analysis and backtest.backtest_result;print("[PASS] Portfolio And Backtest")
 bad=o.handle(JarvisRequest("REQ-12","FULL_ANALYSIS",t,"BAD","NSE","000001"));assert "ValueError" in bad.status;assert {x.status for x in full.audit_events}>={"STARTED","COMPLETED"};assert all("000001" not in x.message for x in full.audit_events);assert full==o.handle(base("REQ-3","FULL_ANALYSIS"));print("[PASS] Failure Audit Determinism");return 0
if __name__=="__main__":sys.exit(main())