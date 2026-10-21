"""Read a bank statement into lines: date, narration, amount, direction, balance and the other side.

A statement shows one account from the inside. It can reveal mule behaviour on that account
(money passing straight through, many unrelated payers, fast cash-out, round-amount splits,
a dormant account waking up) but not the ring around it, because the other side's account
number is usually missing. Narrations often name the other side, so names are read from them,
and account numbers are picked up when a narration carries one.

Readers, tried in order:
  csv    a CSV export with a header row (date, narration, debit/credit or amount, balance)
  text   text copied from a statement or extracted from a PDF: one transaction per line that
         starts with a date (one or two dates; several date styles; optional time), ending in
         debit/credit/balance columns, an amount and balance, or amounts marked CR/DR

Most statements carry dates, not times, so "fast" means the same or the next day unless times
are present. Checking stores nothing; adding a statement to the money map is a separate step.
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime

MONTHS = {m: i for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}
# Date styles seen on Nigerian statements. Day comes before month in numeric dates.
DATE = (r"(?:\d{1,2}-[A-Za-z]{3}-\d{2,4}|\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2}|\d{1,2}-\d{1,2}-\d{4}|"
        r"\d{1,2}\s+[A-Za-z]{3,9},?\s+\d{4}|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})")
TIME = r"(?:\s+(\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?))?"
LINE_START = re.compile(rf"^\s*({DATE}){TIME}(?:\s+({DATE}))?(?:\s+|$)", re.I)
MONEY = r"(?:NGN|₦)?\s?-?[\d,]*\d\.\d{2}(?:\s?(?:CR|DR))?"
TOKEN = re.compile(rf"({MONEY}|(?<!\S)-(?!\S))", re.I)
HEADER = re.compile(r"(Posted|Trans(?:action)?|Value)?\s*Date.{0,40}(Description|Narration|Details|Remarks).{0,60}Balance", re.I)
FEE = re.compile(r"^(COMMISSION|VAT\b|FGN STAMP|SMS ALERT|SMS CHARGE|CHARGE\b|ACCOUNT MAINTENANCE|MAINTENANCE FEE|COT\b|"
                 r"STAMP DUTY|ELECTRONIC MONEY TRANSFER LEVY|EMTL)", re.I)
REVERSAL = re.compile(r"^(REVERSAL|RVSL|REV\b)", re.I)
OPENING = re.compile(r"^(OPENING BALANCE|BALANCE B/?F|BROUGHT FORWARD|BAL B/F)", re.I)
BILL = re.compile(r"BILLS? PYMT|BILL PAYMENT|AIRTIME|DATA TOP ?UP|DATA PURCHASE|DIRECT DEBIT|DSTV|GOTV|ELECTRIC|PREPAID|IKEDC|EKEDC", re.I)
CASH = re.compile(r"\bATM\b|CASH WDL|POS WDL|POS TRANSFER|CASH WITHDRAWAL|AGENT WITHDRAWAL", re.I)
CARD = re.compile(r"VIRTUAL CARD|CARD FUNDING|POS PURCHASE|WEB PURCHASE|POS/WEB", re.I)
BUSINESS = re.compile(r"\b(LTD|LIMITED|VENTURES?|SERVICES|ENTERPRISES?|NIGERIA|HEALTHCARE|HOTEL|MARKETPLACE|PAYSTACK|FLUTTERWAVE|"
                      r"HOSTAFRICA|EMPIRE|MULTIPURPOSE|CHECKOUT|STORES?|PHARMACY|PLC|GLOBAL|RESOURCES|INTEGRATED|CONCEPTS?)\b", re.I)
OUT_TRF = re.compile(r"^(?:MOBILE\s+|\*\d+#\s+|USSD\s+|INTERNET\s+|WEB\s+)?TRF\s+TO\s+([A-Z0-9]+)\s*/\s*(.*)$", re.I)
NAMED = re.compile(r"(?:TRF|TRANSFER|NIP|FT|MOB|USSD)?\s*(?:FROM|FRM|TO|BY)\s*:?\s*([A-Z][A-Za-z.'\- ]{3,60}?)(?=\s*(?:/|-\s|\d|$|REF|VIA|FOR))", re.I)
NUBAN = re.compile(r"(?<!\d)(\d{10})(?!\d)")
BANK_WORDS = re.compile(r"\b(GTB|GTBANK|ZENITH|ACCESS|UBA|FBN|FIRST ?BANK|FIDELITY|STERLING|WEMA|OPAY|PALMPAY|MONIEPOINT|KUDA|ECOBANK|"
                        r"FCMB|UNION|STANBIC|POLARIS|KEYSTONE|PROVIDUS|JAIZ|UNITY|HERITAGE|GLOBUS|TITAN|PARALLEX|CARBON|VFD|"
                        r"MONIEPOINT MFB|PAGA|9PSB|MTN MOMO|ALAT)\b", re.I)

NAIRA = 100


@dataclass
class Line:
    """One statement line. Amounts are positive kobo with a direction ("in" or "out"). The party, bank
    tag, the customer's own note and any 10-digit account number are read from the narration."""

    i: int
    posted: date
    desc: str
    amount: int
    direction: str
    balance: int | None
    kind: str
    party: str = ""
    tag: str = ""
    note: str = ""
    nuban: str = ""
    at: str = ""
    self_transfer: bool = False


