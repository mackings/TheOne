/** Naira amounts, Lagos dates and percentages, formatted the same way everywhere. */
export const naira = (kobo: number | null | undefined) =>
  kobo == null ? "–" : `₦${(kobo / 100).toLocaleString("en-NG", { maximumFractionDigits: 0 })}`;
export const nairaExact = (kobo: number) => `₦${(kobo / 100).toLocaleString("en-NG", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
// One pattern everywhere, in Lagos time, day first: "6 Oct 2026, 10:09 PM".
const LAGOS = "Africa/Lagos";
export const fmtDate = (iso: string | null | undefined) => {
  if (!iso) return "–";
  const p = Object.fromEntries(
    new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit", hour12: true, timeZone: LAGOS })
      .formatToParts(new Date(iso))
      .map((x) => [x.type, x.value]),
  );
  return `${p.day} ${p.month} ${p.year}, ${p.hour}:${p.minute} ${String(p.dayPeriod).toUpperCase()}`;
};
export const fmtDay = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleDateString("en-NG", { day: "numeric", month: "short", year: "numeric", timeZone: LAGOS }) : "–";
export function timeAgo(iso: string | null | undefined) {
  if (!iso) return "–";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
}
export const pct = (v: number | null | undefined) => (v == null ? "–" : `${Math.round(v * 100)}%`);

/** "Ring 100004": the number analysts quote, or a short id for rings saved before numbering. */
export const ringName = (r: { id: string; number?: number | null }) => (r.number ? `Ring ${r.number}` : `Ring ${r.id.slice(0, 8)}`);

// Bank codes as they appear in Nigerian transfer records (CBN and NIBSS institution codes).
export const BANKS: Record<string, string> = {
  "044": "Access Bank", "023": "Citibank", "050": "Ecobank", "070": "Fidelity Bank", "011": "First Bank", "214": "FCMB",
  "058": "GTBank", "030": "Heritage Bank", "301": "Jaiz Bank", "082": "Keystone Bank", "076": "Polaris Bank",
  "101": "Providus Bank", "221": "Stanbic IBTC", "068": "Standard Chartered", "232": "Sterling Bank", "032": "Union Bank",
  "033": "UBA", "215": "Unity Bank", "035": "Wema Bank", "057": "Zenith Bank", "50515": "Moniepoint", "100004": "OPay",
  "100033": "PalmPay", "50211": "Kuda",
};

/** A bank's name from its code, or "bank 123" when the code is not a known bank. */
export const bankName = (code: string) => BANKS[code] ?? (code.startsWith("ST-") ? "from a statement" : `bank ${code}`);

/** "0043602762 · GTBank", or "· our bank" for accounts held with us. */
export const accountLine = (accountNo: string, bankCode: string, home?: boolean) =>
  `${accountNo} · ${home ? "our bank" : bankName(bankCode)}`;
