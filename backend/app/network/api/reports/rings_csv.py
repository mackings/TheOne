"""Ring summary as CSV for fraud reporting (a working export, not the official NIBSS template)."""
from __future__ import annotations

import csv
import io

from app.network.domain.engine import Analysis

FILENAME = "theone-mule-rings.csv"


def render(a: Analysis) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["ring_id", "status", "score", "accounts", "possible_victims", "victim_inflow_naira", "cash_out_naira",
                "first_seen", "last_seen", "member_accounts", "typologies"])
    for r in a.rings:
        sm = r.summary
        members = ";".join(f"{a.snapshot.accounts[x].bank_code}/{a.snapshot.accounts[x].account_no}" for x in r.members)
        w.writerow([r.id, r.status, r.score, sm["size"], sm["possible_victims"], sm["victim_inflow"] // 100,
                    sm["cash_out_total"] // 100, sm["first_seen"], sm["last_seen"], members,
                    ";".join(f"{k}:{v}" for k, v in sm["typologies"].items())])
    return buf.getvalue()
