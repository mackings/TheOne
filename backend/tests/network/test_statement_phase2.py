"""Statement check, phase 2: more layouts, PDF statements, and adding statements to the money map.

All statements here are made up. Layouts imitate common Nigerian bank exports, not real customers."""
from datetime import date, timedelta

import pytest

from app.network.domain.statements import check, parse, pdf_text

TODAY = date.today()


def d(n: int, fmt: str = "%d/%m/%Y") -> str:
    return (TODAY - timedelta(days=n)).strftime(fmt)


def test_slash_dates_amount_and_balance_columns():
    """Zenith-style: one date, description, a single amount column and a running balance."""
    text = "\n".join([
        "Account Name: TUNDE BALOGUN", "Account Number: 2012345678", "Opening Balance: 50,000.00",
        "DATE POSTED DESCRIPTION AMOUNT BALANCE",
        f"{d(5)} NIP TRF FROM AMAKA OKAFOR/0123456789/GTB 20,000.00 70,000.00",
        f"{d(5)} TRF TO SAMUEL EZE/UBA 15,000.00 55,000.00",
        f"{d(4)} SMS CHARGE 4.00 54,996.00",
    ])
    p = parse(text)
    assert p.layout == "text" and len(p.lines) == 3
    a, b, fee = p.lines
    assert (a.direction, a.amount, a.party, a.nuban, a.tag) == ("in", 2_000_000, "AMAKA OKAFOR", "0123456789", "GTB")
    assert (b.direction, b.party) == ("out", "SAMUEL EZE") and fee.kind == "fee"


def test_cr_dr_markers_times_and_remarks_after_balance():
    """GTBank-style: date and time, amounts marked CR/DR, remarks after the balance."""
    text = "\n".join([
        "Account Name: NGOZI ADEYEMI", "Account No: 0098765432",
        f"{d(3, '%d-%b-%Y')} 14:05:10 25,000.00CR 125,000.00 TRANSFER FROM BOLA AKINWALE",
        f"{d(3, '%d-%b-%Y')} 14:40:00 24,500.00DR 100,500.00 POS WDL AGENT MUSA",
    ])
    p = parse(text)
    assert [x.direction for x in p.lines] == ["in", "out"] and p.lines[0].at.startswith("14:05")
    assert p.lines[0].party == "BOLA AKINWALE" and p.lines[1].kind == "cash"


def test_csv_with_amount_and_type_columns():
    text = "\n".join([
        "Customer Statement,,,,",
        "Transaction Date,Narration,Amount,Type,Balance",
        f"{d(2, '%Y-%m-%d')},Transfer from CHIDI NWOSU,30000.00,CR,80000.00",
        f"{d(1, '%Y-%m-%d')},Airtime MTN 0803,1000.00,DR,79000.00",
    ])
    p = parse(text)
    assert p.layout == "csv" and [(x.direction, x.kind) for x in p.lines] == [("in", "transfer"), ("out", "bill")]


def _pdf(lines: list[str]) -> bytes:
    """A minimal one-page PDF with the given text lines (Courier), with a correct xref table."""
    esc = lambda s: s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")  # noqa: E731
    stream = "BT /F1 8 Tf 20 800 Td 10 TL " + " ".join(f"({esc(x)}) Tj T*" for x in lines) + " ET"
    objs = ["<</Type/Catalog/Pages 2 0 R>>", "<</Type/Pages/Kids[3 0 R]/Count 1>>",
            "<</Type/Page/Parent 2 0 R/MediaBox[0 0 842 842]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>",
            f"<</Length {len(stream)}>>stream\n{stream}\nendstream", "<</Type/Font/Subtype/Type1/BaseFont/Courier>>"]
    out, offsets = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode() + b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer<</Size {len(objs) + 1}/Root 1 0 R>>\nstartxref\n{xref}\n%%EOF".encode()
    return out


def test_pdf_statement_is_read(client):
    lines = ["Account Name: TUNDE BALOGUN", "Account Number: 2012345678", "Opening Balance: 50,000.00",
             f"{d(5)} NIP TRF FROM AMAKA OKAFOR/0123456789/GTB 20,000.00 70,000.00",
             f"{d(5)} TRF TO SAMUEL EZE/UBA 15,000.00 55,000.00"]
    pdf = _pdf(lines)
    assert "AMAKA OKAFOR" in pdf_text(pdf)
    r = client.post("/network/statement/check-file", files={"file": ("s.pdf", pdf, "application/pdf")}).json()
    assert r["totals"]["credits"] == 1 and r["account"]["account_no"] == "2012345678" and "text" in r


