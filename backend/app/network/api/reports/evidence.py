"""Printable evidence pack for one ring. Branch managers, legal teams and the police read it: the
ring's story in numbered steps, each finding in plain words, then the supporting facts."""
from __future__ import annotations

import html
from datetime import datetime

from app.network.domain.engine import naira
from app.network.domain.explain import ACTION, PLAIN, ROLE, STATUS, day_label, story, strength, when_label

CSS = """
:root{--brand:#d71920;--brand-soft:#fdecec;--ink:#1f1f1f;--ink2:#4a4a4a;--muted:#6e6e6e;--line:#e6e6e6;--soft:#f7f7f7;
--strong:#a51c1c;--strong-bg:#fbeaea;--mod:#9a4a26;--mod-bg:#fdeee7;--sup:#555;--sup-bg:#efefef;--good:#0c7a0c;--good-bg:#e8f6e8}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:#efefef;color:var(--ink);font:15px/1.55 Inter,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.page{max-width:920px;margin:0 auto;background:#fff;min-height:100vh}
.wrap{padding:0 clamp(16px,4vw,40px)}
header{background:var(--brand);color:#fff;padding:22px 0 20px}
header .kicker{font-size:12px;letter-spacing:.08em;text-transform:uppercase;opacity:.85;font-weight:600}
header h1{margin:4px 0 6px;font-size:clamp(22px,4.5vw,30px);line-height:1.15}
header .meta{font-size:13px;opacity:.92;display:flex;flex-wrap:wrap;gap:4px 14px}
.toolbar{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:10px;padding:12px 0;border-bottom:1px solid var(--line);font-size:13px;color:var(--muted)}
.btn{background:var(--brand);color:#fff;border:0;border-radius:6px;padding:9px 14px;font:600 13px Inter,system-ui,sans-serif;cursor:pointer}
section{padding:26px 0;border-bottom:1px solid var(--line)}
h2{font-size:18px;margin:0 0 4px}.lead{color:var(--muted);font-size:13px;margin:0 0 16px}
.verdict{border-left:4px solid var(--brand);background:var(--brand-soft);border-radius:6px;padding:14px 16px;margin-top:20px}
.verdict b{display:block;font-size:16px;margin-bottom:2px}.verdict p{margin:6px 0 0;font-size:14px}
.verdict.good{border-color:var(--good);background:var(--good-bg)}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:1px;background:var(--line);border:1px solid var(--line);border-radius:8px;overflow:hidden;margin-top:18px}
.tiles div{background:#fff;padding:14px 16px}.tiles span{display:block;font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
.tiles b{display:block;font-size:clamp(18px,3.4vw,22px);margin-top:2px;font-variant-numeric:tabular-nums}
ol.story{list-style:none;margin:0;padding:0;display:grid;gap:14px}
ol.story li{display:grid;grid-template-columns:28px 1fr;gap:12px}
ol.story .n{width:28px;height:28px;border-radius:50%;background:var(--brand);color:#fff;font:700 13px/28px Inter,system-ui,sans-serif;text-align:center}
ol.story b{display:block}ol.story p{margin:2px 0 0;color:var(--ink2);font-size:14px}ol.story small{display:block;color:var(--muted);font-size:13px;margin-top:2px}
.pill{display:inline-block;font-size:11.5px;font-weight:600;border-radius:999px;padding:2px 9px;white-space:nowrap;vertical-align:middle}
.Strong{background:var(--strong-bg);color:var(--strong)}.Moderate{background:var(--mod-bg);color:var(--mod)}.Supporting{background:var(--sup-bg);color:var(--sup)}
.list{border:1px solid var(--line);border-radius:8px;overflow:hidden}
.row{padding:12px 16px;border-top:1px solid var(--line)}.row:first-child{border-top:0}
.row .top{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:6px 12px}
.row .title{font-weight:600}.row .sub{color:var(--muted);font-size:13px;margin-top:2px}
details{margin-top:6px}summary{cursor:pointer;color:var(--brand);font-size:13px;font-weight:600;list-style:none}
summary::-webkit-details-marker{display:none}summary:before{content:"+ "}details[open] summary:before{content:"– "}
details .body{margin-top:8px;font-size:13.5px;color:var(--ink2)}details .body ul{margin:6px 0 0;padding-left:18px}details .body li{margin:3px 0}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:12px}
.card{border:1px solid var(--line);border-radius:8px;padding:14px 16px}
.card .name{font-weight:600}.card .acct{font:12.5px ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--muted)}
.card dl{display:grid;grid-template-columns:auto 1fr;gap:4px 12px;margin:10px 0 0;font-size:13px}.card dt{color:var(--muted)}.card dd{margin:0}
.stage{margin-top:18px}.stage:first-of-type{margin-top:0}
.stage h3{font-size:15px;margin:0}.stage .sum{color:var(--muted);font-size:13px;margin:2px 0 8px}
.flow{display:flex;flex-wrap:wrap;justify-content:space-between;gap:2px 12px}
.flow .who{min-width:0;overflow-wrap:anywhere}.flow .amt{font-weight:600;font-variant-numeric:tabular-nums;white-space:nowrap}
.arrow{color:var(--muted);padding:0 4px}.note{background:#fff8e6;border-left:4px solid #e5a50a;border-radius:6px;padding:12px 16px;font-size:13px}
dl.gloss{display:grid;grid-template-columns:minmax(120px,170px) 1fr;gap:6px 16px;font-size:13.5px;margin:0}dl.gloss dt{font-weight:600}dl.gloss dd{margin:0;color:var(--ink2)}
footer{padding:20px 0 32px;font-size:12.5px;color:var(--muted)}
@media (max-width:560px){body{font-size:14.5px}dl.gloss{grid-template-columns:1fr}dl.gloss dd{margin-bottom:8px}.toolbar .btn{width:100%}}
@media print{body{background:#fff;font-size:12.5px}.page{max-width:none}.toolbar .btn,summary{display:none}
header,.verdict,.pill,ol.story .n{-webkit-print-color-adjust:exact;print-color-adjust:exact}
section,.card,.row,.stage{break-inside:avoid}details>.body{display:block}}
"""


