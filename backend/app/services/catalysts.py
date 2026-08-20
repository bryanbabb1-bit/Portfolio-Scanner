"""The partner trade hiding inside a holding.

WHY THIS IS NOT A CALENDAR
--------------------------
The obvious version of this feature is a list of dated events: "MRK reports
Phase 3 data on 14 October". That version does not work, and the trial that
started this tells you why.

On 2026-08-19 Moderna ran 177% on positive Phase 3 melanoma data from
INTerpath-001. That trial is NCT05933577. Its registered primary completion
date is 2029-10-26 — three years and two months AFTER it read out — and the
registry entry had not been touched since 2025-09-24. A calendar keyed on
completion dates would have had that event listed under 2029, if at all.

Event-driven oncology endpoints do not read out on a date. They read out when
the event count is hit, which is usually at a pre-specified interim analysis,
which can land years early. Anyone selling a biotech "catalyst calendar" built
on primary completion dates is selling a schedule the trials do not follow.

WHAT THE REGISTRY ACTUALLY KNEW
-------------------------------
Since 2023-07-06 the registry has said, in public, that Merck was running a
PHASE 3 trial with ModernaTX as its collaborator. That fact needed no
prediction and had no expiry. It sat there for three years.

And it was the whole trade. On the day the data landed, MRK — which was in the
book — rose 12.6%. MRNA, the partner, rose 177%. Same news, 14x the move,
because the partner was 14x the smaller company. Owning the sponsor of a
successful trial pays; owning its small partner pays enormously.

So this module builds a MAP, not a schedule: for every late-stage trial run by
a company in the book, which investable public company is on the other side of
it, and how much smaller is it. No date is predicted, because no date can be.
The dates the registry does carry are passed through and clearly labelled as
what they are — a plan, not a forecast.

WHAT IT DELIBERATELY LEAVES OUT
-------------------------------
Collaborators that cannot be bought (the NCI, universities, hospital networks,
cooperative groups, foundations) and contract research organisations running
the trial as a vendor rather than betting their own molecule on it. A CRO is
paid either way; it is not leverage on the result.
"""
from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request

from ..config import settings

API = "https://clinicaltrials.gov/api/v2/studies"
_FILE = settings.PORTFOLIO_FILE.parent / "catalysts.json"
_RESOLVED_FILE = settings.PORTFOLIO_FILE.parent / "catalyst_partners.json"
TTL = 24 * 3600            # the registry moves daily at most
RESOLVE_TTL = 30 * 86400   # a company's ticker does not change often

# Late-stage only. A Phase 1 partner is a lottery ticket on a lottery ticket.
PHASES = "3"
# Enrolment closed but the trial is still running: the state an interim
# readout comes from, and the state INTerpath-001 was in when it read out.
# COMPLETED is fetched too but kept only if it completed recently — a trial
# that finished in 2013 is history, not a catalyst.
STATUSES = ("ACTIVE_NOT_RECRUITING", "COMPLETED")
COMPLETED_WITHIN_DAYS = 180
# Below this, a "partner" is almost always a bad name match rather than a real
# biotech, and even when real it is not the trade this module is looking for.
MIN_PARTNER_CAP = 300_000_000

# A holding's name in the trial registry, which is rarely its ticker's name:
# Merck files as "Merck Sharp & Dohme". Only names that actually run trials
# belong here — this is a lookup table, not an aspiration.
SPONSOR_ALIASES: dict[str, list[str]] = {
    "MRK": ["Merck Sharp & Dohme"],
    "LLY": ["Eli Lilly and Company"],
    "ISRG": ["Intuitive Surgical"],
    "ABBV": ["AbbVie"],
    "PFE": ["Pfizer"],
    "AZN": ["AstraZeneca"],
    "BMY": ["Bristol-Myers Squibb"],
    "JNJ": ["Janssen Research & Development", "Johnson & Johnson"],
    "AMGN": ["Amgen"],
    "GILD": ["Gilead Sciences"],
    "REGN": ["Regeneron Pharmaceuticals"],
    "VRTX": ["Vertex Pharmaceuticals"],
    "BIIB": ["Biogen"],
    "NVO": ["Novo Nordisk"],
    "SNY": ["Sanofi"],
    "GSK": ["GlaxoSmithKline", "GSK"],
    "MRNA": ["ModernaTX"],
    "BNTX": ["BioNTech"],
    "NVS": ["Novartis"],
    "RHHBY": ["Hoffmann-La Roche"],
}

