from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN


def _decimal(value):
    return value if isinstance(value, Decimal) else Decimal(str(value))


@dataclass(frozen=True)
class TradeProposal:
    """Explicit trade input. It does not constitute a recommendation or order."""
    instrument: str
    direction: str
    proposed_entry: Decimal
    proposed_stop: Decimal
    proposed_target: Decimal
    capital_available: Decimal
    risk_per_trade_percent: Decimal
    lot_size: int
    quantity_requested: int | None
    timestamp: datetime
    source: str
    is_fresh: bool
    evidence_reference: object | None = None
    sector: str | None = None
    liquidity_status: str | None = None

    def __post_init__(self):
        for name in ("proposed_entry", "proposed_stop", "proposed_target", "capital_available", "risk_per_trade_percent"):
            object.__setattr__(self, name, _decimal(getattr(self, name)))
        timestamp = self.timestamp.replace(tzinfo=timezone.utc) if self.timestamp.tzinfo is None else self.timestamp.astimezone(timezone.utc)
        object.__setattr__(self, "timestamp", timestamp)


@dataclass(frozen=True)
class RiskConfig:
    """Conservative generic defaults; callers can inject portfolio-specific limits."""
    max_risk_per_trade_percent: Decimal = Decimal("1")
    max_total_portfolio_risk_percent: Decimal = Decimal("5")
    minimum_risk_reward_ratio: Decimal = Decimal("1.5")
    max_open_positions: int = 5
    max_positions_per_underlying: int = 1
    max_sector_exposure_percent: Decimal = Decimal("30")
    max_single_position_capital_percent: Decimal = Decimal("25")
    maximum_data_age: timedelta = timedelta(minutes=15)
    require_fresh_data: bool = True
    minimum_liquidity: str | None = None
    reject_incomplete_evidence: bool = False

    def __post_init__(self):
        for name in ("max_risk_per_trade_percent", "max_total_portfolio_risk_percent", "minimum_risk_reward_ratio", "max_sector_exposure_percent", "max_single_position_capital_percent"):
            object.__setattr__(self, name, _decimal(getattr(self, name)))


@dataclass(frozen=True)
class PortfolioRiskContext:
    available_capital: Decimal
    open_positions_count: int = 0
    current_total_risk: Decimal = Decimal("0")
    existing_underlying_exposure: tuple = ()
    sector_exposure: tuple = ()

    def __post_init__(self):
        object.__setattr__(self, "available_capital", _decimal(self.available_capital))
        object.__setattr__(self, "current_total_risk", _decimal(self.current_total_risk))


@dataclass(frozen=True)
class RiskDecision:
    instrument: str
    approved: bool
    rejection_reasons: tuple
    warnings: tuple
    risk_per_unit: Decimal | None
    reward_per_unit: Decimal | None
    risk_reward_ratio: Decimal | None
    allowed_risk_money: Decimal | None
    raw_quantity: Decimal | None
    approved_quantity: int
    lot_size: int
    estimated_position_value: Decimal | None
    estimated_monetary_risk: Decimal | None
    freshness_status: str
    data_completeness: str
    checks: tuple
    timestamp: datetime
    source: str


