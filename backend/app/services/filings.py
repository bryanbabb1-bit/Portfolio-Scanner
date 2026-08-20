"""Material events, filed. Every name in the book, not just the pharma ones.

WHY THIS EXISTS
---------------
The trial map answers "what could move a holding hard" for three names, because
clinicaltrials.gov is a pharma registry and twenty-one of the twenty-four names
in this book do not run clinical trials. Bryan's question was the obvious one:
catalysts exist for all companies, so what covers the rest?

Two cheaper generalisations were tried first and both failed, which is worth
recording so neither gets rebuilt:

  1. FIND PARTNERS FROM PRICE. If MRK and MRNA share a trial, maybe the tape
     shows it. It does not. Regressing every US listing on MRK through
     2026-08-18 — the day before the readout — ranked MRNA 891st of 5,756 by
     beta, at a correlation of 0.11 and an R-squared of 0.01. The link was
     structural, not statistical: it existed in a contract and expressed itself
     exactly once, on the day the data landed. Day to day the two names trade
     on unrelated things. A correlation screen cannot see a latent relationship.

  2. FIND PARTNERS FROM FILING TEXT. EDGAR full-text search does surface real
     dependencies — "Microsoft accounted for" finds Applied Optoelectronics —
     but the phrasing is not standardised ("NVIDIA represented" returns nothing,
     "NVIDIA" returns 158 filings that merely say the word). A co-sponsored
     Phase 3 is a contract; a mention in an annual report is a word. Shipping
     the second dressed as the first would be the kind of feature that looks
     like coverage and is not.

So this does not try to generalise partner discovery, which has no free
structured source outside pharma. It generalises EVENT COVERAGE instead, which
does: an 8-K is, by SEC definition, a company telling the market that something
material happened, and every US issuer files them. Item codes make the event
type machine-readable, so a merger and a routine shareholder vote do not arrive
looking the same.

WHAT THIS IS NOT
----------------
It is not early. An 8-K is filed at or shortly after the event and companies
almost always issue a press release at the same time, so this is concurrent
with the news, not ahead of it. What it is: complete, structured, primary, and
filtered to the names you actually own — which is more than the news wire
manages.
"""
from __future__ import annotations

import json
import time
import urllib.request

from ..config import settings

# The SEC asks for a contact in the User-Agent and rate-limits to 10 requests a
# second. Both are conditions of use, not suggestions.
UA = "portfolio-scanner (bryan.babb1@gmail.com)"
TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik}.json"

_FILE = settings.PORTFOLIO_FILE.parent / "filings.json"
_CIK_FILE = settings.PORTFOLIO_FILE.parent / "sec_ciks.json"
TTL = 3600                 # filings post through the day
CIK_TTL = 30 * 86400
LOOKBACK_DAYS = 30
REQUEST_GAP = 0.12         # stay under the SEC's 10/sec

# What an 8-K item code actually means, and whether it is worth your attention.
# "high" is a thing that changes the investment case. "routine" is the company
# filing because it must — annual meeting results, an exhibit index. Earnings
# (2.02) sits in the middle deliberately: it matters, but the earnings runway
# panel already told you it was coming, so it is never news here.
ITEMS: dict[str, tuple[str, str]] = {
    "1.01": ("Signed a material agreement", "high"),
    "1.02": ("Terminated a material agreement", "high"),
    "1.03": ("Bankruptcy or receivership", "high"),
    "1.04": ("Mine safety disclosure", "routine"),
    "2.01": ("Completed an acquisition or disposal", "high"),
    "2.02": ("Reported results", "medium"),
    "2.03": ("Took on a financial obligation", "medium"),
    "2.04": ("Triggered acceleration of an obligation", "high"),
    "2.05": ("Exit or disposal costs", "medium"),
    "2.06": ("Material impairment", "high"),
    "3.01": ("Delisting notice or listing-rule failure", "high"),
    "3.02": ("Sold unregistered equity (dilution)", "medium"),
    "3.03": ("Changed shareholder rights", "medium"),
    "4.01": ("Changed auditor", "medium"),
    "4.02": ("Prior financials can no longer be relied on", "high"),
    "5.01": ("Change of control", "high"),
    "5.02": ("Officer or director change", "high"),
    "5.03": ("Amended articles or bylaws", "routine"),
    "5.07": ("Shareholder vote results", "routine"),
    "5.08": ("Shareholder director nominations", "routine"),
    "7.01": ("Reg FD disclosure", "medium"),
    "8.01": ("Other material event", "medium"),
    "9.01": ("Financial statements and exhibits", "routine"),
}

# Forms worth surfacing beyond the 8-K. An activist stake or a fresh shelf
# offering moves a stock and neither is an 8-K.
EXTRA_FORMS: dict[str, tuple[str, str]] = {
    "SC 13D": ("Activist stake disclosed", "high"),
    "SC 13D/A": ("Activist stake changed", "medium"),
    "424B5": ("Priced a securities offering (dilution)", "high"),
    "S-3": ("Filed a shelf registration", "medium"),
    "S-3ASR": ("Filed an automatic shelf registration", "medium"),
}

RANK = {"high": 0, "medium": 1, "routine": 2}