# Collaborators that exist but cannot be traded, or that are paid a fee rather
# than exposed to the result.
_NOT_INVESTABLE = re.compile(
    r"\b(university|universit|college|institute|institut|hospital|clinic|"
    r"foundation|trust|charity|centre|center|network|consortium|cooperative|"
    r"group|society|association|ministry|department|national|federal|nhs|"
    r"nci|nih|fda|who|academy|school|council|alliance|organisation|organization|"
    r"ppd|iqvia|parexel|syneos|covance|medpace|icon plc|labcorp|fortrea)\b",
    re.I,
)

# Corporate noise to strip before asking "what is this company's ticker".
_SUFFIXES = re.compile(
    r"\b(inc|llc|ltd|limited|co|corp|corporation|plc|gmbh|ag|sa|nv|bv|ab|as|"
    r"aps|oy|kk|kgaa|spa|srl|pty|holdings?|group|company|companies|"
    r"pharmaceuticals?|pharma|therapeutics|biosciences?|biotech|sciences?|"
    r"laboratories|labs?|research|development|global|international|usa|us|"
    r"america|americas)\b\.?",
    re.I,
)

# US listings and US-traded ADRs. A German or Japanese line of the same company
# is the same bet in a currency and a session Bryan cannot trade.
_US_EXCHANGES = {"NMS", "NYQ", "NGM", "NCM", "ASE", "PCX", "PNK", "OQB", "OQX", "BTS"}


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
        print(f"[catalysts] persist failed: {exc!r}")


# ------------------------------------------------------------------ registry
def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "portfolio-scanner"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.load(r)


def fetch_trials(sponsor: str, phases: str = PHASES,
                 statuses: tuple[str, ...] = STATUSES) -> list[dict]:
    """Every late-stage trial the registry attributes to `sponsor`."""
    out: list[dict] = []
    for status in statuses:
        token = None
        while True:
            q = {
                "query.spons": sponsor,
                "aggFilters": f"phase:{phases}",
                "filter.overallStatus": status,
                "pageSize": "100",
                "fields": ("NCTId,BriefTitle,OverallStatus,Phase,LeadSponsorName,"
                           "CollaboratorName,PrimaryCompletionDate,"
                           "LastUpdatePostDate,Condition"),
            }
            if token:
                q["pageToken"] = token
            try:
                d = _get(f"{API}?{urllib.parse.urlencode(q)}")
            except Exception as exc:
                print(f"[catalysts] {sponsor} / {status}: {exc!r}")
                break
            out.extend(d.get("studies") or [])
            token = d.get("nextPageToken")
            if not token:
                break
    return out


def _flatten(study: dict) -> dict:
    p = study.get("protocolSection") or {}
    ident = p.get("identificationModule") or {}
    stat = p.get("statusModule") or {}
    spons = p.get("sponsorCollaboratorsModule") or {}
    design = p.get("designModule") or {}
    cond = (p.get("conditionsModule") or {}).get("conditions") or []
    return {
        "nct": ident.get("nctId"),
        "title": ident.get("briefTitle"),
        "status": stat.get("overallStatus"),
        "primary_completion": (stat.get("primaryCompletionDateStruct") or {}).get("date"),
        "last_update": (stat.get("lastUpdatePostDateStruct") or {}).get("date"),
        "phases": design.get("phases") or [],
        "sponsor": (spons.get("leadSponsor") or {}).get("name"),
        "collaborators": [c.get("name") for c in (spons.get("collaborators") or [])
                          if c.get("name")],
        "conditions": cond[:3],
    }


