"""The complete list of US-listed symbols, from the exchanges themselves.

WHY NOT THE YAHOO SCREENER
--------------------------
Yahoo's screener caps a page at 25 rows and throttles a deep paging walk by
answering with an EMPTY page rather than an error — so a scan silently truncates
and reports 0.4% coverage as though it had finished. Three separate screens in
this app produced conclusions from a keyhole before that was noticed.

Nasdaq Trader publishes the authoritative lists as plain pipe-delimited files,
free and without a key:

    nasdaqlisted.txt   every Nasdaq-listed security
    otherlisted.txt    NYSE, NYSE American, Arca, BATS, IEX

That is the actual landscape. Cached for a day because listings change slowly,
and a stale-by-hours universe is infinitely better than a 25-name one.

WHAT GETS DROPPED, AND WHY
--------------------------
Test issues, ETFs, warrants, units, rights, preferreds and anything flagged for
delinquent filings. A screen looking for a beaten-down operating company turning
around should not be handed a warrant on a SPAC.
"""
from __future__ import annotations

import json
import time
import urllib.request

from ..config import settings

_FILES = {
    "nasdaq": "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
    "other": "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
}
_CACHE_FILE = settings.PORTFOLIO_FILE.parent / "universe_cache.json"
_TTL = 24 * 3600

# Suffix letters that mark a security as something other than common stock.
# Fifth-letter conventions: W warrant, R right, U unit, P/Q/etc preferred.
_BAD_SUFFIX = ("W", "R", "U", "P", "Q", "Z")


def _fetch(url: str) -> list[str]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", "replace").splitlines()


def _parse(lines: list[str], kind: str) -> list[str]:
    if not lines:
        return []
    header = lines[0].split("|")
    idx = {name: i for i, name in enumerate(header)}
    out: list[str] = []
    for line in lines[1:]:
        if line.startswith("File Creation Time"):
            break
        parts = line.split("|")
        if len(parts) < len(header):
            continue

        def col(name, default=""):
            i = idx.get(name)
            return parts[i].strip() if i is not None and i < len(parts) else default

        if col("Test Issue") == "Y":
            continue
        if col("ETF") == "Y":
            continue
        sym = col("Symbol") or col("ACT Symbol")
        if not sym or not sym.isalpha():
            continue          # drops warrants/units/rights carrying . or $
        # Nasdaq's fifth letter encodes security class; anything but common
        # stock is noise for this purpose.
        if len(sym) == 5 and sym[-1] in _BAD_SUFFIX:
            continue
        if col("Financial Status") not in ("", "N"):
            continue          # delinquent / deficient filers
        out.append(sym.upper())
    return out


def all_symbols(force: bool = False) -> list[str]:
    """Every US-listed common stock, deduped. Cached for a day."""
    if not force:
        try:
            with open(_CACHE_FILE, encoding="utf-8") as f:
                blob = json.load(f)
            if time.time() - blob.get("ts", 0) < _TTL and blob.get("symbols"):
                return blob["symbols"]
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    symbols: set[str] = set()
    for kind, url in _FILES.items():
        try:
            symbols.update(_parse(_fetch(url), kind))
        except Exception as exc:
            print(f"[universe] {kind} fetch failed: {exc!r}")

    out = sorted(symbols)
    if out:
        try:
            _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump({"ts": time.time(), "symbols": out}, f)
        except OSError as exc:
            print(f"[universe] cache write failed: {exc!r}")
    return out
