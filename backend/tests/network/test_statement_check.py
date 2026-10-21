"""Statement check: parsing a text statement, mule checks and the payment-check replay.

Uses made-up statements only; never real customer data."""
from app.network.domain.statements import check, parse

HEAD = """Account Details
Account Name: ADA OBI NWOSU
Account Number: 0123456789
Opening Balance: {opening}
Closing Balance: 0.00
TRANSACTIONS
Posted Date Value Date Description Debit (NGN) Credit (NGN) Balance (NGN)
01-JAN-26 01-JAN-26 Opening Balance - 0.00 {opening}
"""


def _stmt(rows: list[tuple[str, str, float, float]], opening: float) -> str:
    bal, out = opening, [HEAD.format(opening=f"{opening:,.2f}")]
    for day, desc, debit, credit in rows:
        bal += credit - debit
        out.append(f"{day} {day} {desc} {f'{debit:,.2f}' if debit else '-'} {f'{credit:,.2f}' if credit else '-'} {bal:,.2f}\n")
    return "".join(out)


def ordinary() -> str:
    rows = []
    for d in range(2, 28):
        day = f"{d:02d}-JAN-26"
        rows.append((day, f"MOBILE TRF TO PAY/ Food /SHOP {d} VENTURES", 3_000, 0))
        rows.append((day, "COMMISSION MOBILE TRF TO PAY/ Food", 25, 0))
        if d % 5 == 0:
            rows.append((day, "MOBILE BILLS PYMT/ MTN DATA/08030000000", 1_000, 0))
    rows.append(("15-JAN-26", "Transfer from EMPLOYER LIMITED", 0, 250_000))
    return _stmt(rows, 800_000)


FIRST = ["AMAKA", "BOLA", "CHIDI", "DAYO", "EMEKA", "FUNMI", "GODWIN", "HALIMA"]
LAST = ["OKAFOR", "ADEYEMI"]


def mule_like() -> str:
    rows = []
    for d in (10, 11):
        day = f"{d:02d}-FEB-26"
        for k in range(8):
            rows.append((day, f"Transfer from {FIRST[k]} {LAST[d % 2]} {LAST[(k + 1) % 2]}", 0, 150_000))
        for k in range(4):
            rows.append((day, f"MOBILE TRF TO GTB/ Fund /COLLECTOR {k} PARTNER", 280_000, 0))
        rows.append((day, "MOBILE TRF TO MMF/ Fund /POS Transfer-AGENT CASH POINT", 60_000, 0))
    return _stmt(rows, 2_000)


def test_parse_reconciles_and_reads_counterparties():
    p = parse(ordinary())
    assert p.holder == "ADA OBI NWOSU" and p.account_no == "0123456789"
    assert {x.kind for x in p.lines} >= {"transfer", "fee", "bill"}
    salary = next(x for x in p.lines if x.direction == "in")
    assert salary.party == "EMPLOYER LIMITED" and salary.amount == 250_000_00
    shop = next(x for x in p.lines if x.kind == "transfer" and x.direction == "out")
    assert shop.tag == "PAY" and shop.note == "Food" and shop.party == "SHOP 2 VENTURES"


def test_ordinary_account_is_low_risk():
    r = check(ordinary())
    assert r["mule"]["band"] == "Low" and not r["mule"]["flagged"]
    assert not any(c["fired"] for c in r["mule"]["checks"])
    assert r["everyday"]["bills_and_data"] >= 4


def test_mule_like_account_is_flagged_with_reasons():
    r = check(mule_like())
    fired = {c["code"] for c in r["mule"]["checks"] if c["fired"]}
    assert {"FAN_IN", "PASS_THROUGH", "LOW_BALANCE"} <= fired
    assert r["mule"]["flagged"] and r["mule"]["band"] in {"Elevated", "High"}


def test_large_unusual_payment_is_questioned():
    rows = [(f"{d:02d}-JAN-26", f"MOBILE TRF TO PAY/ Fund /FRIEND {d} NAME", 10_000, 0) for d in range(2, 12)]
    rows.append(("20-JAN-26", "MOBILE TRF TO GTB/ Urgent /STRANGER UNKNOWN PERSON", 900_000, 0))
    r = check(_stmt(rows, 2_000_000))
    hit = [x for x in r["payments"] if x["to"] == "STRANGER UNKNOWN PERSON"]
    assert hit and hit[0]["outcome"] in {"Confirm it is you", "Hold"}


def test_endpoint_and_role(client, monkeypatch):
    from app.core.config import get_settings
    assert client.post("/network/statement/check", json={"text": ordinary()}).json()["mule"]["band"] == "Low"
    assert client.post("/network/statement/check", json={"text": "x" * 80}).status_code == 422
    monkeypatch.setattr(get_settings(), "api_keys", "app-key:app,ana-key:analyst")
    hdr = lambda k: {"X-API-Key": k}  # noqa: E731
    assert client.post("/network/statement/check", json={"text": ordinary()}, headers=hdr("app-key")).status_code == 403
    assert client.post("/network/statement/check", json={"text": ordinary()}, headers=hdr("ana-key")).status_code == 200
