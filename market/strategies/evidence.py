from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class StrategyEvidence:
    """Immutable deterministic observations from one analysis strategy."""

    strategy_name: str
    instrument: str
    timestamp: datetime
    direction: str
    evidence_strength: str
    evidence: tuple
    conflicting_evidence: tuple
    invalidation_conditions: tuple
    source: str
    is_fresh: bool
    data_completeness: str
    context_alignment: str = "NOT_AVAILABLE"