CHANNEL = {"nip": "NIP transfer", "mobile": "mobile app", "ussd": "USSD", "internet": "internet banking", "card": "card",
           "pos": "POS", "atm": "ATM", "agent": "agent", "branch": "branch", "statement": "from a statement",
           "statement_cash": "cash, from a statement"}


def _ring_name(g: dict) -> str:
    return f"Ring {g['number']}" if g.get("number") else f"Ring {g['id'][:8]}"


def _verdict(g: dict) -> tuple[str, str, str]:
    """(css class, headline, recommended step) in plain words."""
    sm, score = g["summary"], g["score"]
    band = "High" if score >= 0.85 else "Elevated" if score >= 0.6 else "Watch"
    head = (f"{band} risk ({score:.2f}). {sm['size']} accounts received {naira(sm['victim_inflow'])} from "
            f"{sm['possible_victims']} people and {naira(sm['cash_out_total'])} was withdrawn as cash.")
    complaints = any(s["code"] == "VICTIM_COMPLAINT" for n in g["nodes"] for s in n["signals"])
    if g["status"] == "confirmed":
        return "good", head, ("Confirmed as a mule ring. Post-no-debit blocks were requested at the bank. Contact the victims about "
                              "recovery and keep this pack with the case file.")
    if g["status"] == "dismissed":
        return "good", head, "Dismissed as legitimate after review. No further action unless new activity appears."
    if score >= 0.85 or complaints:
        return "", head, ("Put the accounts on the 24-hour watchlist now so no more money leaves, then call two or three of the "
                          "senders. If they confirm they were defrauded, confirm the ring.")
    return "", head, "Review the accounts. A 24-hour watchlist holds outgoing money while you check with the senders."


