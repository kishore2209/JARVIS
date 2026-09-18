# Run from the project root: python tests/test_risk_firewall.py
"""Deterministic offline tests for the independent Phase F Risk Firewall."""
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from market.risk import PortfolioRiskContext, RiskConfig, RiskFirewall, TradeProposal


def main():
    now = datetime(2026, 9, 17, 10, tzinfo=timezone.utc)
    firewall = RiskFirewall(clock=lambda: now)
    results = []
    def proposal(direction="LONG", entry="100", stop="98", target="104", requested=None, fresh=True): return TradeProposal("RELIANCE", direction, entry, stop, target, "100000", "1", 25, requested, now, "MOCK", fresh)
    def run(name, test):
        try: test(); results.append(True); print(f"[PASS] {name}")
        except Exception as error: results.append(False); print(f"[FAIL] {name}"); print(f"Reason: {error}")
    def test_valid_long_short_math():
        long = firewall.evaluate(proposal(requested=125)); short = firewall.evaluate(proposal("SHORT", "100", "102", "96", requested=125))
        if not long.approved or not short.approved or (long.risk_per_unit, long.reward_per_unit, long.risk_reward_ratio) != (Decimal("2"), Decimal("4"), Decimal("2")): raise AssertionError("valid geometry or math failed")
    def test_invalid_prices_geometry_rr():
        if firewall.evaluate(proposal(stop="101")).approved or firewall.evaluate(proposal(target="102")).approved: raise AssertionError("invalid geometry or R:R accepted")
        if firewall.evaluate(proposal(entry="0")).approved: raise AssertionError("non-positive price accepted")
    def test_sizing_lots_requested():
        decision = firewall.evaluate(proposal(requested=130))
        if (decision.allowed_risk_money, decision.raw_quantity, decision.approved_quantity, decision.estimated_monetary_risk) != (Decimal("1000"), Decimal("500"), 125, Decimal("250")): raise AssertionError("sizing/lot rounding/cap failed")
        if firewall.evaluate(proposal(entry="10000", stop="9999", target="10002")).approved: raise AssertionError("zero lot accepted")
    def test_freshness_portfolio_metadata():
        if firewall.evaluate(proposal(fresh=False)).approved: raise AssertionError("stale proposal accepted")
        context = PortfolioRiskContext("100000", 5, "4900", (("RELIANCE", 1),), (("FINANCE", "29000"),))
        rejected = firewall.evaluate(proposal(), context)
        if rejected.approved or rejected.source != "MOCK" or rejected.timestamp != now: raise AssertionError("portfolio or metadata checks failed")
        missing = firewall.evaluate(proposal())
        if "Portfolio risk context is not available." not in missing.warnings: raise AssertionError("missing portfolio not marked")
        if missing != firewall.evaluate(proposal()): raise AssertionError("non-deterministic output")
    print("="*40); print("J.A.R.V.I.S RISK FIREWALL TEST"); print("="*40)
    run("Valid Long Short And Math", test_valid_long_short_math); run("Invalid Prices Geometry Risk Reward", test_invalid_prices_geometry_rr); run("Sizing Lots Requested Quantity", test_sizing_lots_requested); run("Freshness Portfolio Metadata Determinism", test_freshness_portfolio_metadata)
    passed=sum(results); print("="*40); print("TEST SUMMARY"); print("="*40); print(f"Total Tests : {len(results)}"); print(f"Passed      : {passed}"); print(f"Failed      : {len(results)-passed}"); print("Status      : ALL TESTS PASSED" if passed == len(results) else "Status      : TESTS FAILED"); print("="*40); return len(results)-passed
if __name__ == "__main__": sys.exit(main())