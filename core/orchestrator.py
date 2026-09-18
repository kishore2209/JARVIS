from dataclasses import dataclass
from datetime import datetime, timezone
from time import perf_counter

from market.confluence import ConfluenceEngine
from market.context import MarketContextEngine
from market.paper_trading import PaperTradingEngine
from market.portfolio import PortfolioIntelligenceEngine
from market.risk import RiskFirewall
from market.strategies.engine import MultiStrategyEngine
from market.underlying_analysis import UnderlyingAnalysisEngine

@dataclass(frozen=True)
class JarvisRequest:
    request_id:str; request_type:str; timestamp:datetime; instrument:str|None=None; exchange:str="NSE"; token:str|None=None; interval:str="15m"; data_source:str="PROVIDER"; execution_mode:str="ANALYSIS_ONLY"; parameters:dict|None=None; explicit_user_authorization:bool=False; source:str="USER"
@dataclass(frozen=True)
class AuditEvent:
    timestamp:datetime; request_id:str; stage:str; status:str; message:str; execution_mode:str
@dataclass(frozen=True)
class JarvisResult:
    request_id:str; request_type:str; status:str; started_at:datetime; completed_at:datetime; instrument:str|None; execution_mode:str; market_context:object=None; underlying_analysis:object=None; fno_analysis:object=None; strategy_evidence:object=None; confluence_analysis:object=None; risk_decision:object=None; paper_execution_result:object=None; portfolio_analysis:object=None; backtest_result:object=None; warnings:tuple=(); errors:tuple=(); stages_completed:tuple=(); stages_skipped:tuple=(); data_sources:tuple=(); is_fresh:bool|None=None; data_completeness:str="NOT_AVAILABLE"; audit_events:tuple=()

