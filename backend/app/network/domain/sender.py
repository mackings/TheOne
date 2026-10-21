"""Sender-side risk: is this payment normal for this customer?

Mule detection protects against money landing in a bad account. This covers the other side: an
account taken over, a customer pressured into one huge payment to a normal-looking account, or a
customer forced to transfer under threat. Every rule compares the payment with the sender's own
history and explains itself in plain language.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.network.domain.engine import NAIRA, Signal, naira, noisy_or
from app.network.domain.entities import Account

HISTORY_DAYS = 90
PAYEE_HISTORY_DAYS = 180
NEW_DEVICE_HOURS = 72
BURST_MINUTES = 30
LOCATION_HISTORY = 30


@dataclass(frozen=True)
class SenderRules:
    utc_offset_hours: int
    review_cap_naira: int
    thin_file_naira: int
    new_payee_naira: int
    kyc_daily_limits: dict[int, int]


@dataclass
class SenderHistory:
    """What the bank knows about the sender before this payment."""

    payments: list[tuple[datetime, str | None, int]]
    """(time, payee account id, kobo) over PAYEE_HISTORY_DAYS; statement debits have no payee."""
    approved_recent: list[tuple[str, int]] = field(default_factory=list)
    """(payee, kobo) for payments approved in the last BURST_MINUTES."""
    usual_locations: list[tuple[float, float]] = field(default_factory=list)
    device: tuple[str, str] | None = None
    """(known | recent | new | first, masked id) for the device making this payment."""


@dataclass
class SenderAssessment:
    score: float
    signals: list[Signal]
    today_total: int
    context: dict = field(default_factory=dict)


def local_hour(dt: datetime, offset: int) -> int:
    return (dt + timedelta(hours=offset)).hour


def local_day_start(dt: datetime, offset: int) -> datetime:
    local = dt + timedelta(hours=offset)
    return local.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(hours=offset)


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))


def device_state(first_seen_here: datetime | None, other_devices_first_seen: list[datetime], at: datetime) -> str:
    """first: the account's first device; new: a new device on an account with an established one;
    recent: seen here only lately while an older device exists; known otherwise."""
    old_elsewhere = any(t <= at - timedelta(hours=NEW_DEVICE_HOURS) for t in other_devices_first_seen)
    if first_seen_here is None:
        return "new" if old_elsewhere else "first"
    if first_seen_here > at - timedelta(hours=NEW_DEVICE_HOURS) and old_elsewhere:
        return "recent"
    return "known"


def assess(src: Account, payee_id: str, amount: int, history: SenderHistory, rules: SenderRules, at: datetime,
           location: dict | None = None) -> SenderAssessment:
    off = rules.utc_offset_hours
    sigs: list[Signal] = []
    recent90 = [h for h in history.payments if h[0] >= at - timedelta(days=HISTORY_DAYS)]
    day0 = local_day_start(at, off)
    past = [h for h in recent90 if h[0] < day0]
    today_total = sum(a for ts, _, a in recent90 if ts >= day0) + amount

    cap = rules.review_cap_naira * NAIRA
    if amount >= cap:
        sigs.append(Signal("REVIEW_CAP", 0.95, f"{naira(amount)} is more than the {naira(cap)} that any single payment can send without a check",
                           {"cap": cap}))

    if len(past) >= 5:
        biggest = max(a for _, _, a in past)
        ratio = amount / max(biggest, 1)
        if ratio >= 3:
            w = 0.90 if ratio >= 100 else 0.60 if ratio >= 10 else 0.35
            sigs.append(Signal("AMOUNT_ANOMALY", w,
                               f"{naira(amount)} is {ratio:,.0f} times bigger than anything this customer sent in the last {HISTORY_DAYS} days (largest {naira(biggest)})",
                               {"ratio": round(ratio, 1), "largest_90d": biggest, "transfers_90d": len(past)}))
    elif amount >= rules.thin_file_naira * NAIRA:
        sigs.append(Signal("THIN_FILE_HIGH_VALUE", 0.45,
                           f"the customer has made only {len(past)} payment{'s' if len(past) != 1 else ''} before, and {naira(amount)} is a large amount",
                           {"transfers_90d": len(past)}))

    paid_before = any(d == payee_id for _, d, _ in history.payments)
    if not paid_before and amount >= rules.new_payee_naira * NAIRA:
        sigs.append(Signal("NEW_PAYEE_HIGH_VALUE", 0.35, f"first ever payment to this person, for {naira(amount)}",
                           {"threshold": rules.new_payee_naira * NAIRA}))

    by_day: dict[datetime, int] = {}
    for ts, _, a in past:
        k = local_day_start(ts, off)
        by_day[k] = by_day.get(k, 0) + a
    if len(by_day) >= 5:
        busiest = max(by_day.values())
        if today_total >= 3 * busiest and today_total >= 500_000 * NAIRA:
            sigs.append(Signal("DAILY_VELOCITY", 0.35,
                               f"{naira(today_total)} sent today, {today_total / max(busiest, 1):,.0f} times more than their busiest day before ({naira(busiest)})",
                               {"today_total": today_total, "busiest_day": busiest}))

    # The bank's own limit for this account once synced; until then the configured tier placeholder.
    if src.bank_daily_limit_kobo:
        if today_total > src.bank_daily_limit_kobo:
            sigs.append(Signal("KYC_TIER_LIMIT", 0.90,
                               f"{naira(today_total)} sent today is above the bank's daily limit for this account ({naira(src.bank_daily_limit_kobo)})",
                               {"limit": src.bank_daily_limit_kobo, "source": "bank"}))
    else:
        limit = rules.kyc_daily_limits.get(src.kyc_tier or 0)
        if limit is not None and today_total > limit * NAIRA:
            sigs.append(Signal("KYC_TIER_LIMIT", 0.90,
                               f"{naira(today_total)} sent today is above the daily limit for this type of account ({naira(limit * NAIRA)})",
                               {"tier": src.kyc_tier, "limit": limit * NAIRA, "source": "placeholder"}))

    # Executed transfers and approved decisions both count; one counted twice only errs toward caution.
    since = at - timedelta(minutes=BURST_MINUTES)
    burst = [(d, a) for ts, d, a in recent90 if ts >= since] + list(history.approved_recent)
    burst_total = sum(a for _, a in burst) + amount
    payees = {d for d, _ in burst} | {payee_id}
    if len(burst) >= 2 and burst_total >= 100_000 * NAIRA and len(payees) >= 2:
        w = 0.50 if len(burst) >= 4 else 0.35
        sigs.append(Signal("RAPID_DRAIN", w,
                           f"{len(burst) + 1} payments totalling {naira(burst_total)} to {len(payees)} accounts within {BURST_MINUTES} minutes",
                           {"payments_30min": len(burst) + 1, "total": burst_total, "payees": len(payees)}))

    hour = local_hour(at, off)
    if hour < 5 and amount >= 100_000 * NAIRA and not any(local_hour(ts, off) < 5 for ts, _, _ in past):
        sigs.append(Signal("NIGHT_HIGH_VALUE", 0.25, f"{naira(amount)} at {hour:02d}:00 local time; this customer has no night-time payments",
                           {"local_hour": hour}))

    ctx: dict = {"local_hour": hour}
    if history.device:
        state, masked = history.device
        ctx["device"] = {"state": state, "masked": masked}
        if state in {"new", "recent"} and amount >= 100_000 * NAIRA:
            sigs.append(Signal("NEW_DEVICE_HIGH_VALUE", 0.40,
                               f"{'first' if state == 'new' else 'recent'} use of device {masked} for {naira(amount)}",
                               {"device_state": state}))

    if location and "lat" in location and "lon" in location:
        here = (float(location["lat"]), float(location["lon"]))
        ctx["location"] = {"lat": round(here[0], 4), "lon": round(here[1], 4)}
        pts = history.usual_locations
        if len(pts) >= 3 and amount >= 100_000 * NAIRA:
            lat = sorted(p[0] for p in pts)[len(pts) // 2]
            lon = sorted(p[1] for p in pts)[len(pts) // 2]
            km = haversine_km(here, (lat, lon))
            if km > 50:
                sigs.append(Signal("LOCATION_ANOMALY", 0.30, f"{km:,.0f} km from where this customer usually pays",
                                   {"distance_km": round(km)}))

    return SenderAssessment(noisy_or(sigs) if sigs else 0.0, sigs, today_total, ctx)