# ------------------------------------------------------------------- storage
def _read(path) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _write(path, data: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except OSError as exc:
        print(f"[filings] persist failed: {exc!r}")


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept-Encoding": "gzip, deflate"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            import gzip
            raw = gzip.decompress(raw)
        return json.loads(raw.decode("utf-8"))


# ----------------------------------------------------------------------- cik
def cik_for(symbol: str) -> str | None:
    """Ticker -> zero-padded CIK, from the SEC's own mapping file."""
    cache = _read(_CIK_FILE)
    if not cache or time.time() - float(cache.get("ts", 0)) > CIK_TTL:
        try:
            raw = _get(TICKER_MAP_URL)
        except Exception as exc:
            print(f"[filings] ticker map failed: {exc!r}")
            return (cache.get("map") or {}).get(_norm(symbol))
        cache = {"ts": time.time(),
                 "map": {str(v["ticker"]).upper(): str(v["cik_str"]).zfill(10)
                         for v in raw.values()}}
        _write(_CIK_FILE, cache)
    return (cache.get("map") or {}).get(_norm(symbol))


def _norm(symbol: str) -> str:
    # The book writes BRK.B; the SEC writes BRK-B.
    return (symbol or "").upper().replace(".", "-").strip()


# ------------------------------------------------------------------- filings
def _classify(form: str, items: str) -> tuple[list[str], str]:
    """Plain-English labels for a filing, and how much it matters."""
    form = (form or "").upper()
    if form in EXTRA_FORMS:
        label, sev = EXTRA_FORMS[form]
        return [label], sev
    labels, sev = [], "routine"
    for code in [c.strip() for c in (items or "").split(",") if c.strip()]:
        label, s = ITEMS.get(code, (f"Item {code}", "medium"))
        labels.append((label, s))
        if RANK[s] < RANK[sev]:
            sev = s
    # Item 9.01 rides along on nearly every 8-K. Once there is anything real to
    # report, "Financial statements and exhibits" is packaging, not news.
    keep = [lbl for lbl, s in labels if s != "routine"] or [lbl for lbl, _ in labels]
    return keep, sev


def for_symbol(symbol: str, days: int = LOOKBACK_DAYS) -> list[dict]:
    """Recent material filings for one ticker, newest first."""
    cik = cik_for(symbol)
    if not cik:
        return []
    try:
        d = _get(SUBMISSIONS.format(cik=cik))
    except Exception as exc:
        print(f"[filings] {symbol}: {exc!r}")
        return []

    recent = (d.get("filings") or {}).get("recent") or {}
    forms = recent.get("form") or []
    cutoff = time.strftime("%Y-%m-%d", time.localtime(time.time() - days * 86400))
    out: list[dict] = []
    for i, form in enumerate(forms):
        date = (recent.get("filingDate") or [""] * len(forms))[i]
        if date < cutoff:
            continue
        f = (form or "").upper()
        if not (f.startswith("8-K") or f in EXTRA_FORMS):
            continue
        items = (recent.get("items") or [""] * len(forms))[i]
        labels, sev = _classify(f, items)
        accession = (recent.get("accessionNumber") or [""] * len(forms))[i]
        out.append({
            "symbol": symbol.upper(),
            "company": d.get("name"),
            "form": f,
            "date": date,
            "items": [c.strip() for c in (items or "").split(",") if c.strip()],
            "labels": labels,
            "severity": sev,
            "accession": accession,
            "url": (f"https://www.sec.gov/Archives/edgar/data/"
                    f"{int(cik)}/{accession.replace('-', '')}/"
                    f"{accession}-index.htm") if accession else None,
        })
    return out


def build(symbols: list[str], days: int = LOOKBACK_DAYS) -> dict:
    rows: list[dict] = []
    missing: list[str] = []
    for sym in symbols:
        if not cik_for(sym):
            missing.append(sym.upper())
            continue
        rows.extend(for_symbol(sym, days))
        time.sleep(REQUEST_GAP)
    # Newest first, and within a day the things that matter above the paperwork.
    rows.sort(key=lambda r: (r["date"], -RANK[r["severity"]]), reverse=True)
    return {
        "ts": time.time(),
        "days": days,
        "filings": rows,
        "no_cik": missing,
        "note": ("An 8-K is the company telling the market something material "
                 "happened. It is filed with the press release, not before it — "
                 "this is complete and structured, not early."),
    }


def get(force: bool = False, symbols: list[str] | None = None,
        days: int = LOOKBACK_DAYS) -> dict:
    cached = _read(_FILE)
    if not force and cached and time.time() - float(cached.get("ts", 0)) < TTL:
        return {**cached, "cached": True}

    if symbols is None:
        from . import portfolio as pf_service
        cfg = pf_service.load_portfolio()
        symbols = [h["symbol"] for h in cfg.get("holdings", [])]
        symbols += [w["symbol"] for w in cfg.get("watchlist", [])]

    seen_before = {f["accession"] for f in (cached.get("filings") or [])
                   if f.get("accession")}
    out = build(symbols, days)
    # Only ever push the first time a filing is seen, and only when it matters.
    # A 5.07 shareholder-vote result buzzing the phone is how notifications
    # get muted, and a muted channel cannot deliver the one that counts.
    fresh = [f for f in out["filings"]
             if f["accession"] not in seen_before and f["severity"] == "high"]
    out["new_material"] = [f["accession"] for f in fresh]
    _write(_FILE, out)

    if fresh and seen_before:      # never push the whole backlog on first run
        try:
            from . import push
            for f in fresh[:4]:
                push.send(
                    f"{f['symbol']} filed an 8-K",
                    f"{'; '.join(f['labels'])} — {f['company']}",
                    data={"type": "filing", "symbol": f["symbol"]},
                )
        except Exception as exc:
            print(f"[filings] push failed: {exc!r}")

    return {**out, "cached": False}
