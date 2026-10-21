"""Step 2: the explainable mule rules. Each returns a Signal with a plain reason and evidence, or nothing."""
from __future__ import annotations

import bisect
from collections import defaultdict, deque
from datetime import datetime, timedelta

from app.network.domain.engine.types import AccountView, CASH_CHANNELS, DAY, DAY_CHANNELS, Edge, NAIRA, Signal, Snapshot, naira

def _is_cash_point(a: AccountView) -> bool:
    return a.is_merchant and (a.account_no == "ATM" or a.name.lower().startswith(("pos agent", "atm", "agent")))


def sig_fan_in(acc: AccountView, ins: list[Edge]) -> Signal | None:
    """Many unrelated senders paying one account within 72 hours."""
    first: dict[str, datetime] = {}
    for e in ins:
        first.setdefault(e.src, e.ts)
    times = sorted(first.values())
    best, j, best_end = 0, 0, None
    for i, t in enumerate(times):
        while times[j] < t - timedelta(hours=72):
            j += 1
        if i - j + 1 > best:
            best, best_end = i - j + 1, t
    if best < 6:
        return None
    w = 0.40 if best >= 12 else 0.30
    if acc.is_merchant:
        w *= 0.3
    return Signal("FAN_IN", w, f"{best} new senders paid this account within 72 hours",
                  {"distinct_senders_72h": best, "window_end": best_end.isoformat() if best_end else None})


