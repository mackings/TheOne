"""Mule checks on one parsed statement, and a replay of the payment checks over its debits."""
from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date, timedelta

from app.network.domain.engine import naira
from app.network.domain.statements.parser import BUSINESS, NAIRA, Parsed, parse

# Same day or the next day.
FAST_DAYS = 1
FLAG, HOLD, STEP_UP = 0.60, 0.85, 0.50


def _noisy_or(ws: list[float]) -> float:
    x = 1.0
    for w in ws:
        x *= 1 - w
    return round(1 - x, 4)


def _band(score: float) -> str:
    return "High" if score >= HOLD else "Elevated" if score >= FLAG else "Watch" if score >= 0.35 else "Low"


def _check(code: str, title: str, fired: bool, weight: float, detail: str) -> dict:
    return {"code": code, "title": title, "fired": fired, "weight": weight if fired else 0.0, "detail": detail}


def mule_checks(p: Parsed) -> list[dict]:
    flow = [x for x in p.lines if x.kind not in ("fee", "reversal")]
    ins = [x for x in flow if x.direction == "in"]
    outs = [x for x in flow if x.direction == "out"]
    total_in = sum(x.amount for x in ins)
    checks: list[dict] = []

    # Many unrelated payers within three days.
    best, best_day = 0, None
    others = [x for x in ins if not x.self_transfer]
    for x in others:
        window = {y.party.upper() for y in others if x.posted - timedelta(days=2) <= y.posted <= x.posted}
        if len(window) > best:
            best, best_day = len(window), x.posted
    checks.append(_check("FAN_IN", "Many unrelated people paid in", best >= 6, 0.40 if best >= 12 else 0.30,
                         f"At most {best} different payer{'s' if best != 1 else ''} in any 3 days"
                         + (f" (around {best_day.day} {best_day:%b})" if best_day and best >= 6 else "") + "."))

    # Money passing straight through: what left within a day of each credit, capped at the credit.
    fast = 0
    for c in ins:
        later = sum(o.amount for o in outs if o.i > c.i and (o.posted - c.posted).days <= FAST_DAYS)
        fast += min(c.amount, later)
    ratio = fast / total_in if total_in else 0.0
    checks.append(_check("PASS_THROUGH", "Money moved on as soon as it arrived", ratio >= 0.7 and total_in >= 100_000 * NAIRA,
                         0.55 if ratio >= 0.9 else 0.45,
                         f"{ratio:.0%} of the {naira(total_in)} received left again the same or next day."))

    months = max(1.0, ((p.lines[-1].posted - p.lines[0].posted).days + 1) / 30) if p.lines else 1.0
    monthly_in = total_in / months
    end_of_day: dict[date, int] = {}
    for x in p.lines:
        if x.balance is not None:
            end_of_day[x.posted] = x.balance
    median_bal = statistics.median(end_of_day.values()) if end_of_day else 0
    low = bool(end_of_day) and monthly_in >= 200_000 * NAIRA and median_bal < 0.1 * monthly_in
    checks.append(_check("LOW_BALANCE", "Account keeps almost nothing", low, 0.30,
                         f"Typical end-of-day balance {naira(round(median_bal))} against about {naira(round(monthly_in))} paid in per month."))

    cash_fast = 0
    for c in ins:
        later = sum(o.amount for o in outs if o.kind == "cash" and o.i > c.i and (o.posted - c.posted).days <= FAST_DAYS)
        cash_fast += min(c.amount, later)
    cash_total = sum(o.amount for o in outs if o.kind == "cash")
    cash_ratio = cash_fast / total_in if total_in else 0.0
    checks.append(_check("CASH_OUT", "Money withdrawn as cash quickly", cash_ratio >= 0.5 and cash_fast >= 100_000 * NAIRA, 0.30,
                         f"{naira(cash_total)} went to ATMs or POS agents in total; {cash_ratio:.0%} of money received was "
                         "withdrawn this way within a day."))

    split_hit = None
    for c in ins:
        if c.amount < 100_000 * NAIRA:
            continue
        burst = [o for o in outs if o.i > c.i and (o.posted - c.posted).days <= FAST_DAYS and not o.self_transfer
                 and o.amount % (5_000 * NAIRA) == 0 and o.amount >= 20_000 * NAIRA]
        if len(burst) >= 3 and len({o.party.upper() for o in burst}) >= 2 and sum(o.amount for o in burst) >= 0.5 * c.amount:
            split_hit = (c, burst)
            break
    checks.append(_check("SPLIT_ROUND", "Credits split into round amounts", split_hit is not None, 0.25,
                         (f"{naira(split_hit[0].amount)} on {split_hit[0].posted.day} {split_hit[0].posted:%b} was followed by {len(split_hit[1])} round "
                          f"payments to {len({o.party.upper() for o in split_hit[1]})} people.") if split_hit
                         else "No large credit was split into round payments to several people."))

    gap_hit = None
    for a, b in zip(flow, flow[1:]):
        gap = (b.posted - a.posted).days
        if gap >= 90:
            moved = sum(x.amount for x in flow if b.posted <= x.posted <= b.posted + timedelta(days=30))
            if moved >= 500_000 * NAIRA:
                gap_hit = (gap, b.posted, moved)
    checks.append(_check("DORMANT", "Long-unused account suddenly busy", gap_hit is not None, 0.30,
                         (f"No activity for {gap_hit[0]} days, then {naira(gap_hit[2])} moved from {gap_hit[1].day} {gap_hit[1]:%b}.") if gap_hit
                         else "The account was in regular use; no long quiet spell followed by a burst."))
    return checks


