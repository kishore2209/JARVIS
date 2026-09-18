from dataclasses import dataclass
from decimal import Decimal

from market.risk import _decimal

@dataclass(frozen=True)
class PortfolioAnalysisConfig:
    high_underlying_exposure_percent: Decimal = Decimal("30")
    high_sector_exposure_percent: Decimal = Decimal("40")
    high_gross_exposure_percent: Decimal = Decimal("100")
    high_portfolio_risk_percent: Decimal = Decimal("5")
    elevated_drawdown_percent: Decimal = Decimal("10")
    balanced_net_exposure_tolerance_percent: Decimal = Decimal("5")

@dataclass(frozen=True)
class PortfolioAnalysis:
    timestamp: object; execution_mode: str; starting_capital: Decimal; available_cash: Decimal; capital_in_use: Decimal; total_equity: Decimal; realized_pnl: Decimal; unrealized_pnl: Decimal; total_pnl: Decimal; total_return_percent: Decimal | None; open_position_count: int; closed_position_count: int; long_position_count: int; short_position_count: int; gross_exposure: Decimal; long_exposure: Decimal; short_exposure: Decimal; net_exposure: Decimal; gross_exposure_percent: Decimal | None; net_exposure_percent: Decimal | None; net_exposure_state: str; underlying_exposure: tuple; underlying_exposure_percent: tuple; largest_underlying_exposure: tuple | None; sector_exposure: tuple | None; sector_exposure_percent: tuple | None; largest_sector_exposure: tuple | None; aggregate_initial_risk: Decimal; current_portfolio_risk_percent: Decimal | None; missing_risk_data_count: int; winning_closed_trades: int; losing_closed_trades: int; breakeven_closed_trades: int; win_rate: Decimal | None; average_win: Decimal | None; average_loss: Decimal | None; profit_factor: Decimal | None; expectancy: Decimal | None; current_drawdown: Decimal | None; current_drawdown_percent: Decimal | None; maximum_drawdown: Decimal | None; source_summary: tuple; is_fresh: bool; data_completeness: str; observations: tuple

class PortfolioIntelligenceEngine:
    def __init__(self, config=None): self.config=config or PortfolioAnalysisConfig()
    def analyze(self, account, timestamp, sector_map=None, equity_history=None, execution_mode="PAPER"):
        if execution_mode not in {"PAPER","HISTORICAL_REPLAY"} or account.starting_cash < 0 or account.available_cash < 0: raise ValueError("Invalid account or execution mode.")
        positions=tuple(account.open_positions.values()); self._validate(positions)
        values={p.position_id:_decimal(p.current_price)*p.quantity for p in positions}; long=sum((values[p.position_id] for p in positions if p.direction=="LONG"),Decimal("0")); short=sum((values[p.position_id] for p in positions if p.direction=="SHORT"),Decimal("0")); gross=long+short; net=long-short; reserved=sum((p.reserved_capital for p in positions),Decimal("0")); unrealized=sum((p.unrealized_pnl for p in positions),Decimal("0")); equity=account.available_cash+reserved+unrealized
        by_symbol={}; by_sector={}
        for p in positions:
            by_symbol[p.instrument]=by_symbol.get(p.instrument,Decimal("0"))+values[p.position_id]
            if sector_map and p.instrument in sector_map: by_sector[sector_map[p.instrument]]=by_sector.get(sector_map[p.instrument],Decimal("0"))+values[p.position_id]
        risk,missing=self._risk(positions,account); pnl=[entry.realized_pnl for entry in account.journal]; wins=[x for x in pnl if x>0];losses=[x for x in pnl if x<0]; gp=sum(wins,Decimal("0"));gl=sum(losses,Decimal("0")); total=len(pnl); wr=Decimal(len(wins))/total if total else None;aw=gp/len(wins) if wins else None;al=gl/len(losses) if losses else None; exp=(wr*aw+(1-wr)*al) if wr is not None and aw is not None and al is not None else aw if aw is not None and not losses else al if al is not None and not wins else None
        current_dd,current_dd_pct,max_dd=self._drawdown(equity,equity_history)
        pct=lambda x: x/equity*100 if equity else None; underlying=tuple(sorted(by_symbol.items())); sectors=tuple(sorted(by_sector.items())) if sector_map is not None else None; state="NO_EXPOSURE" if not gross else "BALANCED" if abs(pct(net))<=self.config.balanced_net_exposure_tolerance_percent else "NET_LONG" if net>0 else "NET_SHORT"; observations=[]
        if underlying and max(pct(v) for _,v in underlying)>=self.config.high_underlying_exposure_percent: observations.append("HIGH_UNDERLYING_CONCENTRATION")
        if sectors and max(pct(v) for _,v in sectors)>=self.config.high_sector_exposure_percent: observations.append("HIGH_SECTOR_CONCENTRATION")
        if pct(gross) is not None and pct(gross)>=self.config.high_gross_exposure_percent: observations.append("HIGH_GROSS_EXPOSURE")
        if pct(risk) is not None and pct(risk)>=self.config.high_portfolio_risk_percent: observations.append("HIGH_PORTFOLIO_RISK")
        if state in {"NET_LONG","NET_SHORT"}: observations.append(f"{state}_EXPOSURE")
        if current_dd_pct is not None and current_dd_pct>=self.config.elevated_drawdown_percent: observations.append("DRAWDOWN_ELEVATED")
        if missing: observations.append("RISK_DATA_INCOMPLETE")
        return PortfolioAnalysis(timestamp,execution_mode,account.starting_cash,account.available_cash,reserved,equity,account.realized_pnl,unrealized,account.realized_pnl+unrealized,pct(account.realized_pnl+unrealized),len(positions),len(account.closed_positions),sum(p.direction=="LONG" for p in positions),sum(p.direction=="SHORT" for p in positions),gross,long,short,net,pct(gross),pct(net),state,underlying,tuple((k,pct(v)) for k,v in underlying),max(underlying,key=lambda x:x[1]) if underlying else None,sectors,tuple((k,pct(v)) for k,v in sectors) if sectors is not None else None,max(sectors,key=lambda x:x[1]) if sectors else None,risk,pct(risk),missing,len(wins),len(losses),total-len(wins)-len(losses),wr,aw,al,gp/abs(gl) if gl else None,exp,current_dd,current_dd_pct,max_dd,tuple(sorted({p.source for p in positions})),all(p.current_price is not None for p in positions),"PARTIAL" if missing or sector_map is None else "COMPLETE",tuple(observations))
    @staticmethod
    def _validate(positions):
        for p in positions:
            if p.direction not in {"LONG","SHORT"} or p.quantity<=0 or p.current_price is None or _decimal(p.current_price)<=0: raise ValueError("Invalid open position state.")
    @staticmethod
    def _risk(positions,account):
        total=Decimal("0");missing=0
        for p in positions:
            order=account.order_history.get(p.order_id); risk=getattr(getattr(order,"risk_decision",None),"estimated_monetary_risk",None)
            if risk is None: missing+=1
            else: total+=risk
        return total,missing
    @staticmethod
    def _drawdown(equity,history):
        if not history:return None,None,None
        values=[point.total_equity for point in history];peak=max(values);current=peak-equity;maximum=max(peak-value for value in values);return current,current/peak*100 if peak else None,maximum