# ------------------------------------------------------------------ partners
def _clean(name: str) -> str:
    """A registry company name, reduced to something a ticker search knows."""
    s = re.sub(r"[.,]", " ", name or "")
    s = re.sub(r"\(.*?\)", " ", s)
    s = _SUFFIXES.sub(" ", s)
    # "ModernaTX" -> "Moderna": a trailing capitalised tag glued to the name.
    s = re.sub(r"([a-z])(TX|RX|Bio|Rx)\b", r"\1", s)
    return re.sub(r"\s+", " ", s).strip(" -&")


def investable(name: str, exclude: set[str]) -> bool:
    """Could you actually take a position in this collaborator?"""
    if not name:
        return False
    if _NOT_INVESTABLE.search(name):
        return False
    cleaned = _clean(name).lower()
    if len(cleaned) < 3:
        return False
    # The sponsor listing itself as its own collaborator is not a partner.
    return cleaned not in {_clean(x).lower() for x in exclude}


def resolve_ticker(name: str) -> str | None:
    """Registry company name -> US-traded ticker, or None if not listed here.

    None is a real answer and gets cached: Seagen and Dermira return nothing
    because they were acquired, and a partner that no longer trades is not a
    trade. Re-asking daily would just be slower.
    """
    cache = _read(_RESOLVED_FILE)
    key = _clean(name).lower()
    hit = cache.get(key)
    if hit and time.time() - float(hit.get("ts", 0)) < RESOLVE_TTL:
        return hit.get("ticker")

    ticker = None
    try:
        import yfinance as yf

        cleaned = _clean(name)
        if not cleaned:
            return None
        # The WHOLE cleaned name has to lead the company's name. Matching on
        # the first word alone produced Canadian Solar as the partner on an
        # antipsychotics trial, and a 1,065x "leverage" to go with it.
        want = cleaned.lower()
        for row in (yf.Search(cleaned, max_results=8).quotes or []):
            if row.get("quoteType") != "EQUITY":
                continue
            if row.get("exchange") not in _US_EXCHANGES:
                continue
            sym = (row.get("symbol") or "").upper()
            # ALPMF / OPHLF style five-letter "F" lines are foreign ordinaries:
            # quoted here, barely traded here. A sponsored ADR (…Y) is fine.
            if len(sym) == 5 and sym.endswith("F"):
                continue
            short = (row.get("shortname") or row.get("longname") or "").lower()
            if not short.startswith(want):
                continue
            ticker = row.get("symbol")
            break
    except Exception as exc:
        print(f"[catalysts] ticker lookup for {name!r} failed: {exc!r}")
        return None            # a failed lookup is not a cacheable "no"

    cache[key] = {"ticker": ticker, "name": name, "ts": time.time()}
    _write(_RESOLVED_FILE, cache)
    return ticker


def market_cap(symbol: str) -> float | None:
    try:
        import yfinance as yf

        fi = yf.Ticker(symbol).fast_info
        cap = getattr(fi, "market_cap", None)
        return float(cap) if cap else None
    except Exception:
        return None


def _still_live(t: dict) -> bool:
    """Could this trial still produce news, or is it already history?

    ACTIVE_NOT_RECRUITING is the interesting state: enrolment is shut, the
    clock is running, and an interim analysis can land at any time — it is the
    state INTerpath-001 was in on the morning it moved Moderna 177%. A
    COMPLETED trial only matters if it completed recently enough that the
    readout has not been published yet.
    """
    status = (t.get("status") or "").upper()
    if status not in ("ACTIVE_NOT_RECRUITING", "COMPLETED"):
        return False
    done = _as_epoch(t.get("primary_completion"))
    if done is None:
        # No date at all. Only trust it if enrolment is closed and running.
        return status == "ACTIVE_NOT_RECRUITING"
    age_days = (time.time() - done) / 86400
    if age_days > COMPLETED_WITHIN_DAYS:
        # The primary endpoint date is long past. Whatever this trial had to
        # say, it said — an ACTIVE_NOT_RECRUITING status this old means
        # long-term follow-up, not a pending readout. Six Myriad Genetics rows
        # from 2016-2020 were the entire top of the list before this gate.
        return False
    return True


