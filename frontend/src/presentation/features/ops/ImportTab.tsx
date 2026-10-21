"use client";

/** Import bank data: small files inline, large NIP and CSV files as background jobs with progress. */

import { Database, UploadCloud } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Button, DataTable, Field, Input, Kpi, KpiStrip, Section, Select, useToast } from "@/presentation/components/ui";
import { cx } from "@/presentation/cx";
import { importRoute, jobFinished } from "@/application/imports";
import type { ImportJob, ImportResult } from "@/domain/network";
import { useNetwork } from "@/presentation/hooks/gateways";

const FORMATS = [
  { value: "nip", label: "Bank transfer records: NIP (CSV)", hint: "SessionID, TransactionDate, SourceInstitutionCode, OriginatorAccountNumber, DestinationInstitutionCode, BeneficiaryAccountNumber, Amount, ChannelCode, Narration." },
  { value: "csv", label: "Any list of transfers (CSV)", hint: "reference, timestamp, src_bank, src_account, dst_bank, dst_account, amount, channel. Rename columns with a JSON mapping." },
  { value: "pacs008", label: "Interbank payment messages: ISO 20022 (XML)", hint: "FIToFICstmrCdtTrf with EndToEndId, IntrBkSttlmAmt in NGN, debtor and creditor accounts and agents." },
  { value: "obn_accounts", label: "Account details: Open Banking (JSON)", hint: "Open Banking Nigeria Account objects: accountNumber, fullName, bvn, phoneNumber, accountOpeningDate." },
  { value: "obn_statement", label: "Account statement: Open Banking (JSON)", hint: "getStatement lines: referenceId, amount, debitOrCredit, bookDate. Payment history only, no counterparty." },
];

const MB = (n: number) => `${(n / 1024 / 1024).toLocaleString("en-NG", { maximumFractionDigits: n > 100 * 1024 * 1024 ? 0 : 1 })} MB`;

function JobProgress({ job, upload, size, name }: { job: ImportJob | null; upload: number | null; size: number; name: string }) {
  const stage =
    upload != null ? "Uploading" : !job ? "Starting" : job.status === "queued" ? "Waiting to start" : job.status === "reading" ? (job.dry_run ? "Reading and checking rows" : "Reading and saving rows")
      : job.status === "analysing" ? "Checking every account again" : job.status === "done" ? (job.dry_run ? "Checked" : "Finished") : "Stopped";
  const frac = upload != null ? upload : job?.status === "analysing" || job?.status === "done" ? 1 : job?.progress ?? 0;
  const tone = job?.status === "failed" ? "var(--critical)" : job?.status === "done" ? "var(--good)" : "var(--brand)";
  return (
    <Section title={`${job?.dry_run ? "Checking" : "Importing"} ${name}`} description={`${MB(size)} · large files are handled in batches in the background, so you can leave this page.`}>
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium">{stage}</span>
        <span className="tabular-nums text-[var(--muted)]">{Math.round(frac * 100)}%</span>
      </div>
      <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-[var(--track)]" role="progressbar" aria-valuenow={Math.round(frac * 100)} aria-valuemin={0} aria-valuemax={100}>
        <div className="h-2 rounded-full transition-[width] duration-500" style={{ width: `${frac * 100}%`, background: tone }} />
      </div>
      {job?.status === "analysing" && <p className="mt-2 text-xs text-[var(--muted)]">All rows are saved. Re-scoring every account can take a few minutes for very large files.</p>}
      {job?.message && (
        <div className="mt-3 rounded-[6px] border border-[var(--critical)] bg-[var(--critical-soft)] px-3 py-2 text-sm">
          {job.message}
          {job.transfers_added > 0 && " Rows saved before this are kept; importing the same file again skips them."}
        </div>
      )}
    </Section>
  );
}

