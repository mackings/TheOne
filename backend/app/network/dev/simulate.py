"""Synthetic Nigerian transfer data with planted mule rings, for building and measuring the
engine before any bank data exists.

It deliberately includes legitimate look-alikes that a naive detector would flag:
market traders and ajo (thrift) collectors with many senders, families sharing a phone,
spouses sharing a device, dormant accounts that wake up with small amounts, and payroll.

Ring styles:
  classic          new low-KYC collectors, fast split-and-layer, POS/ATM cash-out
  dormant_rented   old dormant accounts rented out and suddenly reactivated
  external_entry   victims pay a collector at another bank; we see only our half
  reported         like classic, and some victims file complaints
  slow             waits hours between hops (harder; partly missed by design)

Labels (`synthetic_label`) are ground truth for evaluation only; scoring never reads them.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta

from app.core.timeutil import now

FIRST = ["Adaeze", "Chinedu", "Ngozi", "Emeka", "Funmilayo", "Tunde", "Aisha", "Musa", "Zainab", "Ibrahim", "Kemi",
         "Olumide", "Bisi", "Segun", "Halima", "Yusuf", "Chioma", "Ifeanyi", "Amaka", "Obinna", "Tolu", "Femi", "Uche",
         "Nkechi", "Bola", "Sani", "Hauwa", "Garba", "Ebere", "Kelechi", "Damilola", "Gbenga", "Fatima", "Abdullahi",
         "Ijeoma", "Kunle", "Rukayat", "Babajide", "Simi", "Nnamdi"]
LAST = ["Okafor", "Adeyemi", "Bello", "Okonkwo", "Balogun", "Abubakar", "Eze", "Ogunleye", "Mohammed", "Nwosu",
        "Adebayo", "Danjuma", "Okoro", "Lawal", "Chukwu", "Afolabi", "Usman", "Obi", "Ibrahim", "Oyelaran", "Nnaji",
        "Akande", "Yakubu", "Onyeka", "Salami"]
# Partner banks and wallets (demo codes).
OTHER_BANKS = ["B01", "B02", "B03", "B04", "B05", "B06", "W01", "W02"]
SCAM_NARRATIONS = ["investment", "loan processing fee", "POS reversal", "job registration", "crypto deposit",
                   "customs clearance", "promo winning fee", "account upgrade"]


class Generator:
    def __init__(self, seed: int, home_bank: str):
        self.rng = random.Random(seed)
        self.seed = seed
        self.home = home_bank
        self.end = now() - timedelta(minutes=5)
        self.start = self.end - timedelta(days=28)
        self.accounts: dict[str, dict] = {}
        self.transfers: list[dict] = []
        self.reports: list[dict] = []
        self._acct_counter = 0
        self._ref_counter = 0
        self._phone_counter = 0
        self._device_counter = 0


    def name(self) -> str:
        return f"{self.rng.choice(FIRST)} {self.rng.choice(LAST)}"

    def phone(self) -> str:
        self._phone_counter += 1
        return f"080{self.seed % 10}{self._phone_counter:07d}"

    def device(self) -> str:
        self._device_counter += 1
        return f"android-{self.seed:04d}-{self._device_counter:06d}"

    def account(self, *, home: bool = True, name: str | None = None, opened_days_ago: int | None = None,
                tier: int | None = None, merchant: bool = False, label: str | None = None,
                phone: str | None = None, device: str | None = None, bank: str | None = None) -> dict:
        self._acct_counter += 1
        bank = bank or (self.home if home else self.rng.choice(OTHER_BANKS))
        acc = {
            "bank_code": bank,
            "account_no": f"{(self.seed * 7919 + self._acct_counter) % 10**10:010d}",
            "holder_name": name or self.name(),
            "is_merchant": merchant,
            "synthetic_label": label,
        }
        if bank == self.home:
            age = opened_days_ago if opened_days_ago is not None else self.rng.randint(120, 3000)
            acc["opened_at"] = self.end - timedelta(days=age, hours=self.rng.randint(0, 23))
            acc["kyc_tier"] = tier if tier is not None else self.rng.choice([2, 3, 3])
            acc["bvn"] = f"22{self.seed % 100:02d}{self._acct_counter:07d}"
            acc["identifiers"] = [{"kind": "phone", "value": phone or self.phone()},
                                  {"kind": "device", "value": device or self.device()}]
        self.accounts[f"{bank}/{acc['account_no']}"] = acc
        return acc

    def key(self, acc: dict) -> dict:
        return {"bank_code": acc["bank_code"], "account_no": acc["account_no"]}

    def send(self, ts: datetime, src: dict, dst: dict, naira: float, channel: str, narration: str | None = None) -> dict | None:
        if ts > self.end or ts < self.start - timedelta(days=400):
            return None
        self._ref_counter += 1
        t = {"reference": f"SIM{self.seed}-{self._ref_counter:07d}", "ts": ts, "src": self.key(src), "dst": self.key(dst),
             "amount_kobo": int(round(naira)) * 100, "channel": channel, "narration": narration,
             "src_name": src["holder_name"], "dst_name": dst["holder_name"]}
        self.transfers.append(t)
        return t

    def when(self, day_from: float = 0, day_to: float = 28) -> datetime:
        return self.start + timedelta(days=self.rng.uniform(day_from, day_to))


    def build(self, customers: int, rings: int) -> None:
        r = self.rng
        home_customers = [self.account(home=True) for _ in range(int(customers * 0.75))]
        external_customers = [self.account(home=False) for _ in range(customers - len(home_customers))]
        everyone = home_customers + external_customers
        merchants = [self.account(home=r.random() < 0.5, name=f"{r.choice(['Shoprite', 'Mama Put', 'Chicken Republic', 'Pharmacy', 'Fuel Station', 'Supermart', 'Electronics'])} {i}", merchant=True) for i in range(30)]
        agents = [self.account(home=True, name=f"POS Agent {self.name()}", merchant=True) for _ in range(18)]
        atm = self.account(home=True, name="ATM Cash", merchant=True)
        atm["account_no"] = "ATM"
        self.accounts[f"{self.home}/ATM"] = atm
        employers = [self.account(home=r.random() < 0.4, name=f"{r.choice(['Dangote', 'Lagos State', 'Tech Hub', 'Hospital', 'School', 'Logistics'])} Payroll {i}") for i in range(12)]
        suppliers = [self.account(home=False, name=f"Wholesale Supplier {i}") for i in range(10)]

        for c in home_customers:
            emp = r.choice(employers)
            payday = self.when(20, 27)
            salary = r.choice([60_000, 85_000, 120_000, 180_000, 250_000, 400_000, 650_000])
            self.send(payday, emp, c, salary, "nip", "salary")
            for _ in range(r.randint(4, 14)):
                self.send(self.when(), c, r.choice(merchants), r.randint(800, 35_000), "card", "purchase")
            for _ in range(r.randint(1, 6)):
                peer = r.choice(everyone)
                if peer is not c:
                    self.send(self.when(), c, peer, r.randint(2_000, 80_000), r.choice(["mobile", "ussd", "nip"]), "transfer")
            for _ in range(r.randint(1, 4)):
                self.send(self.when(), c, r.choice(agents + [atm]), r.choice([5_000, 10_000, 20_000, 40_000]),
                          r.choice(["pos", "atm", "agent"]), "cash withdrawal")
        for c in external_customers:
            for _ in range(r.randint(0, 3)):
                self.send(self.when(), c, r.choice(home_customers), r.randint(2_000, 120_000), "nip", "transfer")

        # Legitimate look-alikes.
        # Market traders: many small payers, slow supplier payments.
        for _ in range(8):
            trader = self.account(home=True, name=f"{self.name()} Provisions", label="lookalike")
            payers = r.sample(everyone, 30)
            got = 0
            for p in payers:
                amt = r.randint(1_000, 25_000)
                got += amt
                self.send(self.when(), p, trader, amt, "mobile", "goods")
            for wk in range(3):
                self.send(self.start + timedelta(days=7 * wk + 6, hours=r.randint(9, 17)), trader, r.choice(suppliers),
                          int(got * 0.22), "nip", "stock")
        # Ajo and esusu thrift collectors: weekly collection, next-day payout.
        for _ in range(3):
            collector = self.account(home=True, name=f"{self.name()} Ajo", label="lookalike")
            members = r.sample(home_customers, 15)
            for wk in range(4):
                day = self.start + timedelta(days=7 * wk + 1)
                pot = 0
                for mem in members:
                    amt = r.choice([5_000, 10_000, 20_000])
                    pot += amt
                    self.send(day + timedelta(hours=r.uniform(7, 19)), mem, collector, amt, "mobile", "ajo contribution")
                self.send(day + timedelta(days=1, hours=r.uniform(8, 12)), collector, members[wk], pot, "nip", "ajo payout")
        # Families sharing one phone.
        for _ in range(15):
            shared = self.phone()
            a, b = self.account(home=True, phone=shared, label="lookalike"), self.account(home=True, phone=shared, label="lookalike")
            self.send(self.when(), a, b, r.randint(5_000, 50_000), "mobile", "family")
        # Spouses sharing one device.
        for _ in range(5):
            dev = self.device()
            self.account(home=True, device=dev), self.account(home=True, device=dev)
        # Dormant accounts that wake up with small amounts.
        for _ in range(5):
            d = self.account(home=True, opened_days_ago=r.randint(400, 2000), label="lookalike")
            self.send(self.end - timedelta(days=r.randint(150, 320)), r.choice(employers), d, 30_000, "nip", "old credit")
            self.send(self.when(5, 25), r.choice(everyone), d, r.randint(10_000, 150_000), "nip", "transfer")

        styles = ["classic", "dormant_rented", "external_entry", "reported", "slow"]
        for i in range(rings):
            self.ring(styles[i % len(styles)], home_customers, external_customers, agents, atm)


    def ring(self, style: str, home_customers, external_customers, agents, atm) -> None:
        r = self.rng
        slow = style == "slow"
        dev_a, dev_b = self.device(), self.device()
        ph = self.phone()

        def mule(**kw):
            return self.account(label="mule", **kw)

        if style == "dormant_rented":
            collectors = []
            for _ in range(2):
                c = mule(home=True, opened_days_ago=r.randint(500, 1500), tier=2, device=dev_a)
                self.send(self.end - timedelta(days=r.randint(130, 250)), r.choice(home_customers), c, 15_000, "nip", "old")
                collectors.append(c)
        elif style == "external_entry":
            collectors = [mule(home=False)]
        else:
            collectors = [mule(home=True, opened_days_ago=r.randint(3, 20), tier=1, device=dev_a,
                               phone=ph if j == 0 else None) for j in range(r.randint(1, 2))]
        layers = [mule(home=True, opened_days_ago=r.randint(5, 40), tier=r.choice([1, 2]),
                       device=dev_a if j % 2 == 0 else dev_b, phone=ph if j == 0 else None)
                  for j in range(r.randint(2, 4))]
        cashers = [mule(home=True, opened_days_ago=r.randint(2, 25), tier=1, device=dev_b) for _ in range(r.randint(1, 2))]

        attack = self.when(4, 24)
        victims = r.sample(home_customers, r.randint(5, 9)) + r.sample(external_customers, r.randint(2, 5))
        for v in victims:
            v["synthetic_label"] = v.get("synthetic_label") or "victim"
        for v in victims:
            ts = attack + timedelta(hours=r.uniform(0, 40))
            col = r.choice(collectors)
            amount = r.choice([50_000, 85_000, 120_000, 200_000, 350_000, 500_000, 750_000, 900_000]) + r.randint(0, 999)
            t = self.send(ts, v, col, amount, r.choice(["mobile", "ussd", "nip"]), r.choice(SCAM_NARRATIONS))
            if not t:
                continue
            if style == "reported" and r.random() < 0.5:
                self.reports.append({"kind": "victim_complaint", "bank_code": col["bank_code"], "account_no": col["account_no"],
                                     "transfer_reference": t["reference"], "note": "customer reported scam payment",
                                     "reporter": "fraud desk", "ts": ts + timedelta(hours=r.uniform(3, 30))})
            # collector splits into round amounts to layers
            t1 = ts + (timedelta(hours=r.uniform(6, 20)) if slow else timedelta(minutes=r.uniform(4, 45)))
            remaining = int(amount * r.uniform(0.92, 0.98))
            parts = r.randint(2, 4)
            chunk = max(20_000, (remaining // parts) // 10_000 * 10_000)
            hops = []
            sent = 0
            while sent + chunk <= remaining and len(hops) < parts:
                lay = r.choice(layers)
                hops.append((lay, chunk))
                self.send(t1 + timedelta(minutes=r.uniform(0, 20)), col, lay, chunk, "nip", r.choice(["transfer", "refund", "payment"]))
                sent += chunk
            # layers forward to cash-out accounts (or a wallet)
            for lay, amt in hops:
                t2 = t1 + (timedelta(hours=r.uniform(3, 12)) if slow else timedelta(minutes=r.uniform(8, 70)))
                cas = r.choice(cashers)
                fwd = int(amt * r.uniform(0.95, 0.99))
                self.send(t2, lay, cas, fwd, "nip", "transfer")
                # cash-out in chunks
                t3 = t2 + (timedelta(hours=r.uniform(6, 20)) if slow else timedelta(minutes=r.uniform(20, 300)))
                left = fwd
                while left > 15_000:
                    take = min(left, r.choice([20_000, 40_000, 50_000, 100_000]))
                    point = atm if r.random() < 0.3 else r.choice(agents)
                    self.send(t3, cas, point, take, "atm" if point is atm else r.choice(["pos", "agent"]), "cash")
                    t3 += timedelta(minutes=r.uniform(3, 25))
                    left -= take


def generate(seed: int, customers: int, rings: int, home_bank: str) -> Generator:
    g = Generator(seed, home_bank)
    g.build(customers, rings)
    g.transfers.sort(key=lambda t: t["ts"])
    return g
