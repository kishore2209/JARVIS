# Run from the project root: python tests/test_paper_trading.py
"""Deterministic offline tests for the PAPER-only execution engine."""
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from market.ohlcv import OHLCV
from market.paper_trading import PaperAccount, PaperTradingEngine
from market.risk import RiskFirewall, TradeProposal

def main():
    timestamp=datetime(2026,9,17,10,tzinfo=timezone.utc); results=[]
    def setup(direction="LONG", cash="100000"):
        proposal=TradeProposal("RELIANCE",direction,"100","98" if direction=="LONG" else "102","104" if direction=="LONG" else "96","100000","1",25,125,timestamp,"MOCK",True)
        decision=RiskFirewall(clock=lambda:timestamp).evaluate(proposal); engine=PaperTradingEngine(PaperAccount(cash)); return engine,proposal,decision
    def candle(high,low,close=100): return OHLCV("RELIANCE","NSE",timestamp,100,high,low,close,1000,"MOCK",True)
    def run(name,test):
        try:test(); results.append(True);print(f"[PASS] {name}")
        except Exception as e:results.append(False);print(f"[FAIL] {name}");print(f"Reason: {e}")
    def test_creation_rejection_fill():
        engine,p,d=setup(); order=engine.create_order(p,d); fill,pos=engine.fill_order(order.order_id,"100",timestamp,"MOCK")
        if order.quantity!=d.approved_quantity or fill.execution_mode!="PAPER" or pos.status!="OPEN":raise AssertionError("approved order/fill failed")
        try: engine.fill_order(order.order_id,"100",timestamp,"MOCK")
        except ValueError: pass
        else: raise AssertionError("duplicate fill accepted")
        try: engine.create_order(p, type("D",(),{"approved":False})())
        except ValueError:return
        raise AssertionError("rejected decision accepted")
    def test_cash_pnl_long_short():
        engine,p,d=setup(); o=engine.create_order(p,d);_,pos=engine.fill_order(o.order_id,"100",timestamp,"MOCK"); engine.mark_to_market(pos.position_id,"102",timestamp)
        if pos.unrealized_pnl!=250:raise AssertionError("long P&L incorrect")
        closed,j=engine.close_position(pos.position_id,"104",timestamp)
        if closed.realized_pnl!=500 or engine.account.available_cash!=100500 or j.execution_mode!="PAPER":raise AssertionError("long close/cash/journal incorrect")
        engine,p,d=setup("SHORT");o=engine.create_order(p,d);_,pos=engine.fill_order(o.order_id,"100",timestamp,"MOCK");engine.mark_to_market(pos.position_id,"98",timestamp)
        if pos.unrealized_pnl!=250:raise AssertionError("short P&L incorrect")
    def test_exits_state_cash():
        engine,p,d=setup();o=engine.create_order(p,d);_,pos=engine.fill_order(o.order_id,"100",timestamp,"MOCK");closed,_=engine.evaluate_completed_candle(pos.position_id,candle(105,97))
        if closed.exit_reason!="STOP" or closed.exit_price!=98:raise AssertionError("STOP_FIRST policy failed")
        engine,p,d=setup();o=engine.create_order(p,d);_,pos=engine.fill_order(o.order_id,"100",timestamp,"MOCK");closed,_=engine.evaluate_completed_candle(pos.position_id,candle(104,99,104))
        if closed.exit_reason!="TARGET" or closed.exit_price!=104:raise AssertionError("long target failed")
        engine,p,d=setup("SHORT");o=engine.create_order(p,d);_,pos=engine.fill_order(o.order_id,"100",timestamp,"MOCK");closed,_=engine.evaluate_completed_candle(pos.position_id,candle(103,95))
        if closed.exit_reason!="STOP":raise AssertionError("short stop failed")
        engine,p,d=setup("SHORT");o=engine.create_order(p,d);_,pos=engine.fill_order(o.order_id,"100",timestamp,"MOCK");closed,_=engine.evaluate_completed_candle(pos.position_id,candle(101,96))
        if closed.exit_reason!="TARGET" or closed.exit_price!=96:raise AssertionError("short target failed")
        try:engine.close_position(pos.position_id,"96",timestamp)
        except ValueError:pass
        else:raise AssertionError("closed position accepted")
    def test_manual_cash_freshness():
        engine,p,d=setup(cash="100");o=engine.create_order(p,d)
        try:engine.fill_order(o.order_id,"100",timestamp,"MOCK")
        except ValueError:pass
        else:raise AssertionError("insufficient cash accepted")
        engine,p,d=setup();o=engine.create_order(p,d)
        try:engine.fill_order(o.order_id,"100",timestamp,"MOCK",False)
        except ValueError:return
        raise AssertionError("stale fill accepted")
    print("="*40);print("J.A.R.V.I.S PAPER TRADING TEST");print("="*40)
    run("Order Approval Fill Idempotency",test_creation_rejection_fill);run("Cash PNL Long Short Journal",test_cash_pnl_long_short);run("Stops Targets State",test_exits_state_cash);run("Cash And Freshness",test_manual_cash_freshness)
    passed=sum(results);print("="*40);print("TEST SUMMARY");print("="*40);print(f"Total Tests : {len(results)}");print(f"Passed      : {passed}");print(f"Failed      : {len(results)-passed}");print("Status      : ALL TESTS PASSED" if passed==len(results) else "Status      : TESTS FAILED");print("="*40);return len(results)-passed
if __name__=="__main__":sys.exit(main())