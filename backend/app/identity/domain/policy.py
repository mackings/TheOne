"""Decision policy combining match score, spoof score and transaction context."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Decision(StrEnum):
    """STEP_UP asks for a second check, such as iris or the phone's fingerprint."""

    ACCEPT = "ACCEPT"
    STEP_UP = "STEP_UP"
    REJECT = "REJECT"


HIGH_RISK_CONTEXTS = {
    "high_value_transfer",
    "change_beneficiary",
    "unfreeze_account",
    "account_recovery",
}


@dataclass
class Thresholds:
    match_accept: float
    match_stepup: float
    spoof_stepup: float
    spoof_reject: float
    high_risk_margin: float = 0.10


@dataclass
class PolicyResult:
    decision: Decision
    reasons: list[str] = field(default_factory=list)
    effective_accept_threshold: float = 0.0


def decide(match: float, spoof: float, context: str | None, t: Thresholds) -> PolicyResult:
    reasons: list[str] = []
    accept = t.match_accept
    if context in HIGH_RISK_CONTEXTS:
        accept += t.high_risk_margin
        reasons.append(f"high-risk context '{context}': accept threshold raised to {accept:.2f}")

    if spoof >= t.spoof_reject:
        reasons.append(f"spoof score {spoof:.2f} >= reject threshold {t.spoof_reject:.2f}")
        return PolicyResult(Decision.REJECT, reasons, accept)

    if match < t.match_stepup:
        reasons.append(f"match score {match:.2f} below step-up floor {t.match_stepup:.2f}")
        return PolicyResult(Decision.REJECT, reasons, accept)

    if spoof >= t.spoof_stepup:
        reasons.append(f"spoof score {spoof:.2f} >= step-up threshold {t.spoof_stepup:.2f}")
        return PolicyResult(Decision.STEP_UP, reasons, accept)

    if match >= accept:
        reasons.append(f"match score {match:.2f} >= accept threshold {accept:.2f}")
        return PolicyResult(Decision.ACCEPT, reasons, accept)

    reasons.append(f"match score {match:.2f} in step-up band [{t.match_stepup:.2f}, {accept:.2f})")
    return PolicyResult(Decision.STEP_UP, reasons, accept)
