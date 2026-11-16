"""Download each bank's earnings 8-K exhibits (EX-99.x) from SEC EDGAR.

Usage:
  export SEC_USER_AGENT="Your Name your@email.com"   # SEC requires a contact UA
  python -m beval.fetch --check     # confirm CIK -> company names
  python -m beval.fetch             # download exhibits to filings/<TICKER>/

Picks the first 8-K with Item 2.02 (Results of Operations) filed within 50 days
after the quarter end in config/banks.json. Filings are not committed to git;
filings/<TICKER>/meta.json records the exact URLs so anyone can re-fetch.
"""

import argparse
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "config" / "banks.json").read_text())


def session() -> requests.Session:
    ua = os.environ.get("SEC_USER_AGENT")
    if not ua:
        sys.exit("Set SEC_USER_AGENT='Your Name you@email.com' (SEC fair-access rule).")
    s = requests.Session()
    s.headers.update({"User-Agent": ua, "Accept-Encoding": "gzip, deflate"})
    return s


def get(s, url, **kw):
    for attempt in range(4):
        r = s.get(url, timeout=30, **kw)
        if r.status_code == 200:
            time.sleep(0.15)  # stay well under SEC's 10 req/s limit
            return r
        time.sleep(1.5 * (attempt + 1))
    r.raise_for_status()


def submissions(s, cik: int) -> dict:
    return get(s, f"https://data.sec.gov/submissions/CIK{cik:010d}.json").json()


def find_earnings_8k(sub: dict, quarter_end: dt.date) -> dict | None:
    rec = sub["filings"]["recent"]
    hits = []
    for i, form in enumerate(rec["form"]):
        if form not in ("8-K", "8-K/A"):
            continue
        filed = dt.date.fromisoformat(rec["filingDate"][i])
        if not (quarter_end < filed <= quarter_end + dt.timedelta(days=50)):
            continue
        if "2.02" not in (rec.get("items", [""] * len(rec["form"]))[i] or ""):
            continue
        hits.append({"accession": rec["accessionNumber"][i], "filed": rec["filingDate"][i], "form": form})
    hits.sort(key=lambda h: (h["form"] != "8-K", h["filed"]))  # original 8-K first, earliest
    return hits[0] if hits else None


def exhibit_links(s, cik: int, accession: str) -> list[dict]:
    nodash = accession.replace("-", "")
    idx = f"https://www.sec.gov/Archives/edgar/data/{cik}/{nodash}/{accession}-index.htm"
    soup = BeautifulSoup(get(s, idx).text, "lxml")
    out = []
    for row in soup.select("table.tableFile tr"):
        cells = row.find_all("td")
        if len(cells) < 4:
            continue
        doc_type = cells[3].get_text(strip=True).upper()
        a = cells[2].find("a")
        if a and doc_type.startswith("EX-99"):
            href = a["href"].replace("/ix?doc=", "")
            out.append({"type": doc_type, "url": "https://www.sec.gov" + href,
                        "description": cells[1].get_text(strip=True)})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="only verify CIK -> name")
    ap.add_argument("--only", nargs="*", help="tickers to fetch")
    args = ap.parse_args()

    s = session()
    qend = dt.date.fromisoformat(CONFIG["quarter_end"])
    for bank in CONFIG["banks"]:
        if args.only and bank["ticker"] not in args.only:
            continue
        sub = submissions(s, bank["cik"])
        if args.check:
            print(f"{bank['ticker']:5} config={bank['name']!r:40} edgar={sub.get('name')!r}")
            continue
        hit = find_earnings_8k(sub, qend)
        if not hit:
            print(f"{bank['ticker']}: no Item 2.02 8-K found after {qend} -- swap this bank (see plan).")
            continue
        exhibits = exhibit_links(s, bank["cik"], hit["accession"])
        if not exhibits:
            print(f"{bank['ticker']}: 8-K {hit['accession']} has no EX-99 exhibits")
            continue
        d = ROOT / "filings" / bank["ticker"]
        d.mkdir(parents=True, exist_ok=True)
        for ex in exhibits:
            name = ex["type"].lower().replace(".", "_") + Path(ex["url"]).suffix
            (d / name).write_bytes(get(s, ex["url"]).content)
            ex["file"] = name
        meta = {**bank, **hit, "exhibits": exhibits,
                "fetched_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
        (d / "meta.json").write_text(json.dumps(meta, indent=2))
        print(f"{bank['ticker']}: {hit['accession']} filed {hit['filed']} -> {[e['file'] for e in exhibits]}")


if __name__ == "__main__":
    main()
