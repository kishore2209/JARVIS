import os,sys,tempfile
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT))
from market.persistence import SQLiteStore,TypedAuditEventRepository,TypedBacktestResultRepository,TypedPortfolioSnapshotRepository
from market.backtest import BacktestConfig,BacktestMetrics,BacktestResult
from market.paper_trading import PaperAccount
from market.portfolio import PortfolioIntelligenceEngine
def main():
 path=tempfile.mktemp(suffix=".db");t=datetime(2026,1,1,tzinfo=timezone.utc);s=SQLiteStore(path);metrics=BacktestMetrics(0,0,0,0,Decimal("0"),Decimal("0"),Decimal("0.0000"),None,None,None,None,None,Decimal("0"),None,None,Decimal("0"));back=BacktestResult("RELIANCE",t,t,Decimal("100000.1234"),Decimal("100500.1234"),(),(),metrics,BacktestConfig(1,Decimal("100000.1234")),"HISTORICAL");portfolio=PortfolioIntelligenceEngine().analyze(PaperAccount("100000.1234"),t,{});audit={"timestamp":t,"request_id":"R1","stage":"TEST","status":"COMPLETED","message":"Authorization: Bearer secret","execution_mode":"PAPER","metadata":{"access_token":"secret","nested":[{"ANGEL_ONE_PIN":"1234"}]}}
 TypedBacktestResultRepository(s).save("B1",back);TypedPortfolioSnapshotRepository(s).save("P1",portfolio);TypedAuditEventRepository(s).save("A1",audit);s.close();s=SQLiteStore(path)
 restored=TypedBacktestResultRepository(s).restore_result("B1");snap=TypedPortfolioSnapshotRepository(s).restore_analysis("P1");event=TypedAuditEventRepository(s).restore("A1");assert restored.starting_capital==Decimal("100000.1234") and restored.execution_mode=="HISTORICAL_REPLAY" and snap.total_equity==Decimal("100000.1234") and "secret" not in str(event) and "1234" not in str(event);print("[PASS] Typed Backtest Portfolio Audit Restart")
 try:TypedBacktestResultRepository(s).save("B1",back)
 except ValueError:print("[PASS] Duplicate Protection")
 else:raise AssertionError("duplicate accepted")
 s.connection.execute("INSERT INTO backtests VALUES ('BAD','{}')");s.connection.commit()
 try:TypedBacktestResultRepository(s).restore("BAD")
 except ValueError:print("[PASS] Corrupt Record Rejected")
 else:raise AssertionError("corrupt accepted")
 for repository,identifier,value in ((TypedPortfolioSnapshotRepository(s),"P1",portfolio),(TypedAuditEventRepository(s),"A1",audit)):
  try:repository.save(identifier,value)
  except ValueError:pass
  else:raise AssertionError("duplicate accepted")
 print("[PASS] Backtest Portfolio Audit Duplicate Protection")
 for table,identifier in (("backtests","BAD-DEC"),("portfolio_snapshots","BAD-LIVE"),("audit_events","BAD-AUDIT")):
  s.connection.execute(f"INSERT INTO {table} VALUES (?,?)",(identifier,'{"timestamp":"naive","execution_mode":"LIVE"}'))
 s.connection.commit()
 for repository,identifier in ((TypedBacktestResultRepository(s),"BAD-DEC"),(TypedPortfolioSnapshotRepository(s),"BAD-LIVE"),(TypedAuditEventRepository(s),"BAD-AUDIT")):
  try:repository.restore(identifier)
  except ValueError:continue
  raise AssertionError("malformed record accepted")
 print("[PASS] Strict Mode Timestamp Corrupt Handling")
 s.close();os.remove(path)
if __name__=="__main__":main()