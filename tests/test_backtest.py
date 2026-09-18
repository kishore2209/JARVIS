# Run from the project root: python tests/test_backtest.py
"""Deterministic offline tests for historical PAPER replay."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
PROJECT_ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(PROJECT_ROOT))
from market.backtest import BacktestConfig, HistoricalReplayEngine, ReplayClock
from market.ohlcv import OHLCV
from market.risk import TradeProposal

def main():
    start=datetime(2025,1,1,9,15,tzinfo=timezone.utc); results=[]
    def candles(mode="target", count=203):
        result=[]
        for i in range(count):
            close=100+i*.1; high=close+.5; low=close-.5
            if i==200: close,high,low=101,101.5,100.5
            if i==201 and mode=="target": close,high,low=104,105,100
            if i==201 and mode=="stop": close,high,low=98,105,97
            result.append(OHLCV("RELIANCE","NSE",start+timedelta(minutes=i),close,high,low,close,1000,"HISTORICAL_MOCK",True))
        return result
    def callback(history,analysis,confluence):
        if len(history)==200:return TradeProposal("RELIANCE","LONG","101","99","104","100000","1",25,100,history[-1].timestamp,"REPLAY_ONLY",True,confluence)
    def short_callback(history,analysis,confluence):
        if len(history)==200:return TradeProposal("RELIANCE","SHORT","101","103","98","100000","1",25,100,history[-1].timestamp,"REPLAY_ONLY",True,confluence)
    def rejected_callback(history,analysis,confluence):
        if len(history)==200:return TradeProposal("RELIANCE","LONG","101","99","102","100000","1",25,100,history[-1].timestamp,"REPLAY_ONLY",True,confluence)
    def run(name,test):
        try:test();results.append(True);print(f"[PASS] {name}")
        except Exception as e:results.append(False);print(f"[FAIL] {name}");print(f"Reason: {e}")
    def test_clock_warmup_lookahead():
        data=candles();clock=ReplayClock(tuple(data)).advance()
        if len(clock.available_candles)!=1 or clock.timestamp!=data[0].timestamp:raise AssertionError("clock exposes future data")
        try:HistoricalReplayEngine(BacktestConfig(warmup_candles=204)).run(data)
        except ValueError:return
        raise AssertionError("warm-up failure missing")
    def test_target_stop_pipeline():
        target=HistoricalReplayEngine(BacktestConfig(warmup_candles=200),proposal_callback=callback).run(candles())
        if target.total_trades if False else False:pass
        if target.metrics.total_trades!=1 or target.trades[0].exit_reason!="TARGET" or target.trades[0].entry_price!=101 or target.trades[0].realized_pnl!=300:raise AssertionError("next-candle target pipeline failed")
        stop=HistoricalReplayEngine(BacktestConfig(warmup_candles=200),proposal_callback=callback).run(candles("stop"))
        if stop.trades[0].exit_reason!="STOP" or stop.trades[0].realized_pnl!=-200:raise AssertionError("STOP_FIRST failed")
    def test_metrics_quality_determinism():
        engine=HistoricalReplayEngine(BacktestConfig(warmup_candles=200),proposal_callback=callback); first=engine.run(candles());second=engine.run(candles())
        if first!=second or first.metrics.win_rate!=1 or first.metrics.profit_factor is not None or first.execution_mode!="HISTORICAL_REPLAY" or first.data_status!="HISTORICAL":raise AssertionError("metrics or markers failed")
        empty=HistoricalReplayEngine(BacktestConfig(warmup_candles=200)).run(candles())
        if empty.metrics.total_trades!=0 or empty.metrics.win_rate is not None:raise AssertionError("zero trade handling failed")
    def test_short_rejected_equity():
        data=candles(); data[201]=OHLCV("RELIANCE","NSE",data[201].timestamp,100,102,97,98,1000,"HISTORICAL_MOCK",True)
        short=HistoricalReplayEngine(BacktestConfig(warmup_candles=200),proposal_callback=short_callback).run(data)
        if short.trades[0].direction!="SHORT" or short.trades[0].exit_reason!="TARGET" or short.metrics.net_pnl!=300:raise AssertionError("short replay failed")
        rejected=HistoricalReplayEngine(BacktestConfig(warmup_candles=200),proposal_callback=rejected_callback).run(candles())
        if rejected.metrics.total_trades!=0:raise AssertionError("rejected replay proposal executed")
        stopped=HistoricalReplayEngine(BacktestConfig(warmup_candles=200),proposal_callback=callback).run(candles("stop"))
        if stopped.metrics.maximum_drawdown!=200 or not stopped.equity_curve:raise AssertionError("equity drawdown failed")
    print("="*40);print("J.A.R.V.I.S BACKTEST TEST");print("="*40);run("Replay Clock Warmup Lookahead",test_clock_warmup_lookahead);run("Target Stop Pipeline",test_target_stop_pipeline);run("Metrics Quality Determinism",test_metrics_quality_determinism);run("Short Rejected Equity",test_short_rejected_equity)
    passed=sum(results);print("="*40);print("TEST SUMMARY");print("="*40);print(f"Total Tests : {len(results)}");print(f"Passed      : {passed}");print(f"Failed      : {len(results)-passed}");print("Status      : ALL TESTS PASSED" if passed==len(results) else "Status      : TESTS FAILED");print("="*40);return len(results)-passed
if __name__=="__main__":sys.exit(main())