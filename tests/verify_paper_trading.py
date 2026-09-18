# Run from the project root: python tests/verify_paper_trading.py
"""Offline deterministic PAPER-only trade lifecycle verification."""
import sys
from datetime import datetime, timezone
from pathlib import Path
PROJECT_ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(PROJECT_ROOT))
from market.ohlcv import OHLCV
from market.paper_trading import PaperAccount,PaperTradingEngine
from market.risk import RiskFirewall,TradeProposal
t=datetime(2026,9,17,10,tzinfo=timezone.utc);p=TradeProposal("RELIANCE","LONG","100","98","104","100000","1",25,125,t,"MOCK",True);d=RiskFirewall(clock=lambda:t).evaluate(p);a=PaperAccount("100000");e=PaperTradingEngine(a);o=e.create_order(p,d);f,pos=e.fill_order(o.order_id,"100",t,"MOCK");e.mark_to_market(pos.position_id,"102",t);u=pos.unrealized_pnl;closed,j=e.evaluate_completed_candle(pos.position_id,OHLCV("RELIANCE","NSE",t,102,105,101,104,1000,"MOCK",True))
print(f"Account starting cash: {a.starting_cash}\nOrder ID: {o.order_id}\nInstrument: {o.instrument}\nDirection: {o.direction}\nQuantity: {o.quantity}\nEntry: {p.proposed_entry}\nStop: {p.proposed_stop}\nTarget: {p.proposed_target}\nRisk approval: {d.approved}\nVirtual fill price: {f.fill_price}\nPosition status: {closed.status}\nUnrealized P&L before exit: {u}\nExit price: {closed.exit_price}\nExit reason: {closed.exit_reason}\nRealized P&L: {closed.realized_pnl}\nAccount available cash: {a.available_cash}\nAccount realized P&L: {a.realized_pnl}\nJournal entry: {j.position_id}\nExecution mode: {j.execution_mode}")