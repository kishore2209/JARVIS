from dataclasses import dataclass
from datetime import date, datetime, timezone

from market.fno.models import FNOInstrument


@dataclass
class FuturesMarketData:
    underlying_symbol: str
    contract_symbol: str
    token: str
    expiry: date
    price: float | None
    volume: int | None
    open_interest: int | None
    change_in_open_interest: int | None
    price_change: float | None
    lot_size: int
    source: str
    timestamp: datetime
    is_fresh: bool

    @classmethod
    def from_instrument(cls, instrument, price=None, volume=None, open_interest=None,
                        change_in_open_interest=None, price_change=None):
        if not isinstance(instrument, FNOInstrument) or instrument.instrument_type != "FUTURE":
            raise ValueError("A FUTURE FNOInstrument is required.")
        return cls(
            instrument.underlying_symbol, instrument.symbol, instrument.token, instrument.expiry,
            price, volume, open_interest, change_in_open_interest, price_change,
            instrument.lot_size, instrument.source, instrument.timestamp, instrument.is_fresh,
        )


@dataclass
class OptionMarketData:
    underlying_symbol: str
    contract_symbol: str
    token: str
    expiry: date
    strike: float
    option_type: str
    price: float | None
    volume: int | None
    open_interest: int | None
    change_in_open_interest: int | None
    implied_volatility: float | None
    greeks: dict | None
    lot_size: int
    source: str
    timestamp: datetime
    is_fresh: bool

    @classmethod
    def from_instrument(cls, instrument, price=None, volume=None, open_interest=None,
                        change_in_open_interest=None, implied_volatility=None, greeks=None):
        if not isinstance(instrument, FNOInstrument) or instrument.instrument_type != "OPTION":
            raise ValueError("An OPTION FNOInstrument is required.")
        return cls(
            instrument.underlying_symbol, instrument.symbol, instrument.token, instrument.expiry,
            instrument.strike, instrument.option_type, price, volume, open_interest,
            change_in_open_interest, implied_volatility, greeks, instrument.lot_size,
            instrument.source, instrument.timestamp, instrument.is_fresh,
        )


@dataclass
class FuturesAnalysis:
    data: FuturesMarketData
    oi_interpretation: str
    liquidity_status: str
    data_completeness: str


@dataclass
class OptionChainAnalysis:
    underlying_symbol: str
    expiry: date
    underlying_price: float
    contracts: list
    total_ce_oi: int | None
    total_pe_oi: int | None
    pcr: float | None
    highest_ce_oi_strike: float | None
    highest_pe_oi_strike: float | None
    atm_strike: float | None
    strike_moneyness: dict
    oi_resistance_strikes: list
    oi_support_strikes: list
    source: str
    timestamp: datetime
    is_fresh: bool
    data_completeness: str


class FNOIntelligenceEngine:
    """Read-only calculations over normalized futures and option market data."""

    def analyze_future(self, future):
        self._validate_future(future)
        interpretation = self._oi_interpretation(future.price_change, future.change_in_open_interest)
        liquidity = "AVAILABLE" if future.volume is not None and future.volume > 0 else "UNKNOWN"
        completeness = "COMPLETE" if None not in (future.price, future.volume, future.open_interest) else "PARTIAL"
        return FuturesAnalysis(future, interpretation, liquidity, completeness)

    def analyze_option_chain(self, underlying_symbol, underlying_price, options, expiry=None):
        if underlying_price is None or underlying_price <= 0:
            raise ValueError("A positive underlying price is required.")
        filtered = [option for option in options if option.underlying_symbol == underlying_symbol]
        if not filtered:
            raise ValueError("Option chain is empty for the requested underlying.")
        for option in filtered:
            self._validate_option(option)
        selected_expiry = expiry or min(option.expiry for option in filtered)
        contracts = [option for option in filtered if option.expiry == selected_expiry]
        if not contracts:
            raise ValueError("No option contracts exist for the requested expiry.")

        calls = [option for option in contracts if option.option_type == "CE"]
        puts = [option for option in contracts if option.option_type == "PE"]
        total_ce_oi = self._total_oi(calls)
        total_pe_oi = self._total_oi(puts)
        pcr = total_pe_oi / total_ce_oi if total_ce_oi not in (None, 0) and total_pe_oi is not None else None
        highest_ce = self._max_oi_strike(calls)
        highest_pe = self._max_oi_strike(puts)
        atm_strike = min({option.strike for option in contracts}, key=lambda strike: abs(strike - underlying_price))
        moneyness = {option.contract_symbol: self._moneyness(option, atm_strike) for option in contracts}
        latest = max(contracts, key=lambda option: option.timestamp)
        complete = total_ce_oi is not None and total_pe_oi is not None
        return OptionChainAnalysis(
            underlying_symbol, selected_expiry, underlying_price, contracts, total_ce_oi, total_pe_oi,
            pcr, highest_ce, highest_pe, atm_strike, moneyness,
            [highest_ce] if highest_ce is not None else [], [highest_pe] if highest_pe is not None else [],
            latest.source, latest.timestamp, all(option.is_fresh for option in contracts),
            "COMPLETE" if complete else "PARTIAL",
        )

    @staticmethod
    def _oi_interpretation(price_change, oi_change):
        if price_change is None or oi_change is None:
            return "UNKNOWN"
        if price_change > 0 and oi_change > 0:
            return "LONG_BUILDUP"
        if price_change < 0 and oi_change > 0:
            return "SHORT_BUILDUP"
        if price_change > 0 and oi_change < 0:
            return "SHORT_COVERING"
        if price_change < 0 and oi_change < 0:
            return "LONG_UNWINDING"
        return "UNKNOWN"

    @staticmethod
    def _validate_future(future):
        if not isinstance(future, FuturesMarketData) or not future.is_fresh:
            raise ValueError("Fresh normalized futures data is required.")
        if future.price is not None and future.price <= 0:
            raise ValueError("Future price must be positive.")
        if future.open_interest is not None and future.open_interest < 0:
            raise ValueError("Future open interest cannot be negative.")

    @staticmethod
    def _validate_option(option):
        if not isinstance(option, OptionMarketData) or not option.is_fresh:
            raise ValueError("Fresh normalized option data is required.")
        if option.option_type not in {"CE", "PE"} or option.strike is None or option.strike <= 0:
            raise ValueError("Option type and positive strike are required.")
        if option.open_interest is not None and option.open_interest < 0:
            raise ValueError("Option open interest cannot be negative.")

    @staticmethod
    def _total_oi(contracts):
        return None if any(contract.open_interest is None for contract in contracts) else sum(contract.open_interest for contract in contracts)

    @staticmethod
    def _max_oi_strike(contracts):
        eligible = [contract for contract in contracts if contract.open_interest is not None]
        return max(eligible, key=lambda contract: contract.open_interest).strike if eligible else None

    @staticmethod
    def _moneyness(option, atm_strike):
        if option.strike == atm_strike:
            return "ATM"
        if (option.option_type == "CE" and option.strike < atm_strike) or (option.option_type == "PE" and option.strike > atm_strike):
            return "ITM"
        return "OTM"