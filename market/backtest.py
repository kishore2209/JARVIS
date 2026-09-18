from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from market.confluence import ConfluenceEngine
from market.paper_trading import PaperAccount, PaperTradingEngine
from market.risk import RiskConfig, RiskFirewall
from market.strategies.engine import MultiStrategyEngine
from market.underlying_analysis import UnderlyingAnalysisEngine


@dataclass(frozen=True)
class ReplayClock:
    candles: tuple
    index: int = -1
    def advance(self):
        if self.index + 1 >= len(self.candles): raise StopIteration
        return ReplayClock(self.candles, self.index + 1)
    @property
    def timestamp(self): return self.candles[self.index].timestamp if self.index >= 0 else None
    @property
    def available_candles(self): return self.candles[:self.index + 1]


@dataclass(frozen=True)
class BacktestConfig:
    warmup_candles: int = 200
    starting_capital: Decimal = Decimal("100000")
    evaluation_frequency: int = 1
    execution_timing: str = "NEXT_CANDLE_OPEN"
    same_candle_policy: str = "STOP_FIRST"
    fees_enabled: bool = False
    slippage_enabled: bool = False
    close_at_end: bool = True


@dataclass(frozen=True)
class EquityPoint:
    timestamp: datetime
    cash: Decimal
    unrealized_pnl: Decimal
    total_equity: Decimal


@dataclass(frozen=True)
class BacktestTrade:
    instrument: str
    direction: str
    quantity: int
    entry_price: Decimal
    exit_price: Decimal
    realized_pnl: Decimal
    exit_reason: str
    r_multiple: Decimal | None
    opened_at: datetime
    closed_at: datetime
    execution_mode: str = "HISTORICAL_REPLAY"


@dataclass(frozen=True)
class BacktestMetrics:
    total_trades: int
    winning_trades: int
    losing_trades: int
    breakeven_trades: int
    gross_profit: Decimal
    gross_loss: Decimal
    net_pnl: Decimal
    win_rate: Decimal | None
    average_win: Decimal | None
    average_loss: Decimal | None
    expectancy: Decimal | None
    profit_factor: Decimal | None
    maximum_drawdown: Decimal
    maximum_drawdown_percent: Decimal | None
    average_r_multiple: Decimal | None
    total_return_percent: Decimal | None


@dataclass(frozen=True)
class BacktestResult:
    instrument: str
    start_timestamp: datetime
    end_timestamp: datetime
    starting_capital: Decimal
    ending_capital: Decimal
    trades: tuple
    equity_curve: tuple
    metrics: BacktestMetrics
    configuration: BacktestConfig
    source: str
    execution_mode: str = "HISTORICAL_REPLAY"
    data_status: str = "HISTORICAL"


