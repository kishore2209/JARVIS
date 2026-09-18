from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal

from market.risk import RiskDecision, TradeProposal, _decimal


@dataclass(frozen=True)
class VirtualOrder:
    order_id: str
    instrument: str
    direction: str
    quantity: int
    requested_entry: Decimal
    stop: Decimal
    target: Decimal
    lot_size: int
    timestamp: datetime
    source: str
    status: str
    risk_decision: RiskDecision
    evidence_reference: object | None
    execution_mode: str = "PAPER"


@dataclass(frozen=True)
class VirtualFill:
    fill_id: str
    order_id: str
    instrument: str
    direction: str
    quantity: int
    fill_price: Decimal
    timestamp: datetime
    source: str
    fill_reason: str
    execution_mode: str = "PAPER"


@dataclass
class PaperPosition:
    position_id: str
    order_id: str
    instrument: str
    direction: str
    quantity: int
    entry_price: Decimal
    stop: Decimal
    target: Decimal
    opened_at: datetime
    source: str
    status: str = "OPEN"
    current_price: Decimal | None = None
    unrealized_pnl: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    closed_at: datetime | None = None
    exit_price: Decimal | None = None
    exit_reason: str | None = None
    reserved_capital: Decimal = Decimal("0")


@dataclass(frozen=True)
class TradeJournalEntry:
    order_id: str
    position_id: str
    instrument: str
    direction: str
    quantity: int
    entry_price: Decimal
    exit_price: Decimal
    stop: Decimal
    target: Decimal
    realized_pnl: Decimal
    opened_at: datetime
    closed_at: datetime
    exit_reason: str
    risk_decision: RiskDecision
    evidence_reference: object | None
    source: str
    execution_mode: str = "PAPER"


@dataclass
class PaperAccount:
    starting_cash: Decimal
    available_cash: Decimal | None = None
    realized_pnl: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    open_positions: dict = None
    closed_positions: dict = None
    order_history: dict = None
    fill_history: dict = None
    journal: list = None

    def __post_init__(self):
        self.starting_cash = _decimal(self.starting_cash)
        self.available_cash = self.starting_cash if self.available_cash is None else _decimal(self.available_cash)
        self.open_positions = {} if self.open_positions is None else self.open_positions
        self.closed_positions = {} if self.closed_positions is None else self.closed_positions
        self.order_history = {} if self.order_history is None else self.order_history
        self.fill_history = {} if self.fill_history is None else self.fill_history
        self.journal = [] if self.journal is None else self.journal


