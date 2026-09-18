import sys
from datetime import datetime,timezone
from pathlib import Path
PROJECT_ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(PROJECT_ROOT))
from core.orchestrator import JarvisOrchestrator,JarvisRequest
from market.providers.mock import MockMarketDataProvider
t=datetime(2026,9,17,tzinfo=timezone.utc);r=JarvisOrchestrator(MockMarketDataProvider()).handle(JarvisRequest("VERIFY-1","FULL_ANALYSIS",t,"JARVIS","NSE","000001"))
print(f"JARVIS REQUEST\nRequest ID: {r.request_id}\nRequest type: {r.request_type}\nExecution mode: {r.execution_mode}\nANALYSIS\nInstrument: {r.instrument}\nMarket trend: {r.market_context.trend}\nUnderlying trend: {r.underlying_analysis.trend}\nStrategy count: {len(r.strategy_evidence)}\nConfluence bias: {r.confluence_analysis.directional_bias}\nEvidence quality: {r.confluence_analysis.evidence_quality}\nAUDIT\nStages completed: {list(r.stages_completed)}\nStages skipped: {list(r.stages_skipped)}\nErrors: {list(r.errors)}")