class RiskFirewall:
    """Independent deterministic validator for explicit trade proposals only."""
    def __init__(self, config=None, clock=None):
        self.config = config or RiskConfig()
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def evaluate(self, proposal, portfolio_context=None):
        if not isinstance(proposal, TradeProposal):
            raise ValueError("A TradeProposal is required.")
        reasons, warnings, checks = [], [], []
        check = lambda name, passed, reason: self._check(checks, reasons, name, passed, reason)
        valid_prices = all(value > 0 for value in (proposal.proposed_entry, proposal.proposed_stop, proposal.proposed_target))
        check("positive_prices", valid_prices, "Entry, stop, and target must be positive.")
        valid_direction = proposal.direction in {"LONG", "SHORT"}
        check("valid_direction", valid_direction, "Direction must be LONG or SHORT.")
        valid_lot = isinstance(proposal.lot_size, int) and proposal.lot_size > 0
        check("valid_lot_size", valid_lot, "Lot size must be a positive integer.")
        geometry = valid_prices and valid_direction and ((proposal.direction == "LONG" and proposal.proposed_stop < proposal.proposed_entry < proposal.proposed_target) or (proposal.direction == "SHORT" and proposal.proposed_target < proposal.proposed_entry < proposal.proposed_stop))
        check("valid_geometry", geometry, "Proposal price geometry is invalid for its direction.")
        fresh = self._is_fresh(proposal)
        check("fresh_data", fresh or not self.config.require_fresh_data, "Proposal data is stale or marked not fresh.")
        self._evidence_check(proposal, checks, reasons, warnings)
        if not (valid_prices and valid_direction and valid_lot and geometry):
            return self._decision(proposal, reasons, warnings, checks, None, None, None, None, None, 0)

        risk = abs(proposal.proposed_entry - proposal.proposed_stop)
        reward = abs(proposal.proposed_target - proposal.proposed_entry)
        ratio = reward / risk
        allowed_percent = min(proposal.risk_per_trade_percent, self.config.max_risk_per_trade_percent)
        allowed_risk = proposal.capital_available * allowed_percent / Decimal("100")
        raw_quantity = allowed_risk / risk
        requested = Decimal(proposal.quantity_requested) if proposal.quantity_requested is not None else raw_quantity
        capital_quantity = proposal.capital_available / proposal.proposed_entry
        capped_quantity = min(raw_quantity, requested, capital_quantity)
        quantity = int((capped_quantity / proposal.lot_size).to_integral_value(rounding=ROUND_DOWN)) * proposal.lot_size
        check("minimum_risk_reward", ratio >= self.config.minimum_risk_reward_ratio, "Risk/reward ratio is below the configured minimum.")
        check("non_zero_lot_quantity", quantity > 0, "No whole lot fits the risk and capital limits.")
        position_value = proposal.proposed_entry * quantity
        monetary_risk = risk * quantity
        check("single_position_capital", position_value <= proposal.capital_available * self.config.max_single_position_capital_percent / Decimal("100"), "Position exceeds the configured capital allocation limit.")
        self._liquidity_check(proposal, checks, reasons, warnings)
        self._portfolio_checks(proposal, portfolio_context, monetary_risk, position_value, checks, reasons, warnings)
        return self._decision(proposal, reasons, warnings, checks, risk, reward, ratio, allowed_risk, raw_quantity, quantity, position_value, monetary_risk)

    def _is_fresh(self, proposal):
        now = self._clock().astimezone(timezone.utc)
        return proposal.is_fresh and now - proposal.timestamp <= self.config.maximum_data_age

    def _evidence_check(self, proposal, checks, reasons, warnings):
        evidence = proposal.evidence_reference
        if evidence is None:
            warnings.append("Confluence evidence is not available."); checks.append(("evidence_available", "NOT_AVAILABLE")); return
        complete = getattr(evidence, "data_completeness", "PARTIAL") == "COMPLETE"
        fresh = getattr(evidence, "is_fresh", False)
        passed = complete and fresh
        if not passed and self.config.reject_incomplete_evidence: reasons.append("Confluence evidence is stale or incomplete.")
        elif not passed: warnings.append("Confluence evidence is stale or incomplete.")
        checks.append(("evidence_quality", "PASS" if passed else "WARN" if not self.config.reject_incomplete_evidence else "FAIL"))

    def _liquidity_check(self, proposal, checks, reasons, warnings):
        if self.config.minimum_liquidity is None:
            checks.append(("liquidity", "NOT_AVAILABLE")); return
        if proposal.liquidity_status is None:
            warnings.append("Liquidity data is not available."); checks.append(("liquidity", "NOT_AVAILABLE")); return
        self._check(checks, reasons, "liquidity", proposal.liquidity_status == self.config.minimum_liquidity, "Liquidity does not meet the configured requirement.")

    def _portfolio_checks(self, proposal, context, monetary_risk, position_value, checks, reasons, warnings):
        if context is None:
            warnings.append("Portfolio risk context is not available."); checks.append(("portfolio_context", "NOT_AVAILABLE")); return
        check = lambda name, passed, reason: self._check(checks, reasons, name, passed, reason)
        check("max_open_positions", context.open_positions_count < self.config.max_open_positions, "Maximum open positions reached.")
        underlying = dict(context.existing_underlying_exposure).get(proposal.instrument, 0)
        check("duplicate_underlying", underlying < self.config.max_positions_per_underlying, "Maximum positions for this underlying reached.")
        total_limit = context.available_capital * self.config.max_total_portfolio_risk_percent / Decimal("100")
        check("portfolio_risk", context.current_total_risk + monetary_risk <= total_limit, "Portfolio risk limit would be exceeded.")
        if proposal.sector is None:
            warnings.append("Sector metadata is not available."); checks.append(("sector_exposure", "NOT_AVAILABLE"))
        else:
            sector_value = _decimal(dict(context.sector_exposure).get(proposal.sector, 0))
            limit = context.available_capital * self.config.max_sector_exposure_percent / Decimal("100")
            check("sector_exposure", sector_value + position_value <= limit, "Sector exposure limit would be exceeded.")

    @staticmethod
    def _check(checks, reasons, name, passed, reason):
        checks.append((name, "PASS" if passed else "FAIL"))
        if not passed: reasons.append(reason)

    def _decision(self, proposal, reasons, warnings, checks, risk, reward, ratio, allowed, raw, quantity, value=None, monetary_risk=None):
        return RiskDecision(proposal.instrument, not reasons, tuple(reasons), tuple(warnings), risk, reward, ratio, allowed, raw, quantity, proposal.lot_size, value, monetary_risk, "FRESH" if self._is_fresh(proposal) else "STALE", "COMPLETE" if not reasons and not warnings else "PARTIAL", tuple(checks), proposal.timestamp, proposal.source)