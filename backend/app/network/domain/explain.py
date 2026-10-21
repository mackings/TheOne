"""Plain-language explanations of findings, roles and ring stories, for readers who are not fraud analysts."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.network.domain.engine import naira

WAT = ZoneInfo("Africa/Lagos")

PLAIN: dict[str, tuple[str, str]] = {
    "FAN_IN": ("Many unrelated people paid the same account",
               "Ordinary accounts are paid by a few familiar people. A mule account suddenly receives money from many "
               "strangers in a short time, which is what happens when several fraud victims are told to pay into it."),
    "PASS_THROUGH": ("Money was moved on almost as soon as it arrived",
                     "The account kept almost nothing. Most of what came in left again within minutes or hours, so it acts "
                     "as a pipe for someone else's money, not as a real customer's account."),
    "SPLIT_ROUND": ("Money was split into round amounts",
                    "Large credits were quickly broken into round sums and sent to several accounts, to spread money "
                    "across mules and stay under transfer limits."),
    "CASH_OUT": ("Money was withdrawn as cash quickly",
                 "Funds were taken out through ATMs or POS agents soon after arriving. Cash cannot be recalled."),
    "NEW_ACCOUNT_VELOCITY": ("A new account handled large sums",
                             "The account is only days or weeks old but has already moved a lot of money. Mule accounts are "
                             "often opened just for one scheme."),
    "LOW_KYC_HIGH_VALUE": ("Basic-level account moving large sums",
                           "The account was opened with minimal identity checks (tier 1) yet handles amounts typical of a "
                           "fully verified customer."),
    "DORMANT_REACTIVATED": ("A long-unused account suddenly became busy",
                            "The account sat unused for months, then started moving money. Dormant accounts are sometimes "
                            "sold or taken over for fraud."),
    "DEVICE_FARM": ("One phone runs several new accounts",
                    "The same device logs into several recently opened accounts, which usually means one person controls them."),
    "SHARED_IDENTIFIER": ("Accounts share a phone number, device or BVN",
                          "Accounts that look unrelated are linked by the same phone, device or BVN, pointing to one person "
                          "or group operating them together."),
    "VICTIM_COMPLAINT": ("Fraud victims named this account",
                         "Customers reported they were defrauded and gave this account as the one they paid. This is direct "
                         "evidence, not a pattern."),
    "BVN_WATCHLIST": ("The account holder is on the BVN watch-list",
                      "NIBSS keeps an industry watch-list of BVNs belonging to people confirmed in fraud. This holder's BVN is on it."),
    "CONFIRMED_MULE": ("Already confirmed as a mule",
                       "An analyst at this bank or another institution has already confirmed this account as a mule."),
    "FAST_FROM_FLAGGED": ("Received money straight from a flagged account",
                          "Money arrived from an account already flagged as a mule and was moved again shortly after. It is "
                          "the next link in the chain."),
    "LIVE_PASS_THROUGH": ("Draining fresh credits right now",
                          "Money that just arrived is already leaving, so acting quickly can still stop funds leaving."),
    "STATUS_CONFIRMED": ("Confirmed by an analyst", "A member of the fraud team confirmed this account as a mule."),
    "STATUS_CLEARED": ("Cleared by an analyst", "A member of the fraud team reviewed this account and found it legitimate."),
}

ROLE = {
    "collector": ("Collector", "First account to receive the victims' money."),
    "layer": ("Layering", "Receives money from collectors and passes it on, to hide where it came from."),
    "cash_out": ("Cash-out", "Last account in the chain. Withdraws the money as cash or sends it out."),
    "victim": ("Possible victim", "Paid money into the ring. Treated as a victim, never as a suspect."),
    "source": ("Source", "Sent money into the ring."),
    "cash_point": ("Cash point", "ATM or POS agent where money was withdrawn."),
    "exit": ("Exit", "Account outside the ring where money finally went."),
    "traced": ("Traced at another bank", "Account at another bank that received the money next, found through a NIBSS trace."),
}

ACTION = {"watchlist_24h": "Placed on 24-hour watchlist", "confirm": "Ring confirmed as mule accounts",
          "dismiss": "Ring dismissed as legitimate", "release": "Released from watchlist"}

STATUS = {"open": "Open, under investigation", "confirmed": "Confirmed mule ring", "dismissed": "Dismissed as legitimate",
          "stale": "No longer active"}


def strength(w: float) -> str:
    return "Strong" if w >= 0.5 else "Moderate" if w >= 0.3 else "Supporting"


def _lagos(iso: str) -> datetime:
    t = datetime.fromisoformat(iso)
    if t.tzinfo is None:
        t = t.replace(tzinfo=ZoneInfo("UTC"))
    return t.astimezone(WAT)


def day_label(iso: str | None) -> str:
    """Nigerian style, day first: 6 Oct 2026."""
    if not iso:
        return ""
    t = _lagos(iso)
    return f"{t.day} {t:%b %Y}"


def when_label(iso: str | None) -> str:
    """Nigerian style in Lagos time: 6 Oct 2026, 12:09 pm."""
    if not iso:
        return ""
    t = _lagos(iso)
    return f"{t.day} {t:%b %Y}, {(t.hour % 12) or 12}:{t:%M} {'AM' if t.hour < 12 else 'PM'}"


def _dur(seconds: float) -> str:
    m = max(1, round(seconds / 60))
    if m < 90:
        return f"{m} minute{'s' if m > 1 else ''}"
    h = round(m / 60)
    if h < 48:
        return f"{h} hour{'s' if h > 1 else ''}"
    d = round(h / 24)
    return f"{d} day{'s' if d > 1 else ''}"


def _names(ids: list[str], nodes: dict[str, dict]) -> str:
    names = [nodes[i]["name"] or nodes[i]["account_no"] for i in ids]
    if len(names) <= 2:
        return " and ".join(names)
    rest = len(names) - 2
    return f"{', '.join(names[:2])} and {rest} other{'s' if rest > 1 else ''}"


def story(g: dict) -> list[tuple[str, str]]:
    sm, nodes = g["summary"], {n["id"]: n for n in g["nodes"]}
    in_ring = lambda i: i in sm["roles"]  # noqa: E731
    role = lambda i: nodes.get(i, {}).get("role")  # noqa: E731
    steps: list[tuple[str, str]] = []
    ins = [e for e in g["edges"] if role(e["src"]) in ("victim", "source") and in_ring(e["dst"])]
    receivers = sorted({e["dst"] for e in ins})
    first_in = min((e["first"] for e in ins), default=None)
    last_in = max((e["last"] for e in ins), default=None)
    steps.append(("Money came in from many people",
                  f"{sm['possible_victims']} people sent {naira(sm['victim_inflow'])} to {len(receivers)} "
                  f"account{'s' if len(receivers) != 1 else ''} ({_names(receivers, nodes)})"
                  + (f" between {when_label(first_in)} and {when_label(last_in)}" if first_in else "")
                  + ". Most had never paid these accounts before, so they are treated as possible fraud victims."))
    onward = [e for e in g["edges"] if in_ring(e["src"]) and in_ring(e["dst"])]
    if onward:
        passed = sum(e["amount"] for e in onward if e["src"] in receivers)
        layers = sorted({e["dst"] for e in onward} - set(receivers))
        first_out = min((e["first"] for e in g["edges"] if in_ring(e["src"])), default=None)
        gap = (datetime.fromisoformat(first_out) - datetime.fromisoformat(first_in)).total_seconds() if first_in and first_out else None
        steps.append(("It was passed along a chain of accounts",
                      (f"Within {_dur(gap)} of the first payment, " if gap is not None and gap >= 0 else "")
                      + f"{naira(passed)} was moved on to {len(layers) or 'other'} account{'s' if len(layers) != 1 else ''}"
                      + (f" ({_names(layers, nodes)})" if layers else "")
                      + (". That is more than the victims paid in, so these accounts were also moving money from other sources"
                         if passed > sm["victim_inflow"] else "")
                      + ". Passing money through several accounts makes it harder to trace and recover."))
    points = {e["dst"] for e in g["edges"] if in_ring(e["src"]) and role(e["dst"]) == "cash_point"}
    if points or sm["cash_out_total"]:
        atm = sum(1 for p in points if "atm" in nodes[p]["name"].lower())
        pos = len(points) - atm
        via = " and ".join(x for x in [f"{atm} ATM{'s' if atm > 1 else ''}" if atm else "",
                                       f"{pos} POS agent{'s' if pos > 1 else ''}" if pos else ""] if x)
        share = round(100 * sm["cash_out_total"] / sm["victim_inflow"]) if sm["victim_inflow"] else None
        steps.append(("Most of it was withdrawn as cash",
                      f"{naira(sm['cash_out_total'])}" + (f", about {min(share, 100)}% of what the victims paid," if share is not None else "")
                      + " left as cash" + (f" through {via}" if via else "")
                      + ". Cash cannot be recalled, which is why mule rings withdraw quickly."))
    traced = [n for n in g["nodes"] if n["role"] == "traced"]
    if traced:
        exits = [n for n in g["nodes"] if n["role"] == "exit"]
        sent_out = sum(e["amount"] for e in g["edges"] if in_ring(e["src"]) and role(e["dst"]) == "exit")
        moved_on = sum(e["amount"] for e in g["edges"] if role(e["src"]) == "exit")
        banks = len({n["bank_code"] for n in traced})
        steps.append(("It was followed into other banks",
                      f"{naira(sent_out)} was sent to {len(exits)} account{'s' if len(exits) != 1 else ''} at other banks. Trace requests "
                      f"through NIBSS show {naira(moved_on)} of it moved on again, reaching {len(traced)} more account"
                      f"{'s' if len(traced) != 1 else ''} at {banks} bank{'s' if banks != 1 else ''}. Those banks can be asked to hold "
                      "what is left."))
    if g["identifier_links"]:
        linked = {a for x in g["identifier_links"] for a in x["accounts"]}
        word = {"bvn": "BVN", "phone": "phone number", "device": "device"}
        kinds = " or ".join(sorted({word.get(x["kind"], x["kind"]) for x in g["identifier_links"]}))
        steps.append(("The accounts are controlled together",
                      f"{'All' if len(linked) == sm['size'] else len(linked)} of the {sm['size']} accounts use the same {kinds}. Accounts that look unrelated but "
                      "share these details are usually run by one person or group."))
    complained = [n["id"] for n in g["nodes"] if in_ring(n["id"]) and any(s["code"] == "VICTIM_COMPLAINT" for s in n["signals"])]
    if complained:
        steps.append(("Victims have already complained",
                      f"Fraud reports name {_names(complained, nodes)} as the account{'s' if len(complained) > 1 else ''} "
                      "they were told to pay."))
    return steps