FIRST = ["AMAKA", "BOLA", "CHIDI", "DAYO", "EMEKA", "FUNMI", "GODWIN", "HALIMA"]


def mule_statement(holder: str, number: str, pays_to: tuple[str, str] | None) -> str:
    """Eight strangers pay in each day; almost everything leaves the same day."""
    rows, bal = [f"Account Name: {holder}", f"Account Number: {number}", "Opening Balance: 5,000.00"], 5_000.0
    for day in (6, 5, 4):
        for k in range(8):
            bal += 120_000
            rows.append(f"{d(day)} TRANSFER FROM {FIRST[k]} {['OKAFOR', 'ADEYEMI', 'BELLO'][day % 3]} 120,000.00 {bal:,.2f}")
        for k in range(3):
            bal -= 300_000
            to = f"NIP TRF TO {pays_to[1]}/{pays_to[0]}/GTB" if pays_to else f"TRF TO CASH POINT {FIRST[k]}/OPAY"
            rows.append(f"{d(day)} {to} 300,000.00 {bal:,.2f}")
    return "\n".join(rows)


@pytest.fixture
def fresh(client):
    client.post("/network/reset")
    yield
    client.post("/network/reset")


def test_statements_join_the_money_map_and_form_a_ring(client, fresh):
    b = mule_statement("KEMI LAYER", "0222222222", None)
    a = mule_statement("JOHN COLLECTOR", "0111111111", ("0222222222", "KEMI LAYER"))
    first = client.post("/network/statement/import", json={"text": a, "bank_code": "999"}).json()
    assert first["transfers_added"] > 20 and first["with_account_number"] == 1
    second = client.post("/network/statement/import", json={"text": b, "bank_code": "058"}).json()
    assert second["risk_now"] >= 0.6, "fan-in plus same-day pass-through flags the account"
    rings = client.get("/network/rings").json()
    members = {m["account_no"] for r in rings for m in client.get(f"/network/rings/{r['id']}").json()["nodes"]
               if m["id"] in client.get(f"/network/rings/{r['id']}").json()["summary"]["roles"]}
    assert {"0111111111", "0222222222"} <= members, "the account number in one statement links it to the other"
    again = client.post("/network/statement/import", json={"text": a, "bank_code": "999"}).json()
    assert again["transfers_added"] == 0, "importing the same statement twice adds nothing"


def test_import_needs_supervisor(client, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "api_keys", "ana-key:analyst,sup-key:supervisor")
    body = {"text": mule_statement("X Y", "0333333333", None), "bank_code": "999"}
    assert client.post("/network/statement/import", json=body, headers={"X-API-Key": "ana-key"}).status_code == 403


def test_ordinary_statement_stays_low():
    rows = ["Account Name: ADA NWOSU", "Account Number: 0444444444", "Opening Balance: 900,000.00"]
    bal = 900_000.0
    for n in range(20, 0, -1):
        bal -= 4_000
        rows.append(f"{d(n)} POS PURCHASE SHOPRITE LEKKI 4,000.00 {bal:,.2f}")
    bal += 350_000
    rows.append(f"{d(10)} SALARY FROM ACME NIGERIA LIMITED 350,000.00 {bal:,.2f}")
    assert check("\n".join(rows))["mule"]["band"] == "Low"


def test_password_protected_pdf(client):
    pypdf = pytest.importorskip("pypdf")
    import io

    w = pypdf.PdfWriter()
    w.append(pypdf.PdfReader(io.BytesIO(_pdf(["Account Name: TUNDE BALOGUN", "Account Number: 2012345678",
                                               f"{d(5)} TRANSFER FROM AMAKA OKAFOR 20,000.00CR 70,000.00"]))))
    w.encrypt("1234")
    buf = io.BytesIO()
    w.write(buf)
    files = lambda: {"file": ("s.pdf", buf.getvalue(), "application/pdf")}  # noqa: E731
    assert client.post("/network/statement/check-file", files=files()).status_code == 401
    assert client.post("/network/statement/check-file", files=files(), data={"password": "nope"}).status_code == 403
    ok = client.post("/network/statement/check-file", files=files(), data={"password": "1234"})
    assert ok.status_code == 200 and ok.json()["totals"]["credits"] == 1