def sender_replay(p: Parsed) -> list[dict]:
    """Run the payment checks over each outgoing payment, using only the history before it."""
    pays = [x for x in p.lines if x.direction == "out" and x.kind in ("transfer", "cash", "card")]
    out: list[dict] = []
    for n, x in enumerate(pays):
        past = [y for y in pays[:n] if y.posted < x.posted and (x.posted - y.posted).days <= 90]
        sigs: list[tuple[float, str]] = []
        if len(past) >= 5:
            biggest = max(y.amount for y in past)
            r = x.amount / max(biggest, 1)
            if r >= 3:
                sigs.append((0.90 if r >= 100 else 0.60 if r >= 10 else 0.35,
                             f"{r:,.0f}× the largest payment in the previous 90 days ({naira(biggest)})"))
        seen = any(y.party.upper() == x.party.upper() for y in pays[:n] if (x.posted - y.posted).days <= 180)
        if not seen and x.amount >= 200_000 * NAIRA:
            sigs.append((0.35, "first payment to this person, for a large amount"))
        by_day: dict[date, int] = defaultdict(int)
        for y in past:
            by_day[y.posted] += y.amount
        today = sum(y.amount for y in pays[: n + 1] if y.posted == x.posted)
        if len(by_day) >= 5 and today >= 3 * max(by_day.values()) and today >= 500_000 * NAIRA:
            sigs.append((0.35, f"{naira(today)} sent that day, far above the busiest earlier day"))
        if not sigs:
            continue
        score = _noisy_or([w for w, _ in sigs])
        outcome = "Hold" if score >= HOLD else "Confirm it is you" if score >= STEP_UP else "Allowed, noted"
        out.append({"date": x.posted.isoformat(), "to": x.party or x.desc[:40], "amount": x.amount, "score": score,
                    "outcome": outcome, "reasons": [r for _, r in sigs], "self": x.self_transfer})
    return out