def _as_epoch(date: str | None) -> float | None:
    """A registry date (YYYY, YYYY-MM or YYYY-MM-DD) as a timestamp."""
    try:
        parts = [int(x) for x in (date or "").split("-")]
    except (ValueError, TypeError):
        return None
    if not parts:
        return None
    while len(parts) < 3:
        parts.append(1)
    try:
        return time.mktime((parts[0], parts[1], parts[2], 0, 0, 0, 0, 1, -1))
    except (ValueError, TypeError, OverflowError):
        return None


# ---------------------------------------------------------------------- map
def build(symbols: list[str]) -> dict:
    """The catalyst map for a set of held symbols."""
    rows: list[dict] = []
    covered: list[str] = []
    caps: dict[str, float | None] = {}

    for sym in symbols:
        aliases = SPONSOR_ALIASES.get(sym.upper())
        if not aliases:
            continue                      # no registry presence — not a miss
        covered.append(sym.upper())
        if sym.upper() not in caps:
            caps[sym.upper()] = market_cap(sym)

        seen: set[str] = set()
        for alias in aliases:
            for study in fetch_trials(alias):
                t = _flatten(study)
                if not t["nct"] or t["nct"] in seen:
                    continue
                seen.add(t["nct"])
                if not _still_live(t):
                    continue
                partners = []
                for c in t["collaborators"]:
                    if not investable(c, exclude=set(aliases) | {t["sponsor"] or ""}):
                        continue
                    tk = resolve_ticker(c)
                    if not tk or tk.upper() == sym.upper():
                        continue
                    if tk not in caps:
                        caps[tk] = market_cap(tk)
                    own = caps.get(sym.upper())
                    theirs = caps.get(tk)
                    if theirs is not None and theirs < MIN_PARTNER_CAP:
                        continue
                    partners.append({
                        "name": c,
                        "symbol": tk,
                        "market_cap": theirs,
                        # How much more this news would move them than you.
                        # The whole point: same result, smaller company.
                        "leverage": round(own / theirs, 1)
                        if own and theirs and theirs > 0 else None,
                    })
                if not partners:
                    continue
                rows.append({**t, "holding": sym.upper(), "partners": partners})

    # Biggest leverage first — that is the ranking that matters, since every
    # row here is already a late-stage trial on a name in the book.
    def rank(r):
        vals = [p["leverage"] for p in r["partners"] if p["leverage"]]
        live = 1 if (r.get("status") or "").upper() == "ACTIVE_NOT_RECRUITING" else 0
        return (live, max(vals) if vals else 0)

    rows.sort(key=rank, reverse=True)
    return {
        "ts": time.time(),
        "covered": covered,
        "uncovered": [s.upper() for s in symbols
                      if s.upper() not in SPONSOR_ALIASES],
        "trials": rows,
        "note": ("Registry dates are a plan, not a forecast: the Phase 3 that "
                 "moved MRNA 177% on 2026-08-19 was registered to complete in "
                 "2029. Rank by leverage, not by date."),
    }


def get(force: bool = False, symbols: list[str] | None = None) -> dict:
    """Cached map. The registry updates daily at most, so this does too."""
    cached = _read(_FILE)
    if not force and cached and time.time() - float(cached.get("ts", 0)) < TTL:
        return {**cached, "cached": True}

    if symbols is None:
        from . import portfolio as pf_service
        cfg = pf_service.load_portfolio()
        symbols = [h["symbol"] for h in cfg.get("holdings", [])]
        symbols += [w["symbol"] for w in cfg.get("watchlist", [])]

    out = build(symbols)
    _write(_FILE, out)
    return {**out, "cached": False}