def sig_pass_through(ins: list[Edge], outs: list[Edge], fast: timedelta) -> Signal | None:
    """Money arriving and leaving again within the fast window (FIFO matching)."""
    total_in = sum(e.amount for e in ins)
    senders = {e.src for e in ins}
    if total_in < 100_000 * NAIRA or len(senders) < 3 or not outs:
        return None
    events = sorted([(e.ts, 0, e) for e in ins] + [(e.ts, 1, e) for e in outs], key=lambda x: (x[0], x[1]))
    queue: deque[list] = deque()
    fast_out = 0
    delays: list[float] = []
    by_day = any(e.channel in DAY_CHANNELS for e in outs)
    for ts, kind, e in events:
        if kind == 0:
            queue.append([ts, e.amount])
            continue
        win = DAY if e.channel in DAY_CHANNELS else fast
        while queue and ts - queue[0][0] > win:
            queue.popleft()
        amt = e.amount
        while amt > 0 and queue:
            take = min(amt, queue[0][1])
            delays.append((ts - queue[0][0]).total_seconds() / 60)
            queue[0][1] -= take
            amt -= take
            fast_out += take
            if queue[0][1] == 0:
                queue.popleft()
    ratio = fast_out / total_in
    if ratio < 0.7:
        return None
    delays.sort()
    median = delays[len(delays) // 2] if delays else None
    w = 0.55 if ratio >= 0.9 else 0.45
    return Signal("PASS_THROUGH", w,
                  f"{ratio:.0%} of {naira(total_in)} received left again "
                  + ("the same or next day" if by_day else f"within {int(fast.total_seconds() // 60)} minutes"),
                  {"ratio": round(ratio, 3), "inbound": total_in, "fast_outbound": fast_out,
                   "median_delay_min": round(median, 1) if median is not None else None})


def sig_split_round(ins: list[Edge], outs: list[Edge]) -> Signal | None:
    """A burst of round-amount transfers to several recipients right after a credit."""
    rounds = [e for e in outs if e.amount % (5_000 * NAIRA) == 0 and e.amount >= 20_000 * NAIRA and e.channel not in CASH_CHANNELS]
    in_times = [e.ts for e in ins]
    j = 0
    for i, e in enumerate(rounds):
        day = e.channel in DAY_CHANNELS
        while rounds[j].ts < e.ts - (DAY if day else timedelta(minutes=30)):
            j += 1
        burst = rounds[j : i + 1]
        if len(burst) >= 3 and len({b.dst for b in burst}) >= 2:
            k = bisect.bisect_right(in_times, burst[0].ts)
            if k and burst[0].ts - in_times[k - 1] <= (DAY if day else timedelta(hours=2)):
                total = sum(b.amount for b in burst)
                return Signal("SPLIT_ROUND", 0.25,
                              f"{len(burst)} round-amount transfers totalling {naira(total)} to {len({b.dst for b in burst})} accounts "
                              + ("within a day of a credit" if day else "within 30 minutes of a credit"),
                              {"count": len(burst), "total": total, "refs": [b.ref for b in burst][:6]})
    return None


def sig_cash_out(ins: list[Edge], outs: list[Edge]) -> Signal | None:
    """Most outflow withdrawn as cash (POS, ATM, agent) soon after money arrives."""
    total_out = sum(e.amount for e in outs)
    cash = [e for e in outs if e.channel in CASH_CHANNELS]
    cash_total = sum(e.amount for e in cash)
    if total_out < 100_000 * NAIRA or cash_total / total_out < 0.6 or not ins:
        return None
    in_times = [e.ts for e in ins]
    delays = []
    for e in cash:
        k = bisect.bisect_right(in_times, e.ts)
        if k:
            delays.append((e.ts - in_times[k - 1]).total_seconds() / 3600)
    if not delays:
        return None
    delays.sort()
    median = delays[len(delays) // 2]
    if median > 24:
        return None
    return Signal("CASH_OUT", 0.30,
                  f"{cash_total / total_out:.0%} of outflow withdrawn as cash, median {median:.1f} h after money arrived",
                  {"cash_share": round(cash_total / total_out, 3), "cash_total": cash_total, "median_delay_h": round(median, 2)})


def sig_new_account(acc: AccountView, ins: list[Edge], outs: list[Edge], at: datetime) -> list[Signal]:
    out: list[Signal] = []
    through = sum(e.amount for e in ins) + sum(e.amount for e in outs)
    if acc.opened_at and (at - acc.opened_at) <= timedelta(days=45) and through >= 1_000_000 * NAIRA:
        age = (at - acc.opened_at).days
        out.append(Signal("NEW_ACCOUNT_VELOCITY", 0.30, f"account opened {age} days ago has moved {naira(through)}",
                          {"age_days": age, "throughput": through}))
    if acc.kyc_tier == 1 and through >= 500_000 * NAIRA:
        out.append(Signal("LOW_KYC_HIGH_VALUE", 0.15, f"tier-1 KYC account has moved {naira(through)}",
                          {"kyc_tier": 1, "throughput": through}))
    return out


def sig_dormant(acc_id: str, ins: list[Edge], outs: list[Edge], prior_last: dict[str, datetime]) -> Signal | None:
    last = prior_last.get(acc_id)
    events = [e.ts for e in ins] + [e.ts for e in outs]
    if not last or not events:
        return None
    first = min(events)
    gap = (first - last).days
    through = sum(e.amount for e in ins) + sum(e.amount for e in outs)
    if gap >= 90 and through >= 500_000 * NAIRA:
        return Signal("DORMANT_REACTIVATED", 0.30, f"dormant for {gap} days, then moved {naira(through)}",
                      {"dormant_days": gap, "throughput": through})
    return None


def sig_shared(acc_id: str, snap: Snapshot) -> Signal | None:
    others: dict[str, set[str]] = defaultdict(set)
    for ident in snap.acct_idents.get(acc_id, ()):
        members = snap.ident_members.get(ident, set()) - {acc_id}
        if members:
            others[ident] |= members
    distinct = set().union(*others.values()) if others else set()
    n = len(distinct)
    if n == 0:
        return None
    w = 0.40 if n >= 4 else 0.25 if n >= 2 else 0.10
    shared = [{"kind": snap.ident_info.get(i, ("?", "?"))[0], "masked": snap.ident_info.get(i, ("?", "?"))[1],
               "accounts": len(v)} for i, v in others.items()]
    return Signal("SHARED_IDENTIFIER", w, f"shares phone, device or BVN with {n} other account{'s' if n > 1 else ''}",
                  {"other_accounts": n, "identifiers": shared})


def sig_device_farm(acc_id: str, snap: Snapshot) -> Signal | None:
    """One device or phone operating several recently opened accounts (rented or bought accounts).
    Agent-assisted onboarding on an agent's phone can look similar, so the reason says so."""
    best = None
    for ident in snap.acct_idents.get(acc_id, ()):
        kind, masked = snap.ident_info.get(ident, ("?", "?"))
        if kind not in {"device", "phone"}:
            continue
        members = snap.ident_members.get(ident, set())
        if len(members) < 3:
            continue
        young = [x for x in members if (v := snap.accounts.get(x)) and v.opened_at and (snap.at - v.opened_at).days <= 60]
        if len(young) >= 3 and len(young) * 2 >= len(members) and (best is None or len(young) > best[0]):
            best = (len(young), len(members), kind, masked)
    if not best:
        return None
    young, total, kind, masked = best
    return Signal("DEVICE_FARM", 0.35,
                  f"one {kind} ({masked}) operates {total} accounts, {young} of them opened in the last 60 days "
                  "(check for agent-assisted onboarding before acting)",
                  {"kind": kind, "masked": masked, "accounts": total, "recent_accounts": young})


def sig_reports(kinds: list[str]) -> list[Signal]:
    out: list[Signal] = []
    complaints = kinds.count("victim_complaint")
    if complaints:
        out.append(Signal("VICTIM_COMPLAINT", 0.80 if complaints >= 2 else 0.60,
                          f"{complaints} fraud complaint{'s name' if complaints > 1 else ' names'} this account as the beneficiary",
                          {"complaints": complaints}))
    if "bvn_watchlist" in kinds:
        out.append(Signal("BVN_WATCHLIST", 0.70, "the account holder's BVN is on the industry fraud watch-list (NIBSS)", {}))
    if "confirmed_mule" in kinds:
        out.append(Signal("CONFIRMED_MULE", 0.95, "previously confirmed as a mule by an analyst or another institution", {}))
    return out
