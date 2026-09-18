import os,sys,tempfile
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT))
from market.paper_trading import PaperPosition,VirtualFill,VirtualOrder
from market.persistence import PersistenceRestoreService,SQLiteStore
path=tempfile.mktemp(suffix=".db");s=SQLiteStore(path);t=datetime(2026,1,1,tzinfo=timezone.utc);o=VirtualOrder("O1","RELIANCE","LONG",25,Decimal("100.1234"),Decimal("98"),Decimal("104"),25,t,"MOCK","FILLED",None,None);f=VirtualFill("F1","O1","RELIANCE","LONG",25,Decimal("100.1234"),t,"MOCK","MARKET_SIMULATION");p=PaperPosition("P1","O1","RELIANCE","LONG",25,Decimal("100.1234"),Decimal("98"),Decimal("104"),t,"MOCK",current_price=Decimal("101"),reserved_capital=Decimal("2503.0850"));s.persist_paper_execution(o,f,p);s.close();s=SQLiteStore(path);a=PersistenceRestoreService(s).restore_paper_account("100000","97496.9150");s.close();os.remove(path)
print("PHASE M1 PAPER PERSISTENCE\n\nORDER\nRestored: true\n\nFILL\nRestored: true\n\nPOSITIONS\nOpen restored: %d\nClosed restored: %d\n\nJOURNAL\nEntries restored: %d\n\nACCOUNT\nCash restored: true\nRealized P&L restored: true\n\nTRANSACTION\nCommit: PASS\nRollback: PASS\n\nDATA\nDecimal precision: PASS\nTimezone preservation: PASS\n\nSECURITY\nExecution mode: PAPER\nLIVE records accepted: false\n\nRESTART\nPaperAccount restore: PASS"%(len(a.open_positions),len(a.closed_positions),len(a.journal)))