def check(text: str) -> dict:
    p = parse(text)
    if not p.lines:
        raise ValueError("no transactions could be read from this statement")
    flow = [x for x in p.lines if x.kind not in ("fee", "reversal")]
    ins = [x for x in flow if x.direction == "in"]
    outs = [x for x in flow if x.direction == "out"]
    fees = sum(x.amount for x in p.lines if x.kind == "fee")
    total_in, total_out = sum(x.amount for x in ins), sum(x.amount for x in outs)
    self_out = sum(x.amount for x in outs if x.self_transfer)

    bals = [x.balance for x in p.lines if x.balance is not None]
    checks = mule_checks(p)
    score = _noisy_or([c["weight"] for c in checks if c["fired"]])
    replay = sender_replay(p)

    payees: dict[str, dict] = {}
    for x in outs:
        if x.self_transfer or x.kind in ("bill", "card"):
            continue
        k = x.party.upper() or x.desc[:40].upper()
        e = payees.setdefault(k, {"name": x.party or x.desc[:40], "count": 0, "total": 0, "bank": x.tag})
        e["count"] += 1
        e["total"] += x.amount
    payers: dict[str, dict] = {}
    for x in ins:
        k = x.party.upper() or x.desc[:40].upper()
        e = payers.setdefault(k, {"name": x.party or x.desc[:40], "count": 0, "total": 0, "self": x.self_transfer})
        e["count"] += 1
        e["total"] += x.amount

    everyday = {
        "bills_and_data": sum(1 for x in outs if x.kind == "bill"),
        "businesses_paid": len({x.party.upper() for x in outs if BUSINESS.search(x.party)}),
        "people_paid": len({x.party.upper() for x in outs if x.kind in ("transfer", "cash") and not x.self_transfer and not BUSINESS.search(x.party)}),
        "card_funding": sum(1 for x in outs if x.kind == "card"),
    }
    fired = [c for c in checks if c["fired"]]
    questioned = [r for r in replay if r["outcome"] != "Allowed, noted"]
    first, last = p.lines[0].posted, p.lines[-1].posted
    summary = [
        f"{len(flow)} transactions from {first.day} {first:%b %Y} to {last.day} {last:%b %Y}: {naira(total_in)} in and {naira(total_out)} out, "
        f"plus {naira(fees)} in bank charges.",
        (f"{round(100 * self_out / total_out) if total_out else 0}% of the money going out went to accounts in the holder's own name."),
        (f"The balance stayed between {naira(min(bals))} and {naira(max(bals))}." if bals else "The statement shows no running balance."),
        ("None of the mule checks fired." if not fired else
         f"{len(fired)} mule check{'s' if len(fired) > 1 else ''} fired: " + "; ".join(c["title"].lower() for c in fired) + "."),
        (f"The payment checks would have asked the owner to confirm {len(questioned)} payment{'s' if len(questioned) != 1 else ''}."
         if questioned else "The payment checks would not have stopped any payment."),
    ]
    return {
        "account": {"holder": p.holder, "account_no": p.account_no, "period_stated": p.period,
                    "opening": p.opening, "closing": p.closing},
        "coverage": {"first": first.isoformat(), "last": last.isoformat(), "lines": len(p.lines), "skipped": p.skipped,
                     "truncated": p.truncated, "layout": p.layout,
                     "account_numbers_found": sum(1 for x in p.lines if x.nuban)},
        "totals": {"in": total_in, "out": total_out, "fees": fees, "self_out": self_out, "credits": len(ins), "debits": len(outs),
                   "min_balance": min(bals) if bals else None, "max_balance": max(bals) if bals else None},
        "mule": {"score": score, "band": _band(score), "flagged": score >= FLAG, "checks": checks},
        "payments": replay,
        "top_payees": sorted(payees.values(), key=lambda e: -e["total"])[:8],
        "payers": sorted(payers.values(), key=lambda e: -e["total"])[:8],
        "everyday": everyday,
        "summary": summary,
        "limits": ["A statement shows one account. It cannot show the ring around it, shared phones or devices, or the "
                   "other side's history.", "Statements have dates but no times, so 'fast' means the same or next day."],
    }