export function ImportTab({ onDone }: { onDone: () => void }) {
  const net = useNetwork();
  const toast = useToast();
  const [fmtName, setFmt] = useState("nip");
  const [file, setFile] = useState<File | null>(null);
  const [mapping, setMapping] = useState("");
  const [bankCode, setBankCode] = useState("");
  const [accountNo, setAccountNo] = useState("");
  const [result, setResult] = useState<ImportResult | null>(null);
  const [busy, setBusy] = useState<"check" | "import" | null>(null);
  const [drag, setDrag] = useState(false);
  const [job, setJob] = useState<ImportJob | null>(null);
  const [upload, setUpload] = useState<number | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const f = FORMATS.find((x) => x.value === fmtName)!;
  const route = file ? importRoute(fmtName, file.size) : "inline";

  function choose(x: File | null | undefined) {
    setFile(x ?? null);
    setResult(null);
    setJob(null);
  }

  // Poll a background import until it finishes.
  const jobId = job?.id;
  const running = !!job && !jobFinished(job);
  useEffect(() => {
    if (!jobId || !running) return;
    const t = setInterval(() => {
      net.importJob(jobId).then((j) => {
        setJob(j);
        if (j.status === "done") {
          setBusy(null);
          if (j.dry_run) toast.info("File checked", `${j.valid.toLocaleString()} of ${j.rows.toLocaleString()} rows are valid.`);
          else {
            toast[j.error_count ? "warning" : "success"]("Import finished", `${j.transfers_added.toLocaleString()} payments added, ${j.error_count.toLocaleString()} rows could not be read.`);
            onDone();
          }
        } else if (j.status === "failed") {
          setBusy(null);
          toast.error("Import stopped", j.message ?? "the import failed; rows saved so far are kept");
        }
      }).catch(() => {});
    }, 1500);
    return () => clearInterval(t);
  }, [net, jobId, running, toast, onDone]);

  async function runBig(dry: boolean) {
    if (!file) return;
    setBusy(dry ? "check" : "import");
    setResult(null);
    setUpload(0);
    try {
      const j = await net.startImportJob(fmtName, file, { mapping: mapping || undefined, bank_code: bankCode || undefined, dry_run: dry }, setUpload);
      setJob(j);
    } catch (e) {
      toast.error("Upload failed", (e as Error).message);
      setBusy(null);
    } finally {
      setUpload(null);
    }
  }

  async function run(dry: boolean) {
    if (!file) return;
    if (route === "too_large") return toast.error("File too large for this format", "Files over 40 MB import in the background for NIP and CSV. Split XML or JSON files.");
    if (route === "background") return runBig(dry);
    setBusy(dry ? "check" : "import");
    try {
      const r = await net.importFile(fmtName, file, { mapping: mapping || undefined, bank_code: bankCode || undefined, account_no: accountNo || undefined, dry_run: dry });
      setResult(r);
      if (dry) toast.info("File checked", `${r.valid} of ${r.rows} rows are valid.`);
      else {
        const loaded = (r.transfers_added ?? 0) + (r.statement_lines_added ?? 0) + (r.accounts ?? 0);
        toast[r.errors.length ? "warning" : "success"]("Import finished", `${loaded} records added. ${r.errors.length} rows could not be read.`);
        onDone();
      }
    } catch (e) {
      toast.error("Import failed", (e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <Section title="Upload a file" description="Check a file first, then import it. Duplicates are skipped.">
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="grid content-start gap-3">
            <Field label="Type of file" hint={`Columns TheOne looks for: ${f.hint}`}>
              <Select value={fmtName} onChange={(e) => { setFmt(e.target.value); setResult(null); }} options={FORMATS.map((x) => ({ value: x.value, label: x.label }))} />
            </Field>
            {fmtName === "csv" && (
              <Field label="Different column names? (optional)">
                <Input value={mapping} onChange={(e) => setMapping(e.target.value)} placeholder='{"reference": "TxnRef", "amount": "Naira"}' className="font-mono text-xs" />
              </Field>
            )}
            {(fmtName.startsWith("obn") || fmtName === "csv") && (
              <Field label={fmtName === "csv" ? "Bank code, if the file has no bank columns" : "Bank code, defaults to your bank"}>
                <Input value={bankCode} onChange={(e) => setBankCode(e.target.value)} inputMode="numeric" />
              </Field>
            )}
            {fmtName === "obn_statement" && (
              <Field label="Account number, if lines omit it">
                <Input value={accountNo} onChange={(e) => setAccountNo(e.target.value)} inputMode="numeric" />
              </Field>
            )}
          </div>
          <div
            className={cx(
              "flex min-h-44 cursor-pointer flex-col items-center justify-center gap-2 rounded-[6px] border-2 border-dashed px-6 py-8 text-center transition-colors",
              drag ? "border-[var(--brand)] bg-[var(--brand-soft)]" : "border-[var(--line-strong)] bg-[var(--surface-2)] hover:border-[var(--ink-2)]",
            )}
            onClick={() => input.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => { e.preventDefault(); setDrag(false); choose(e.dataTransfer.files?.[0]); }}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => e.key === "Enter" && input.current?.click()}
          >
            <UploadCloud className="size-8 text-[var(--muted)]" />
            {file ? (
              <>
                <div className="break-all text-sm font-semibold">{file.name}</div>
                <div className="text-xs text-[var(--muted)]">{file.size > 1024 * 1024 ? MB(file.size) : `${(file.size / 1024).toFixed(1)} KB`} · click to choose another</div>
                {route !== "inline" && <div className="text-xs font-medium text-[var(--ink-2)]">{route === "background" ? "Large file: it will import in the background with progress" : "Too large for this format; split the file"}</div>}
              </>
            ) : (
              <>
                <div className="text-sm font-semibold">Drop a file here, or click to choose</div>
                <div className="text-xs text-[var(--muted)]">NIP and CSV files of any size · XML and JSON up to 50 MB</div>
              </>
            )}
            <input ref={input} type="file" className="hidden" onChange={(e) => choose(e.target.files?.[0])} />
          </div>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button disabled={!file} loading={busy === "check"} onClick={() => run(true)}>Check file</Button>
          <Button variant="primary" icon={Database} disabled={!file || busy === "check"} loading={busy === "import"} onClick={() => run(false)}>Import</Button>
        </div>
      </Section>
      {(job || upload != null) && file && <JobProgress job={job} upload={upload} size={file.size} name={file.name} />}
      {job && (job.rows > 0 || job.errors.length > 0) && (
        <>
          {job.rows > 0 && <KpiStrip cols={4}>
            <Kpi label="Rows read" value={job.rows.toLocaleString()} />
            <Kpi label="Readable" value={job.valid.toLocaleString()} />
            <Kpi label="Could not be read" value={job.error_count.toLocaleString()} />
            <Kpi label="Added" value={job.dry_run ? "Check only" : job.transfers_added.toLocaleString()}
              sub={job.transfers_skipped ? `${job.transfers_skipped.toLocaleString()} already present` : job.accounts_added ? `${job.accounts_added.toLocaleString()} new accounts` : undefined} />
          </KpiStrip>}
          {job.errors.length > 0 && (
            <Section title={job.rows ? "Rows that could not be read" : "What was found"} flush description={job.error_count > job.errors.length ? `Showing the first ${job.errors.length} of ${job.error_count.toLocaleString()}.` : undefined}>
              <DataTable
                rows={job.errors.map((e, i) => ({ ...e, i }))}
                rowKey={(e) => String(e.i)}
                pageSize={10}
                columns={[
                  { key: "row", header: job.rows ? "Row" : "Line", width: "90px", render: (e) => <span className="font-mono">{e.row ?? "–"}</span> },
                  { key: "err", header: "Problem", render: (e) => e.error },
                ]}
              />
            </Section>
          )}
        </>
      )}
      {result && (
        <>
          <KpiStrip cols={4}>
            <Kpi label="Rows read" value={result.rows.toLocaleString()} />
            <Kpi label="Readable" value={result.valid.toLocaleString()} />
            <Kpi label="Could not be read" value={result.errors.length} />
            <Kpi
              label="Added"
              value={result.dry_run ? "Check only" : ((result.transfers_added ?? 0) + (result.statement_lines_added ?? 0) + (result.accounts ?? 0)).toLocaleString()}
              sub={result.transfers_skipped ? `${result.transfers_skipped} already present` : undefined}
            />
          </KpiStrip>
          {result.errors.length > 0 && (
            <Section title="Rows that could not be read" flush>
              <DataTable
                rows={result.errors.map((e, i) => ({ ...e, i }))}
                rowKey={(e) => String(e.i)}
                pageSize={10}
                columns={[
                  { key: "row", header: "Row", width: "90px", sort: (e) => e.row, render: (e) => <span className="font-mono">{e.row}</span> },
                  { key: "err", header: "Problem", render: (e) => e.error },
                ]}
              />
            </Section>
          )}
        </>
      )}
    </>
  );
}