class HistoricalReplayEngine:
    """Replays completed historical candles. Proposal callbacks must be REPLAY_ONLY."""
    def __init__(self, config=None, risk_config=None, proposal_callback=None):
        self.config = config or BacktestConfig()
        self.risk_config = risk_config or RiskConfig()
        self.proposal_callback = proposal_callback
        if self.config.execution_timing != "NEXT_CANDLE_OPEN": raise ValueError("Only NEXT_CANDLE_OPEN is supported.")

    def run(self, candles):
        candles = tuple(candles); self._validate(candles)
        if len(candles) < self.config.warmup_candles: raise ValueError("Not enough candles for configured warm-up.")
        account = PaperAccount(self.config.starting_capital); paper = PaperTradingEngine(account, self.config.same_candle_policy)
        clock = ReplayClock(candles); pending = []; curve = []
        while True:
            try: clock = clock.advance()
            except StopIteration: break
            candle = candles[clock.index]
            for position_id in tuple(account.open_positions): paper.evaluate_completed_candle(position_id, candle)
            for proposal, decision in pending:
                order = paper.create_order(proposal, decision)
                paper.fill_order(order.order_id, candle.open, candle.timestamp, candle.source, True)
            pending = []
            if clock.index + 1 >= self.config.warmup_candles and (clock.index + 1 - self.config.warmup_candles) % self.config.evaluation_frequency == 0:
                pending = self._evaluate(clock, candle)
            curve.append(self._equity_point(candle.timestamp, account))
        if self.config.close_at_end:
            for position_id in tuple(account.open_positions): paper.close_position(position_id, candles[-1].close, candles[-1].timestamp, "END_OF_REPLAY")
            curve[-1] = self._equity_point(candles[-1].timestamp, account)
        trades = tuple(self._trade(entry) for entry in account.journal)
        return BacktestResult(candles[-1].symbol, candles[0].timestamp, candles[-1].timestamp, account.starting_cash, account.available_cash, trades, tuple(curve), self._metrics(trades, curve, account.starting_cash), self.config, candles[-1].source)

    def _evaluate(self, clock, candle):
        if self.proposal_callback is None: return []
        analysis = UnderlyingAnalysisEngine().analyze(clock.available_candles)
        evidence = MultiStrategyEngine().analyze(clock.available_candles, analysis)
        confluence = ConfluenceEngine().analyze(analysis, evidence)
        proposal = self.proposal_callback(clock.available_candles, analysis, confluence)
        if proposal is None: return []
        if proposal.source != "REPLAY_ONLY": raise ValueError("Historical proposals must have source REPLAY_ONLY.")
        decision = RiskFirewall(self.risk_config, clock=lambda: candle.timestamp).evaluate(proposal)
        return [(proposal, decision)] if decision.approved else []

    @staticmethod
    def _validate(candles):
        if not candles: raise ValueError("Historical candle input is empty.")
        timestamps = [candle.timestamp for candle in candles]
        if any(timestamp.tzinfo is None for timestamp in timestamps): raise ValueError("Historical timestamps must be timezone-aware.")
        if timestamps != sorted(timestamps) or len(set(timestamps)) != len(timestamps): raise ValueError("Historical candles must be sorted with unique timestamps.")
        for candle in candles:
            if min(candle.open, candle.high, candle.low, candle.close) < 0 or candle.low > candle.high or candle.volume < 0: raise ValueError("Historical OHLCV data is invalid.")

    @staticmethod
    def _trade(entry):
        risk = entry.risk_decision.estimated_monetary_risk
        r_multiple = entry.realized_pnl / risk if risk else None
        return BacktestTrade(entry.instrument, entry.direction, entry.quantity, entry.entry_price, entry.exit_price, entry.realized_pnl, entry.exit_reason, r_multiple, entry.opened_at, entry.closed_at)

    @staticmethod
    def _equity_point(timestamp, account):
        reserved = sum((position.reserved_capital for position in account.open_positions.values()), Decimal("0"))
        total_equity = account.available_cash + reserved + account.unrealized_pnl
        return EquityPoint(timestamp, account.available_cash, account.unrealized_pnl, total_equity)

    @staticmethod
    def _metrics(trades, curve, starting):
        pnl = [trade.realized_pnl for trade in trades]; wins = [value for value in pnl if value > 0]; losses = [value for value in pnl if value < 0]
        total = len(pnl); net = sum(pnl, Decimal("0")); gross_profit = sum(wins, Decimal("0")); gross_loss = sum(losses, Decimal("0"))
        win_rate = Decimal(len(wins)) / total if total else None; average_win = gross_profit / len(wins) if wins else None; average_loss = gross_loss / len(losses) if losses else None
        expectancy = (win_rate * average_win + (Decimal("1") - win_rate) * average_loss) if win_rate is not None and average_win is not None and average_loss is not None else average_win if average_win is not None and not losses else average_loss if average_loss is not None and not wins else None
        profit_factor = gross_profit / abs(gross_loss) if gross_loss else None
        peak = starting; drawdown = Decimal("0")
        for point in curve: peak = max(peak, point.total_equity); drawdown = max(drawdown, peak - point.total_equity)
        r_values = [trade.r_multiple for trade in trades if trade.r_multiple is not None]
        return BacktestMetrics(total, len(wins), len(losses), total-len(wins)-len(losses), gross_profit, gross_loss, net, win_rate, average_win, average_loss, expectancy, profit_factor, drawdown, drawdown / peak * 100 if peak else None, sum(r_values, Decimal("0"))/len(r_values) if r_values else None, net / starting * 100 if starting else None)