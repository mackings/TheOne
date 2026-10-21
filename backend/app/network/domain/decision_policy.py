"""The real-time transfer decision: ALLOW, WARN_PAYEE, STEP_UP_OWNER or HOLD, with reasons a customer
service agent can read out."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.network.domain.engine import naira
from app.network.domain.sender import SenderAssessment

SEVERITY = {"ALLOW": 0, "WARN_PAYEE": 1, "STEP_UP_OWNER": 2, "HOLD": 3}
STATUS = {"ALLOW": "allowed", "WARN_PAYEE": "pending", "STEP_UP_OWNER": "pending", "HOLD": "pending_review"}
BLOCKED = {"watchlist", "confirmed_mule"}


def risk_words(score: float) -> str:
    return "very high" if score >= 0.85 else "high" if score >= 0.6 else "medium" if score >= 0.35 else "low"


@dataclass
class Verdict:
    decision: str = "ALLOW"
    reasons: list[str] = field(default_factory=list)
    bank_otp_fallback: bool = False
    over_safe_limit: bool = False

    def raise_to(self, level: str, reason: str) -> None:
        self.reasons.append(reason)
        if SEVERITY[level] > SEVERITY[self.decision]:
            self.decision = level

    @property
    def status(self) -> str:
        return STATUS[self.decision]


def decide(*, src_status: str, src_score: float, dst_status: str, dst_score: float, owner_methods: list[str],
           sender: SenderAssessment, flag: float, hold: float, sender_stepup: float, safe_limit: int | None) -> Verdict:
    v = Verdict()
    if src_status in BLOCKED:
        v.raise_to("HOLD", f"The sender's account is {'on the 24-hour watch' if src_status == 'watchlist' else 'confirmed as a mule account'}, "
                   "so money cannot leave it.")
    elif src_score >= hold:
        v.raise_to("HOLD", f"The sender's account looks like a mule account ({risk_words(src_score)} risk), so the payment is held.")
    elif src_score >= flag:
        if owner_methods:
            v.raise_to("STEP_UP_OWNER", f"The sender's account looks suspicious ({risk_words(src_score)} risk). "
                       "The owner must confirm it is really them making this payment.")
        else:
            v.raise_to("HOLD", f"The sender's account looks suspicious ({risk_words(src_score)} risk) and the owner has no voice or iris "
                       "set up to confirm it is them, so the payment is held.")
    if dst_status in BLOCKED:
        v.raise_to("HOLD", "The receiver's account is on the watch list or confirmed as a mule account. "
                   "The payment is held to protect the sender.")
    elif dst_score >= hold:
        v.raise_to("HOLD", f"The receiver's account looks like a mule account ({risk_words(dst_score)} risk), so this is probably a scam. "
                   "The payment is held and the sender should be contacted.")
    elif dst_score >= flag:
        v.raise_to("WARN_PAYEE", f"The receiver's account looks suspicious ({risk_words(dst_score)} risk). Warn the sender before they pay.")

    top = sorted(sender.signals, key=lambda x: -x.weight)
    if sender.score >= hold:
        v.raise_to("HOLD", f"This payment is very unusual for this customer: {top[0].reason}.")
    elif sender.score >= sender_stepup:
        if owner_methods:
            v.raise_to("STEP_UP_OWNER", f"This payment is unusual for this customer: {top[0].reason}. "
                       "The owner must confirm it is really them.")
        else:
            # The bank's usual one-time code is proportionate for an unusual payment. Mule risk without a
            # biometric still holds, because mule owners pass one-time codes too.
            v.bank_otp_fallback = True
            v.raise_to("STEP_UP_OWNER", f"This payment is unusual for this customer: {top[0].reason}. "
                       "They have no voice or iris set up, so confirm with the bank's usual one-time code.")

    if safe_limit is not None and sender.today_total > safe_limit:
        v.over_safe_limit = True
        v.raise_to("HOLD", f"{naira(sender.today_total)} sent today is above the daily limit the customer set for themselves "
                   f"({naira(safe_limit)}).")
    if v.decision == "ALLOW":
        v.reasons.append("Nothing suspicious about the sender, the receiver or the payment.")
    return v
