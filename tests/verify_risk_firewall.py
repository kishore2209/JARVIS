# Run from the project root: python tests/verify_risk_firewall.py
"""Offline deterministic Phase F verification; no orders are created."""
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from market.risk import RiskFirewall, TradeProposal

proposal = TradeProposal("RELIANCE", "LONG", "100", "98", "104", "100000", "1", 25, 125, datetime(2026, 9, 17, 10, tzinfo=timezone.utc), "MOCK", True)
decision = RiskFirewall(clock=lambda: proposal.timestamp).evaluate(proposal)
print(f"Instrument: {proposal.instrument}\nDirection: {proposal.direction}\nEntry: {proposal.proposed_entry}\nStop: {proposal.proposed_stop}\nTarget: {proposal.proposed_target}")
print(f"Risk/unit: {decision.risk_per_unit}\nReward/unit: {decision.reward_per_unit}\nR:R: {decision.risk_reward_ratio}")
print(f"Capital: {proposal.capital_available}\nAllowed risk money: {decision.allowed_risk_money}\nRaw quantity: {decision.raw_quantity}\nApproved quantity: {decision.approved_quantity}\nLot size: {decision.lot_size}")
print(f"Approved: {decision.approved}\nRejection reasons: {list(decision.rejection_reasons)}\nWarnings: {list(decision.warnings)}\nChecks: {list(decision.checks)}")