def render(g: dict, actions: list[dict], bank_name: str, generated: datetime) -> str:
    e = html.escape
    sm = g["summary"]
    nodes = {n["id"]: n for n in g["nodes"]}
    in_ring = lambda i: i in sm["roles"]  # noqa: E731
    role = lambda i: nodes.get(i, {}).get("role")  # noqa: E731
    who = lambda i: e(nodes[i]["name"] or nodes[i]["account_no"]) if i in nodes else e(i)  # noqa: E731
    members = sorted((n for n in g["nodes"] if in_ring(n["id"])), key=lambda n: -n["risk"])

    cls, head, step = _verdict(g)
    period = f"{day_label(sm['first_seen'])} – {day_label(sm['last_seen'])}" if sm["first_seen"] else "not recorded"
    steps = ""
    for i, (t, b) in enumerate(story(g), 1):
        first, _, rest = b.partition(". ")
        steps += (f"<li><span class='n'>{i}</span><div><b>{e(t)}</b><p>{e(first.rstrip('.'))}.</p>"
                  + (f"<small>{e(rest)}</small>" if rest else "") + "</div></li>")

    found: dict[str, dict] = {}
    for n in members:
        for s in n["signals"]:
            f = found.setdefault(s["code"], {"max": 0.0, "hits": []})
            f["max"] = max(f["max"], s["weight"])
            f["hits"].append((n, s["reason"]))
    rows = ""
    for code, f in sorted(found.items(), key=lambda kv: (-kv[1]["max"], -len(kv[1]["hits"]))):
        title, means = PLAIN.get(code, (code.replace("_", " ").capitalize(), ""))
        st = strength(f["max"])
        names = [n["name"] or n["account_no"] for n, _ in f["hits"]]
        on = ", ".join(names[:3]) + (f" and {len(names) - 3} more" if len(names) > 3 else "")
        seen = "".join(f"<li><b>{e(n['name'] or n['account_no'])}</b>: {e(r)}</li>" for n, r in f["hits"])
        rows += (f"<div class='row'><div class='top'><span class='title'>{e(title)}</span><span class='pill {st}'>{st}</span></div>"
                 f"<div class='sub'>Found on {len(names)} account{'s' if len(names) != 1 else ''}: {e(on)}</div>"
                 f"<details><summary>What this means</summary><div class='body'>{e(means)}<ul>{seen}</ul></div></details></div>")

    cards = ""
    for n in members:
        role_name, role_means = ROLE.get(n["role"], (n["role"], ""))
        band = "High" if n["risk"] >= 0.85 else "Elevated" if n["risk"] >= 0.6 else "Watch" if n["risk"] >= 0.35 else "Low"
        pill = {"High": "Strong", "Elevated": "Moderate"}.get(band, "Supporting")
        main = PLAIN.get(n["signals"][0]["code"], (n["signals"][0]["code"], ""))[0] if n["signals"] else "–"
        cards += (f"<div class='card'><div class='top flow'><span class='name'>{e(n['name'] or 'Unknown')}</span>"
                  f"<span class='pill {pill}'>{band} · {n['risk']:.2f}</span></div>"
                  f"<div class='acct'>{e(n['bank_code'])}/{e(n['account_no'])}{' · our customer' if n['home'] else ' · other bank'}</div>"
                  f"<dl><dt>Role</dt><dd>{e(role_name)}</dd><dt>Status</dt><dd>{e(n['status'].replace('_', ' ').capitalize())}</dd>"
                  f"<dt>Main finding</dt><dd>{e(main)}</dd></dl></div>")

    stages = [
        ("Paid in by possible victims", lambda x: role(x["src"]) in ("victim", "source") and in_ring(x["dst"])),
        ("Passed between ring accounts", lambda x: in_ring(x["src"]) and in_ring(x["dst"])),
        ("Withdrawn or sent out of the ring", lambda x: in_ring(x["src"]) and role(x["dst"]) in ("cash_point", "exit")),
        ("Followed into other banks", lambda x: role(x["src"]) in ("exit", "traced")),
    ]
    trail = ""
    for title, test in stages:
        flows = sorted((x for x in g["edges"] if test(x)), key=lambda x: -x["amount"])
        if not flows:
            continue
        total = sum(x["amount"] for x in flows)
        first, last = min(x["first"] for x in flows), max(x["last"] for x in flows)
        line = lambda x: (f"<div class='row flow'><span class='who'>{who(x['src'])}<span class='arrow'>→</span>{who(x['dst'])}</span>"  # noqa: E731
                          f"<span class='amt'>{naira(x['amount'])}</span>"
                          f"<span class='sub' style='flex-basis:100%'>{x['count']} transfer{'s' if x['count'] != 1 else ''} · "
                          f"{e(when_label(x['first']))} · {e(', '.join(CHANNEL.get(c, c) for c in x['channels']))}</span></div>")
        top, rest = flows[:5], flows[5:]
        trail += (f"<div class='stage'><h3>{e(title)}</h3><div class='sum'>{naira(total)} in {sum(x['count'] for x in flows)} "
                  f"transfers, {e(when_label(first))} to {e(when_label(last))}</div><div class='list'>{''.join(line(x) for x in top)}</div>"
                  + (f"<details><summary>Show all {len(flows)}</summary><div class='body'><div class='list'>"
                     f"{''.join(line(x) for x in rest)}</div></div></details>" if rest else "") + "</div>")

    ids = "".join(
        f"<div class='row'><div class='top'><span class='title'>"
        f"{'Same BVN' if x['kind'] == 'bvn' else 'Same phone number' if x['kind'] == 'phone' else 'Same phone or device'}</span>"
        f"<span class='acct'>{e(x['masked'])}</span></div><div class='sub'>Used by "
        f"{e(', '.join(nodes[a]['name'] or a for a in x['accounts'] if a in nodes))}</div></div>"
        for x in g["identifier_links"]) or "<div class='row sub'>No phone, device or BVN is shared inside this ring.</div>"
    acts = "".join(
        f"<div class='row'><div class='top'><span class='title'>{e(ACTION.get(x['action'], x['action']))}</span>"
        f"<span class='sub'>{e(when_label(x['at']))}</span></div><div class='sub'>By {e(x['actor'])} · {len(x['accounts'])} account"
        f"{'s' if len(x['accounts']) != 1 else ''}{' · ' + e(x['note']) if x['note'] else ''} · <span class='acct'>{e(x['action'])}</span>"
        f"</div></div>" for x in actions) or "<div class='row sub'>No analyst action has been taken yet.</div>"
    gloss = "".join(f"<dt>{e(v[0])}</dt><dd>{e(v[1])}</dd>" for v in ROLE.values())
    gloss += ("<dt>Risk score</dt><dd>From 0 to 1. Above 0.60 is flagged for review, above 0.85 is high. It shows where to look "
              "first; it is not proof of guilt.</dd><dt>Strong, Moderate, Supporting</dt><dd>How much a finding counts on its own. "
              "A victim complaint is strong; a new account on its own is only supporting.</dd>")

    return f"""<!doctype html><html lang="en-NG"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Evidence pack · {e(_ring_name(g))}</title><style>{CSS}</style></head><body><div class="page">
<header><div class="wrap"><div class="kicker">Mule network evidence pack</div><h1>{e(_ring_name(g))}</h1>
<div class="meta"><span>{e(bank_name)}</span><span>{e(STATUS.get(g['status'], g['status']))}</span><span>Activity {e(period)}</span></div></div></header>
<div class="wrap">
<div class="toolbar"><span>Prepared {e(when_label(generated.isoformat()))} · all times are Lagos time (WAT)</span>
<button class="btn" onclick="window.print()">Print or save as PDF</button></div>
<div class="verdict {cls}"><b>{e(head)}</b><p><strong>Recommended next step:</strong> {e(step)}</p></div>
<div class="tiles"><div><span>Accounts in ring</span><b>{sm['size']}</b></div><div><span>Possible victims</span><b>{sm['possible_victims']}</b></div>
<div><span>Paid in by victims</span><b>{naira(sm['victim_inflow'])}</b></div><div><span>Withdrawn as cash</span><b>{naira(sm['cash_out_total'])}</b></div></div>
<section><h2>What happened</h2><p class="lead">The ring in plain words, worked out from the transfers and reports below.</p><ol class="story">{steps}</ol></section>
<section><h2>The evidence</h2><p class="lead">Strongest first. Open a finding to see what it means and what was seen on each account.</p><div class="list">{rows}</div></section>
<section><h2>Accounts in the ring</h2><p class="lead">Highest risk first. People who paid in are possible victims and appear in the money trail.</p><div class="cards">{cards}</div></section>
<section><h2>Money trail</h2><p class="lead">Grouped by stage, largest first. Each line is the total between two accounts.</p>{trail}</section>
<section><h2>Shared details</h2><p class="lead">Phone numbers, devices and BVNs used by more than one account in the ring. Values are masked.</p><div class="list">{ids}</div></section>
<section><h2>Actions taken</h2><div class="list">{acts}</div></section>
<section><details><summary>Words used in this pack</summary><div class="body"><dl class="gloss">{gloss}</dl></div></details></section>
<footer><p class="note">Identifiers are masked; TheOne does not store raw phone numbers, device ids or BVNs. Risk scores and findings are
indicators for investigation, not findings of guilt. People who paid into the ring are treated as possible victims.</p></footer>
</div></div>
<script>window.addEventListener("beforeprint",()=>document.querySelectorAll("details").forEach(d=>d.open=true));</script>
</body></html>"""
