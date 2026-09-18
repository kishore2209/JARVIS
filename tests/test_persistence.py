import os,sys,tempfile
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT))
from market.persistence import PersistenceRestoreService,SCHEMA_VERSION,SQLiteStore
from market.paper_trading import PaperPosition,TradeJournalEntry,VirtualFill,VirtualOrder
def main():
 path=tempfile.mktemp(suffix=".db");s=SQLiteStore(path);t=datetime(2026,1,1,tzinfo=timezone.utc);s.initialize();assert s.version()==SCHEMA_VERSION;print("[PASS] Schema Version Idempotency")
 order=VirtualOrder("O1","RELIANCE","LONG",25,Decimal("100.1234"),Decimal("98"),Decimal("104"),25,t,"MOCK","FILLED",None,None);fill=VirtualFill("F1","O1","RELIANCE","LONG",25,Decimal("100.1234"),t,"MOCK","MARKET_SIMULATION");open_position=PaperPosition("P1","O1","RELIANCE","LONG",25,Decimal("100.1234"),Decimal("98"),Decimal("104"),t,"MOCK",current_price=Decimal("101.1234"),unrealized_pnl=Decimal("25"),reserved_capital=Decimal("2503.0850"));closed_position=PaperPosition("P2","O2","INFY","SHORT",25,Decimal("100"),Decimal("102"),Decimal("96"),t,"MOCK","CLOSED",Decimal("96"),Decimal("0"),Decimal("100"),t,Decimal("96"),"TARGET",Decimal("2500"));journal=TradeJournalEntry("O2","P2","INFY","SHORT",25,Decimal("100"),Decimal("96"),Decimal("102"),Decimal("96"),Decimal("100"),t,t,"TARGET",None,None,"MOCK")
 s.persist_paper_execution(order,fill,open_position);s.save("positions","P2",closed_position);s.save("journal","P2",journal);assert s.get("orders","O1")["requested_entry"]=="100.1234" and s.get("fills","F1")["execution_mode"]=="PAPER";print("[PASS] Order Fill Position Journal Round Trip")
 try:s.save("orders","O1",order);s.save("fills","F1",fill)
 except ValueError:print("[PASS] Duplicate Order Fill Protection")
 else:raise AssertionError("duplicate accepted")
 open_position.current_price=Decimal("102.1234");open_position.unrealized_pnl=Decimal("50");s.update("positions","P1",open_position);s.close();s=SQLiteStore(path);account=PersistenceRestoreService(s).restore_paper_account("100000","94996.9150","100")
 assert len(account.order_history)==1 and len(account.fill_history)==1 and len(account.open_positions)==1 and len(account.closed_positions)==1 and len(account.journal)==1 and account.open_positions["P1"].current_price==Decimal("102.1234") and account.closed_positions["P2"].exit_reason=="TARGET";print("[PASS] Complete PaperAccount Restart Hydration")
 rollback=tempfile.mktemp(suffix=".db");r=SQLiteStore(rollback)
 try:r.persist_paper_execution(order,fill,open_position,journal,True)
 except RuntimeError:pass
 assert not r.read_all("orders") and not r.read_all("fills") and not r.read_all("positions") and not r.read_all("journal");print("[PASS] Grouped Transaction Rollback")
 r.close();os.remove(rollback)
 try:s.connection.execute("INSERT INTO orders VALUES ('BAD','{')");s.connection.commit();s.read_all("orders")
 except ValueError:print("[PASS] Malformed Record Rejected")
 s.close();os.remove(path);return 0
if __name__=="__main__":sys.exit(main())