@dataclass
class Parsed:
    holder: str = ""
    account_no: str = ""
    period: str = ""
    opening: int | None = None
    closing: int | None = None
    lines: list[Line] = field(default_factory=list)
    skipped: int = 0
    truncated: bool = False
    layout: str = ""


def parse_date(s: str) -> date:
    s = " ".join(s.replace(",", " ").split())
    for fmt in ("%d-%b-%y", "%d-%b-%Y", "%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%d-%m-%Y", "%d %b %Y", "%d %B %Y", "%b %d %Y", "%B %d %Y"):
        try:
            return datetime.strptime(s.title() if "%b" in fmt or "%B" in fmt else s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unreadable date {s!r}")


def _k(s: str) -> int:
    v = re.sub(r"(?i)NGN|₦|CR|DR|\s", "", s).replace(",", "")
    return round(float(v) * 100)


def _money(label: str, text: str) -> int | None:
    m = re.search(rf"{label}\s*:?\s*(?:NGN|₦)?\s*(-?[\d,]+\.\d{{2}})", text, re.I)
    return _k(m.group(1)) if m else None


def _tokens(name: str) -> set[str]:
    return {t for t in re.sub(r"[^A-Z ]", " ", name.upper()).split() if len(t) > 1}


def _clean_name(s: str) -> str:
    s = re.sub(r"^(POS Transfer-?|NIP\s*(TRF|TRANSFER)?\s*(FROM|TO)?|TRF\s*(FROM|TO)|TRANSFER\s*(FROM|TO))\s*", "", s.strip(), flags=re.I)
    s = re.sub(r"\s+", " ", s).strip(" -/.:")
    return s[:80]


def _looks_like_name(seg: str) -> bool:
    words = [w for w in re.split(r"\s+", seg.strip()) if w]
    return 2 <= len(words) <= 8 and not re.search(r"\d", seg) and sum(w.isalpha() for w in words) >= 2


def read_party(desc: str, direction: str) -> tuple[str, str, str, str]:
    """(name, bank tag, own narration, account number) read from one narration."""
    nuban_m = NUBAN.search(desc)
    nuban = nuban_m.group(1) if nuban_m else ""
    o = OUT_TRF.match(desc) if direction == "out" else None
    # MOBILE TRF TO <BANK>/ <narration> /<NAME>
    if o:
        parts = [x.strip() for x in o.group(2).split("/") if x.strip()]
        return _clean_name(parts[-1] if parts else ""), o.group(1).upper(), parts[0] if len(parts) > 1 else "", nuban
    bank = BANK_WORDS.search(desc)
    tag = bank.group(1).upper().replace(" ", "") if bank else ""
    if direction == "in" and desc.upper().startswith("RTGI/"):
        return _clean_name(desc.split("/")[-1]), tag, "", nuban
    segs = [x.strip() for x in re.split(r"/|\|", desc) if x.strip()]
    # NIP/<BANK>/<NAME>/<ref> and similar: the first segment that reads like a person or business.
    for seg in segs:
        cleaned = _clean_name(seg)
        if _looks_like_name(cleaned) and not BANK_WORDS.fullmatch(cleaned):
            return cleaned, tag, "", nuban
    n = NAMED.search(desc)
    if n:
        return _clean_name(n.group(1)), tag, "", nuban
    return _clean_name(segs[0] if segs else desc), tag, "", nuban


def _classify(desc: str) -> str:
    return ("fee" if FEE.match(desc) else "reversal" if REVERSAL.match(desc) else "card" if CARD.search(desc)
            else "bill" if BILL.search(desc) else "cash" if CASH.search(desc) else "transfer")


def _header(text: str, p: Parsed) -> None:
    m = re.search(r"(?:Account Name|Customer Name|Name of Account|Account Holder)\s*:?\s*([A-Za-z][^\n:]{2,80})", text, re.I)
    p.holder = " ".join(m.group(1).split()) if m else ""
    m = re.search(r"(?:Account (?:Number|No\.?)|A/C (?:No\.?|Number))\s*:?\s*(\d{10})", text, re.I)
    p.account_no = m.group(1) if m else ""
    m = re.search(r"(?:Statement Period|Period)\s*:?\s*(.+?)(?:Currency|\n\s*\n|$)", text, re.S | re.I)
    p.period = " ".join(m.group(1).split())[:120] if m else ""
    p.opening, p.closing = _money("Opening Balance", text), _money("Closing Balance", text)
    p.truncated = "message truncated" in text.lower()


def _add(p: Parsed, posted: date, desc: str, amount: int, direction: str, balance: int | None, at: str = "") -> None:
    desc = " ".join(desc.split()).strip(" -")
    line = Line(len(p.lines), posted, desc, amount, direction, balance, _classify(desc), at=at)
    line.party, line.tag, line.note, line.nuban = read_party(desc, direction)
    line.self_transfer = len(_tokens(p.holder) & _tokens(line.party)) >= 2
    p.lines.append(line)


def _direction(tokens: list[str], prev_balance: int | None, desc: str) -> tuple[int, str, int | None] | None:
    """Work out amount, direction and balance from the money columns at the end of a line."""
    marked = [t for t in tokens if re.search(r"(CR|DR)\s*$", t, re.I)]
    vals = [None if t == "-" else _k(t) for t in tokens]
    if marked and len(tokens) <= 2:
        amt_tok = marked[0]
        bal = vals[-1] if len(tokens) == 2 and tokens[-1] != amt_tok else None
        return abs(_k(amt_tok)), "in" if amt_tok.upper().rstrip().endswith("CR") else "out", bal
    if len(tokens) >= 3:
        debit, credit, bal = vals[-3], vals[-2], vals[-1]
        if debit not in (None, 0):
            # A negative debit is a reversal credit.
            return (abs(debit), "in" if debit < 0 else "out", bal)
        if credit not in (None, 0):
            return abs(credit), "in", bal
        return None
    if len(tokens) == 2 and vals[0] is not None and vals[1] is not None:
        amt, bal = vals
        if prev_balance is not None:
            delta = bal - prev_balance
            if abs(abs(delta) - abs(amt)) <= max(200, abs(amt) // 1000):
                return abs(amt), "in" if delta > 0 else "out", bal
        if amt < 0:
            return -amt, "out", bal
        if re.search(r"\b(FROM|CREDIT|DEPOSIT|LODGEMENT|REVERSAL|INWARD)\b", desc, re.I):
            return amt, "in", bal
        return amt, "out", bal
    return None


def _parse_text(text: str, p: Parsed) -> None:
    body = re.sub(r"</?pasted_content[^>]*>|\[Message truncated[^\]]*\]", " ", text)
    start = re.search(r"\bTRANSACTIONS\b|Transaction Details|Account Activity", body, re.I)
    body = body[start.end():] if start else body
    entries: list[list] = []
    for raw in body.splitlines():
        if HEADER.search(raw):
            continue
        m = LINE_START.match(raw)
        if m:
            try:
                d = parse_date(m.group(1))
            except ValueError:
                d = None
            if d:
                entries.append([d, m.group(2) or "", raw[m.end():]])
                continue
        if entries and raw.strip():
            entries[-1][2] += " " + raw.strip()
    prev = p.opening
    for d, at, seg in entries:
        seg = " ".join(seg.split())
        toks = list(TOKEN.finditer(seg))
        # Money columns are the last run of adjacent amount tokens. Most layouts end with them;
        # some (remarks after the balance) put text after, so the run can sit mid-line.
        runs: list[list[re.Match]] = []
        for t in toks:
            if runs and not seg[runs[-1][-1].end(): t.start()].strip():
                runs[-1].append(t)
            else:
                runs.append([t])
        good = [r for r in runs if len(r) >= 2 or re.search(r"(CR|DR)\s*$", r[0].group(1), re.I)]
        if not good:
            p.skipped += 1
            continue
        tail = good[-1]
        desc = seg[: tail[0].start()] + " " + seg[tail[-1].end():]
        if OPENING.match(desc.strip()):
            prev = _k(tail[-1].group(1))
            if p.opening is None:
                p.opening = prev
            continue
        got = _direction([t.group(1) for t in tail[-3:]], prev, desc)
        if not got:
            p.skipped += 1
            continue
        amt, direction, bal = got
        _add(p, d, desc, amt, direction, bal, at)
        if bal is not None:
            prev = bal
    p.layout = "text"


CSV_FIELDS = {
    "date": ["transaction date", "trans date", "posted date", "post date", "txn date", "date", "value date"],
    "desc": ["narration", "description", "transaction details", "details", "remarks", "particulars", "transaction description"],
    "debit": ["debit", "debits", "withdrawal", "withdrawals", "money out", "debit amount", "dr"],
    "credit": ["credit", "credits", "deposit", "deposits", "lodgement", "lodgements", "money in", "credit amount", "cr"],
    "amount": ["amount", "transaction amount"],
    "type": ["type", "dr/cr", "debit/credit", "transaction type"],
    "balance": ["balance", "running balance", "closing balance", "available balance", "balance (ngn)"],
}


def _parse_csv(text: str, p: Parsed) -> bool:
    try:
        dialect = csv.Sniffer().sniff(text[:4000], delimiters=",;\t")
    except csv.Error:
        return False
    rows = list(csv.reader(io.StringIO(text), dialect))
    for hi, row in enumerate(rows[:40]):
        names = [c.strip().lower() for c in row]
        col = {}
        for key, aliases in CSV_FIELDS.items():
            for a in aliases:
                if a in names:
                    col[key] = names.index(a)
                    break
        if "date" in col and "desc" in col and ({"debit", "credit"} & col.keys() or "amount" in col):
            break
    else:
        return False
    prev = p.opening
    for row in rows[hi + 1:]:
        cell = lambda k: row[col[k]].strip() if k in col and col[k] < len(row) else ""  # noqa: E731
        try:
            d = parse_date(cell("date").split(" ")[0] if re.match(r"\d{4}-", cell("date")) else cell("date"))
        except ValueError:
            p.skipped += 1 if any(c.strip() for c in row) else 0
            continue
        desc = cell("desc")
        bal = _k(cell("balance")) if re.search(r"\d", cell("balance")) else None
        if OPENING.match(desc):
            prev = bal
            continue
        debit = _k(cell("debit")) if re.search(r"\d", cell("debit")) else 0
        credit = _k(cell("credit")) if re.search(r"\d", cell("credit")) else 0
        if not debit and not credit and re.search(r"\d", cell("amount")):
            amt = _k(cell("amount"))
            kind = cell("type").upper()
            if kind.startswith(("C", "CR")):
                credit = abs(amt)
            elif kind.startswith(("D", "DR")):
                debit = abs(amt)
            elif prev is not None and bal is not None:
                credit, debit = (abs(amt), 0) if bal > prev else (0, abs(amt))
            else:
                credit, debit = (amt, 0) if amt > 0 else (0, -amt)
        if debit:
            _add(p, d, desc, abs(debit), "in" if debit < 0 else "out", bal)
        elif credit:
            _add(p, d, desc, abs(credit), "in", bal)
        else:
            continue
        if bal is not None:
            prev = bal
    p.layout = "csv"
    return bool(p.lines)


def parse(text: str) -> Parsed:
    p = Parsed()
    _header(text, p)
    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    if first.count(",") >= 3 or first.count("\t") >= 3 or first.count(";") >= 3 or re.search(r"(narration|description).*(debit|credit|amount)", text[:3000], re.I) and text.count(",") > 20:
        if _parse_csv(text, Parsed(holder=p.holder, account_no=p.account_no, opening=p.opening)):
            q = Parsed(holder=p.holder, account_no=p.account_no, period=p.period, opening=p.opening, closing=p.closing)
            _parse_csv(text, q)
            return q
    _parse_text(text, p)
    return p


def pdf_text(data: bytes, password: str | None = None) -> str:
    """Text of a PDF statement, page by page. Many Nigerian banks password-protect statements."""
    import pdfplumber
    from pdfminer.pdfdocument import PDFPasswordIncorrect
    from pdfplumber.utils.exceptions import PdfminerException

    try:
        with pdfplumber.open(io.BytesIO(data), password=password or "") as pdf:
            if len(pdf.pages) > 300:
                raise ValueError("this PDF has more than 300 pages; split the statement")
            return "\n".join((pg.extract_text(layout=False) or "") for pg in pdf.pages)
    except (PDFPasswordIncorrect, PdfminerException) as e:
        inner = e.args[0] if isinstance(e, PdfminerException) and e.args else e
        if isinstance(inner, PDFPasswordIncorrect):
            raise PermissionError("this PDF is password protected; enter the statement password") from e
        raise ValueError("this PDF could not be read; try exporting the statement again") from e


def party_key(line: Line) -> tuple[str, str]:
    """A stable key for the other side when the statement gives no account number."""
    norm = " ".join(sorted(_tokens(line.party))) or line.desc[:40].upper()
    return f"ST-{(line.tag or 'UNK')[:9]}", "N" + hashlib.sha1(norm.encode()).hexdigest()[:12]