class JarvisOrchestrator:
    def __init__(self,provider=None,allow_paper_execution=True,observability=None): self.provider=provider;self.allow_paper_execution=allow_paper_execution;self.observability=observability
    def handle(self,request):
        started=request.timestamp; timer=perf_counter(); audits=[]; done=[]; skipped=[]; warnings=[]; errors=[]; values={}
        def audit(stage,status,msg):audits.append(AuditEvent(request.timestamp,request.request_id,stage,status,msg,request.execution_mode))
        if request.execution_mode=="LIVE": return JarvisResult(request.request_id,request.request_type,"LIVE_EXECUTION_UNSUPPORTED",started,started,request.instrument,"LIVE",errors=("LIVE execution is unsupported.",),audit_events=(AuditEvent(started,request.request_id,"REQUEST","FAILED","LIVE execution is unsupported.","LIVE"),))
        try:
            if request.request_type in {"MARKET_CONTEXT","UNDERLYING_ANALYSIS","FULL_ANALYSIS"}:
                audit("RESOLVE_DATA","STARTED","Resolving provider candles")
                if self.provider is None: raise ValueError("A market-data provider is required.")
                candles=self.provider.get_candles(request.instrument,request.exchange,request.token,240); done.append("RESOLVE_DATA");audit("RESOLVE_DATA","COMPLETED","Normalized candles resolved")
                if request.request_type in {"MARKET_CONTEXT","FULL_ANALYSIS"}: values["market_context"]=MarketContextEngine().analyze(candles);done.append("MARKET_CONTEXT");audit("MARKET_CONTEXT","COMPLETED","Context computed")
                if request.request_type in {"UNDERLYING_ANALYSIS","FULL_ANALYSIS"}: values["underlying_analysis"]=UnderlyingAnalysisEngine().analyze(candles,values.get("market_context"));done.append("UNDERLYING_ANALYSIS");audit("UNDERLYING_ANALYSIS","COMPLETED","Underlying analysis computed")
                if request.request_type=="FULL_ANALYSIS":
                    values["strategy_evidence"]=MultiStrategyEngine().analyze(candles,values["underlying_analysis"],values.get("market_context"));done.append("MULTI_STRATEGY");audit("MULTI_STRATEGY","COMPLETED","Evidence computed")
                    values["confluence_analysis"]=ConfluenceEngine().analyze(values["underlying_analysis"],values["strategy_evidence"],values.get("market_context"),request.parameters.get("fno_analysis") if request.parameters else None);done.append("CONFLUENCE");audit("CONFLUENCE","COMPLETED","Evidence aggregated")
                    skipped.append("FNO_INTELLIGENCE");warnings.append("FNO_DATA = NOT_AVAILABLE")
            elif request.request_type=="RISK_VALIDATE":
                proposal=request.parameters.get("proposal"); values["risk_decision"]=RiskFirewall(request.parameters.get("risk_config")).evaluate(proposal,request.parameters.get("portfolio_context"));done.append("RISK_VALIDATION");audit("RISK_VALIDATION","COMPLETED","Risk validated")
            elif request.request_type=="PAPER_EXECUTE":
                proposal=request.parameters.get("proposal"); decision=request.parameters.get("risk_decision"); paper=request.parameters.get("paper_engine")
                if not request.explicit_user_authorization: return self._result(request,started,values,warnings,("AUTHORIZATION_REQUIRED",),done,skipped+["PAPER_EXECUTION"],audits+[AuditEvent(request.timestamp,request.request_id,"PAPER_EXECUTION","AUTHORIZATION_REQUIRED","Explicit authorization required.",request.execution_mode)])
                if not decision or not decision.approved: return self._result(request,started,values,warnings,("RISK_REJECTED",),done,skipped+["PAPER_EXECUTION"],audits)
                values["paper_execution_result"]=paper.create_order(proposal,decision);done.append("PAPER_EXECUTION");audit("PAPER_EXECUTION","COMPLETED","Paper order created")
            elif request.request_type=="PORTFOLIO_ANALYSIS": values["portfolio_analysis"]=PortfolioIntelligenceEngine().analyze(request.parameters["account"],request.timestamp,request.parameters.get("sector_map"));done.append("PORTFOLIO_ANALYSIS")
            elif request.request_type=="BACKTEST": values["backtest_result"]=request.parameters["backtest_engine"].run(request.parameters["candles"]);done.append("BACKTEST")
            else: raise ValueError("Unsupported request type.")
        except Exception as error: errors.append(f"{type(error).__name__}: {error}");audit("PIPELINE","FAILED",type(error).__name__)
        result=self._result(request,started,values,warnings,errors,done,skipped,audits)
        if self.observability:
            self.observability.record("ORCHESTRATOR","REQUEST",result.status,request_id=request.request_id,instrument=request.instrument,execution_mode=request.execution_mode,duration_ms=int((perf_counter()-timer)*1000),message=request.request_type)
            if result.status!="COMPLETED":self.observability.counters["requests_failed"]=self.observability.counters.get("requests_failed",0)+1
            if result.risk_decision:self.observability.counters["risk_approved_total" if result.risk_decision.approved else "risk_rejected_total"]=self.observability.counters.get("risk_approved_total" if result.risk_decision.approved else "risk_rejected_total",0)+1
            if result.paper_execution_result:self.observability.counters["paper_orders_total"]=self.observability.counters.get("paper_orders_total",0)+1
            if result.backtest_result:self.observability.counters["backtests_total"]=self.observability.counters.get("backtests_total",0)+1
        return result
    def _result(self,r,s,v,w,e,d,k,a):
        fresh=getattr(v.get("underlying_analysis") or v.get("market_context"),"is_fresh",None); source=getattr(v.get("underlying_analysis") or v.get("market_context"),"source",None)
        return JarvisResult(r.request_id,r.request_type,"COMPLETED" if not e else e[0],s,r.timestamp,r.instrument,r.execution_mode,warnings=tuple(w),errors=tuple(e),stages_completed=tuple(d),stages_skipped=tuple(k),data_sources=(source,) if source else (),is_fresh=fresh,data_completeness="COMPLETE" if not e else "PARTIAL",audit_events=tuple(a),**v)