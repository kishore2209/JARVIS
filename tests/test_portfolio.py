import sys
from datetime import datetime,timezone
from pathlib import Path
PROJECT_ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(PROJECT_ROOT))
from market.paper_trading import PaperAccount,PaperPosition
from market.portfolio import PortfolioIntelligenceEngine
from decimal import Decimal
def main():
 t=datetime(2026,9,17,tzinfo=timezone.utc);a=PaperAccount("100000",available_cash="70000",realized_pnl=Decimal("500"));a.open_positions={"a":PaperPosition("a","x","RELIANCE","LONG",100,Decimal("100"),Decimal("98"),Decimal("104"),t,"MOCK",current_price=Decimal("105"),unrealized_pnl=Decimal("500"),reserved_capital=Decimal("10000")),"b":PaperPosition("b","y","INFY","SHORT",50,Decimal("100"),Decimal("102"),Decimal("96"),t,"MOCK",current_price=Decimal("98"),unrealized_pnl=Decimal("100"),reserved_capital=Decimal("5000"))};r=PortfolioIntelligenceEngine().analyze(a,t,{"RELIANCE":"ENERGY","INFY":"IT"})
 if (r.total_equity,r.gross_exposure,r.net_exposure,r.net_exposure_state)!=(Decimal("85600"),Decimal("15400"),Decimal("5600"),"NET_LONG"):raise AssertionError("portfolio aggregation mismatch")
 if r!=PortfolioIntelligenceEngine().analyze(a,t,{"RELIANCE":"ENERGY","INFY":"IT"}):raise AssertionError("non-deterministic output")
 print("[PASS] Portfolio Aggregation");print("[PASS] Deterministic Output");return 0
if __name__=="__main__":sys.exit(main())