"""Large files import in the background, in batches, with progress, and give the same result
as the regular import."""
import time
from datetime import timedelta

import pytest

from app.core.timeutil import now

HEADER = "SessionID,TransactionDate,SourceInstitutionCode,OriginatorAccountNumber,OriginatorName,DestinationInstitutionCode,BeneficiaryAccountNumber,BeneficiaryName,Amount,ChannelCode,Narration\n"


def nip_file(n: int, bad_every: int = 0) -> bytes:
    t0 = now() - timedelta(days=3)
    lines = [HEADER]
    for i in range(n):
        ts = (t0 + timedelta(seconds=7 * i)).strftime("%Y-%m-%d %H:%M:%S")
        amount = "abc" if bad_every and i % bad_every == 0 else f"{1000 + i % 500}.00"
        lines.append(f"S{i:09d},{ts},999,{1000000000 + i % 4000:010d},Payer {i % 4000},058,"
                     f"{2000000000 + i % 1500:010d},Payee {i % 1500},{amount},3,test\n")
    return "".join(lines).encode()


@pytest.fixture(autouse=True)
def clean(client):
    client.post("/network/reset")
    yield


def wait(client, job_id: str, timeout: float = 120) -> dict:
    end = time.time() + timeout
    while time.time() < end:
        j = client.get(f"/network/import/jobs/{job_id}").json()
        if j["status"] in ("done", "failed"):
            return j
        time.sleep(0.2)
    raise AssertionError("import job did not finish")


def test_large_file_imports_in_batches(client):
    data = nip_file(30_000, bad_every=1000)
    job = client.post("/network/import/nip/job", files={"file": ("big.csv", data)}).json()
    assert job["status"] in ("queued", "reading") and job["size_bytes"] == len(data)
    done = wait(client, job["id"])
    assert done["status"] == "done", done
    assert done["rows"] == 30_000 and done["transfers_added"] == 30_000 - 30 and done["error_count"] == 30
    # Four payers only appear in the broken rows.
    assert done["errors"] and done["progress"] == 1.0 and done["accounts_added"] == 4000 + 1500 - 4
    assert client.get("/network/summary").json()["transfers_in_window"] == 29_970
    again = wait(client, client.post("/network/import/nip/job", files={"file": ("big.csv", data)}).json()["id"])
    assert again["transfers_added"] == 0 and again["transfers_skipped"] == 29_970, "re-running the same file adds nothing"


def test_background_and_regular_import_agree(client):
    data = nip_file(2_000)
    small = client.post("/network/import/nip", files={"file": ("s.csv", data)}).json()
    client.post("/network/reset")
    big = wait(client, client.post("/network/import/nip/job", files={"file": ("s.csv", data)}).json()["id"])
    assert small["transfers_added"] == big["transfers_added"] == 2_000


def test_check_only_saves_nothing(client):
    j = wait(client, client.post("/network/import/nip/job", files={"file": ("s.csv", nip_file(500))}, data={"dry_run": "true"}).json()["id"])
    assert j["valid"] == 500 and j["transfers_added"] == 0
    assert client.get("/network/summary").json()["transfers_in_window"] == 0


def test_missing_columns_fail_cleanly(client):
    j = wait(client, client.post("/network/import/nip/job", files={"file": ("x.csv", b"a,b\n1,2\n")}).json()["id"])
    assert j["status"] == "failed" and j["rows"] == 0 and "do not match" in j["message"] and "a, b" in j["errors"][1]["error"]


def test_one_sided_labelled_dataset_is_explained(client):
    data = b"transaction_id,customer_id,timestamp,amount,channel,is_fraud\nT1,C1,2023-01-01 10:00:00,500,Mobile,0\n"
    j = wait(client, client.post("/network/import/nip/job", files={"file": ("d.csv", data)}).json()["id"])
    assert j["status"] == "failed" and "no recipient account" in j["message"] and "labelled transaction dataset" in j["message"]
    assert len(j["message"]) <= 300


def test_file_where_no_row_is_valid_fails(client):
    j = wait(client, client.post("/network/import/nip/job", files={"file": ("b.csv", nip_file(20, bad_every=1))}).json()["id"])
    assert j["status"] == "failed" and j["error_count"] == 20


def test_other_formats_are_refused(client):
    assert client.post("/network/import/pacs008/job", files={"file": ("x.xml", b"<x/>")}).status_code == 422