class PaperTradingEngine:
    """Deterministic in-memory PAPER executor. It has no provider or broker dependency."""
    def __init__(self, account, same_candle_policy="STOP_FIRST"):
        if same_candle_policy != "STOP_FIRST":
            raise ValueError("Only the conservative STOP_FIRST policy is supported.")
        self.account = account
        self.same_candle_policy = same_candle_policy
        self._order_number = self._fill_number = self._position_number = 0

    def create_order(self, proposal, decision):
        if not isinstance(proposal, TradeProposal) or not isinstance(decision, RiskDecision):
            raise ValueError("TradeProposal and RiskDecision are required.")
        if not decision.approved:
            raise ValueError("Paper order rejected: RiskDecision is not approved.")
        if proposal.instrument != decision.instrument or decision.approved_quantity <= 0:
            raise ValueError("Paper order rejected: approved decision does not match proposal.")
        self._order_number += 1
        order = VirtualOrder(f"PAPER-ORDER-{self._order_number:04d}", proposal.instrument, proposal.direction, decision.approved_quantity, proposal.proposed_entry, proposal.proposed_stop, proposal.proposed_target, proposal.lot_size, proposal.timestamp, proposal.source, "PENDING", decision, proposal.evidence_reference)
        self.account.order_history[order.order_id] = order
        return order

    def fill_order(self, order_id, fill_price, timestamp, source, is_fresh=True):
        order = self._order(order_id, "PENDING")
        if not is_fresh:
            raise ValueError("Paper fill rejected: market data is stale.")
        price = _decimal(fill_price)
        if price <= 0:
            raise ValueError("Paper fill price must be positive.")
        reserved = price * order.quantity
        if reserved > self.account.available_cash:
            raise ValueError("Paper fill rejected: insufficient available cash.")
        self._fill_number += 1; self._position_number += 1
        fill = VirtualFill(f"PAPER-FILL-{self._fill_number:04d}", order.order_id, order.instrument, order.direction, order.quantity, price, self._utc(timestamp), source, "MARKET_SIMULATION")
        position = PaperPosition(f"PAPER-POS-{self._position_number:04d}", order.order_id, order.instrument, order.direction, order.quantity, price, order.stop, order.target, fill.timestamp, source, current_price=price, reserved_capital=reserved)
        self.account.available_cash -= reserved
        self.account.fill_history[fill.fill_id] = fill
        self.account.order_history[order_id] = replace(order, status="FILLED")
        self.account.open_positions[position.position_id] = position
        return fill, position

    def mark_to_market(self, position_id, price, timestamp, is_fresh=True):
        position = self._position(position_id, "OPEN")
        if not is_fresh:
            raise ValueError("Paper mark rejected: market data is stale.")
        position.current_price = _decimal(price)
        if position.current_price <= 0:
            raise ValueError("Paper market price must be positive.")
        position.unrealized_pnl = self._pnl(position.direction, position.entry_price, position.current_price, position.quantity)
        self._refresh_unrealized()
        return position

    def evaluate_completed_candle(self, position_id, candle):
        position = self._position(position_id, "OPEN")
        if not candle.is_fresh:
            raise ValueError("Paper exit evaluation rejected: candle is stale.")
        stop_hit = candle.low <= position.stop if position.direction == "LONG" else candle.high >= position.stop
        target_hit = candle.high >= position.target if position.direction == "LONG" else candle.low <= position.target
        if stop_hit:
            return self.close_position(position_id, position.stop, candle.timestamp, "STOP")
        if target_hit:
            return self.close_position(position_id, position.target, candle.timestamp, "TARGET")
        return self.mark_to_market(position_id, candle.close, candle.timestamp, candle.is_fresh)

    def close_position(self, position_id, exit_price, timestamp, reason="MANUAL_PAPER"):
        position = self._position(position_id, "OPEN")
        price = _decimal(exit_price)
        if price <= 0:
            raise ValueError("Paper exit price must be positive.")
        realized = self._pnl(position.direction, position.entry_price, price, position.quantity)
        position.status, position.closed_at, position.exit_price, position.exit_reason = "CLOSED", self._utc(timestamp), price, reason
        position.realized_pnl, position.unrealized_pnl = realized, Decimal("0")
        self.account.available_cash += position.reserved_capital + realized
        self.account.realized_pnl += realized
        self.account.open_positions.pop(position_id); self.account.closed_positions[position_id] = position
        self.account.order_history[position.order_id] = replace(self.account.order_history[position.order_id], status="CLOSED")
        entry = TradeJournalEntry(position.order_id, position.position_id, position.instrument, position.direction, position.quantity, position.entry_price, price, position.stop, position.target, realized, position.opened_at, position.closed_at, reason, self.account.order_history[position.order_id].risk_decision, self.account.order_history[position.order_id].evidence_reference, position.source)
        self.account.journal.append(entry); self._refresh_unrealized()
        return position, entry

    def _order(self, order_id, expected):
        order = self.account.order_history.get(order_id)
        if order is None or order.status != expected:
            raise ValueError(f"Order must exist and be {expected}.")
        return order
    def _position(self, position_id, expected):
        position = self.account.open_positions.get(position_id)
        if position is None or position.status != expected:
            raise ValueError(f"Position must exist and be {expected}.")
        return position
    @staticmethod
    def _pnl(direction, entry, exit_price, quantity):
        return (exit_price - entry if direction == "LONG" else entry - exit_price) * quantity
    def _refresh_unrealized(self): self.account.unrealized_pnl = sum((p.unrealized_pnl for p in self.account.open_positions.values()), Decimal("0"))
    @staticmethod
    def _utc(timestamp): return timestamp.replace(tzinfo=timezone.utc) if timestamp.tzinfo is None else timestamp.astimezone(timezone.utc)