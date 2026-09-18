# Run from the project root: python tests/verify_backtest.py
"""Offline deterministic historical PAPER replay verification."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
PROJECT_ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(PROJECT_ROOT))
from market.backtest import BacktestConfig, HistoricalReplayEngine
from market.ohlcv import OHLCV
from market.risk import TradeProposal

start=datetime(2025,1,1,9,15,tzinfo=timezone.utc)
candles=[]
for index in range(203):
	close=100+index*.1; high=close+.5; low=close-.5
	if index==200: close,high,low=101,101.5,100.5
	if index==201: close,high,low=104,105,100
	candles.append(OHLCV("RELIANCE","NSE",start+timedelta(minutes=index),close,high,low,close,1000,"HISTORICAL_MOCK",True))

def callback(history,analysis,confluence):
	if len(history)==200:
		return TradeProposal("RELIANCE","LONG","101","99","104","100000","1",25,100,history[-1].timestamp,"REPLAY_ONLY",True,confluence)

result=HistoricalReplayEngine(BacktestConfig(warmup_candles=200),proposal_callback=callback).run(candles)
m=result.metrics
print(f"Instrument: {result.instrument}\nReplay start: {result.start_timestamp}\nReplay end: {result.end_timestamp}\nStarting capital: {result.starting_capital}\nEnding capital: {result.ending_capital}\nTotal trades: {m.total_trades}\nWins: {m.winning_trades}\nLosses: {m.losing_trades}\nWin rate: {m.win_rate}\nGross profit: {m.gross_profit}\nGross loss: {m.gross_loss}\nNet P&L: {m.net_pnl}\nAverage win: {m.average_win}\nAverage loss: {m.average_loss}\nExpectancy: {m.expectancy}\nProfit factor: {m.profit_factor}\nMax drawdown: {m.maximum_drawdown}\nMax drawdown %: {m.maximum_drawdown_percent}\nTotal return %: {m.total_return_percent}\nExecution mode: {result.execution_mode}")
for trade in result.trades:print(f"Trade: {trade.direction} {trade.quantity} {trade.entry_price}->{trade.exit_price} {trade.exit_reason} P&L={trade.realized_pnl}")