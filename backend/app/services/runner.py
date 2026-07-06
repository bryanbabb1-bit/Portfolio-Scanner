"""Runner Radar — the anatomy of an explosive low-float mover (the MGRT type).

MGRT ran 1000%+ in weeks on a ~2M-share float. That is a DIFFERENT animal
from a SNDK-style large-cap momentum run: the fuel is a tiny tradeable float,
so a small dollar inflow forces a vertical move. This engine scores names on
the structural + velocity DNA those runners share, and — being a real advisor
— attaches the honest caution: the same thinness that lets them 10x lets them
lose 90% with no bid to sell into. These are lottery-ticket position sizes.

Curated universe of the RIGHT TYPE of stock (low-float, recent-IPO, high-beta
microcaps) — because a large-cap AI book structurally cannot contain the next
MGRT. Bryan can add tickers; the conviction engine also flags any held/watched
name that develops the pattern.
"""
from __future__ import annotations

import re
import time

from ..config import settings
from ..models.schemas import RunnerCandidate
from . import market_data
from .technical import compute_indicators, build_quote

# --------------------------------------------------------- live market movers
# Instead of guessing which 30 names WILL run, scan the whole market for the
# ones that ARE running today and score them. Yahoo's screener returns
# real-time movers with price/%/cap/volume in one cheap call.
_MOVERS_CACHE: dict[str, tuple[float, list[dict]]] = {}
_CLEAN_TICKER = re.compile(r"^[A-Z]{1,5}$")  # US common shares, no .HK/.L/warrants


def _movers_ttl() -> int:
    # Catching ignition EARLY means re-scanning fast while the market's live;
    # off-hours nothing churns so cache long. (Was a flat 10 min — too slow to
    # catch a runner before it's already extended.)
    from .market_data import _market_hours
    return 120 if _market_hours() else 600

# Runner profile floors/ceilings: real small/mid caps, not shells or megacaps.
_MIN_CAP = 30_000_000
_MAX_CAP = 12_000_000_000
_MIN_VOL = 500_000
_MIN_PRICE = 1.0


def _clean_rows(quotes: list[dict]) -> list[dict]:
    out: list[dict] = []
    for q in quotes:
        sym = (q.get("symbol") or "").upper()
        if not _CLEAN_TICKER.match(sym):
            continue  # drop foreign listings, warrants (…W), units (…U)
        cap = q.get("marketCap")
        vol = q.get("regularMarketVolume") or q.get("dayVolume")
        # Use the ACTIVE session's move: a stock gapping +40% pre-market shows
        # its jump in preMarketChangePercent, not the (stale) regular field.
        state = q.get("marketState", "REGULAR")
        if state in ("PRE", "PREPRE") and q.get("preMarketChangePercent") is not None:
            chg = q.get("preMarketChangePercent")
            price = q.get("preMarketPrice") or q.get("regularMarketPrice")
        elif state in ("POST", "POSTPOST", "CLOSED") and q.get("postMarketChangePercent") is not None:
            chg = q.get("postMarketChangePercent")
            price = q.get("postMarketPrice") or q.get("regularMarketPrice")
        else:
            chg = q.get("regularMarketChangePercent")
            price = q.get("regularMarketPrice")
        if cap is None or not (_MIN_CAP <= cap <= _MAX_CAP):
            continue
        if price is None or price < _MIN_PRICE:
            continue
        if vol is None or vol < _MIN_VOL:
            continue
        # Relative volume = the real "something is happening NOW" tell — a fresh
        # catalyst shows up as volume many times the average, EARLY, before the
        # full % move. And where price sits in the day's range tells igniting
        # (near the high) from faded (rolled over off the high).
        avg = q.get("averageDailyVolume3Month") or q.get("averageDailyVolume10Day")
        rvol = round(float(vol) / float(avg), 1) if avg else None
        d_hi, d_lo = q.get("regularMarketDayHigh"), q.get("regularMarketDayLow")
        range_pos = None
        if d_hi and d_lo and d_hi > d_lo:
            range_pos = round((float(price) - float(d_lo)) / (float(d_hi) - float(d_lo)), 2)
        out.append({
            "symbol": sym,
            "name": q.get("shortName") or q.get("longName") or sym,
            "change_pct": round(float(chg), 1) if chg is not None else 0.0,
            "market_cap": float(cap),
            "price": float(price),
            "volume": float(vol),
            "avg_vol": float(avg) if avg else None,
            "rvol": rvol,             # x average daily volume
            "range_pos": range_pos,   # 1.0 = at day high (strong), 0 = at day low (faded)
        })
    return out


def live_movers(force: bool = False) -> list[dict]:
    """Whole-market runner candidates that are moving NOW, deduped + filtered.

    Blends a custom small/mid-cap-up-big query with Yahoo's day_gainers,
    small_cap_gainers and most_actives. Cached 10 min. Empty on any failure
    (mock mode, blocked egress) — the curated universe still shows."""
    if settings.DATA_MODE == "mock":
        return []
    hit = _MOVERS_CACHE.get("movers")
    if hit and not force and (time.time() - hit[0]) < _movers_ttl():
        return hit[1]

    rows: dict[str, dict] = {}
    try:
        import yfinance as yf
        from yfinance import EquityQuery as Q

        custom = Q("and", [
            Q("gt", ["percentchange", 6]),   # catch ignition early, not at +25%
            Q("lt", ["intradaymarketcap", _MAX_CAP]),
            Q("gt", ["intradaymarketcap", _MIN_CAP]),
            Q("gt", ["dayvolume", _MIN_VOL]),
        ])
        sources = [custom, "day_gainers", "small_cap_gainers", "most_actives"]
        for src in sources:
            try:
                kw = {"count": 50}
                if not isinstance(src, str):
                    kw.update(sortField="percentchange", sortAsc=False)
                res = yf.screen(src, **kw)
                for r in _clean_rows(res.get("quotes", []) if isinstance(res, dict) else []):
                    rows.setdefault(r["symbol"], r)
            except Exception as exc:
                print(f"[runner] screener {src!r} failed: {exc!r}")
    except Exception as exc:
        print(f"[runner] live movers unavailable: {exc!r}")

    result = sorted(rows.values(), key=lambda r: -r["change_pct"])
    _MOVERS_CACHE["movers"] = (time.time(), result)
    return result


# Ignition tuning — catch the START of the move, while there's still runway.
_IGNITION_MIN = 7      # a real move underway (was 25 = already exhausted)
_EXTENDED_PCT = 25     # beyond this the bulk of the day's move is usually done
_RVOL_MIN = 3.0        # unusual volume = a live catalyst, not drift
_RUNNER_MAX_CAP = 6_000_000_000


def _stage(m: dict) -> str | None:
    """Classify a live mover: 'igniting' (early, buyable with runway) vs
    'extended' (already ran / faded — do NOT chase). None = not a runner."""
    chg = m["change_pct"]
    rvol = m.get("rvol")
    rp = m.get("range_pos")
    if chg < _IGNITION_MIN:
        return None
    # Demand unusual volume for the EARLY band; a small % pop on normal volume
    # is noise. (Big % moves pass even if avg-vol data is missing.)
    if chg < _EXTENDED_PCT and rvol is not None and rvol < _RVOL_MIN:
        return None
    faded = rp is not None and rp < 0.4   # rolled well off the day's high
    if chg >= _EXTENDED_PCT or faded:
        return "extended"
    return "igniting"


def igniting_movers(limit: int = 4) -> list[dict]:
    """Live movers worth a slap, EARLY. Returns each tagged with 'stage':
    'igniting' names (up ~7-25% on heavy volume, still near highs — buyable
    with runway) are slapped first; 'extended' names (already ran / faded) are
    surfaced as do-not-chase awareness, not buy signals. Cheap: screener
    payload only, no per-ticker fetch."""
    staged: list[dict] = []
    for m in live_movers():
        if not (_MIN_CAP <= m["market_cap"] <= _RUNNER_MAX_CAP):
            continue
        if m["volume"] < 750_000:
            continue
        st = _stage(m)
        if st:
            staged.append({**m, "stage": st})
    # Igniting first, ranked by conviction (relative volume x momentum);
    # extended only fills remaining slots, ranked by size of move.
    igniting = sorted(
        (m for m in staged if m["stage"] == "igniting"),
        key=lambda m: -((m.get("rvol") or 1.0) * m["change_pct"]))
    extended = sorted(
        (m for m in staged if m["stage"] == "extended"),
        key=lambda m: -m["change_pct"])
    picks = (igniting + extended)[:limit]
    if igniting:
        print(f"[runner] {len(igniting)} igniting + {len(extended)} extended; "
              f"slapping {len(picks)} (igniting first)")
    return picks

# (symbol, name) — genuinely low-float / recent-IPO / high-velocity names.
# This is the *type* to fish in, not a buy list.
UNIVERSE: list[tuple[str, str]] = [
    ("MGRT", "Mega Fortune"), ("SNDK", "Sandisk"), ("AAOI", "Applied Optoelectronics"),
    ("SOUN", "SoundHound AI"), ("RGTI", "Rigetti Computing"), ("QBTS", "D-Wave Quantum"),
    ("IONQ", "IonQ"), ("QUBT", "Quantum Computing"), ("LAES", "SEALSQ"),
    ("BBAI", "BigBear.ai"), ("KULR", "KULR Technology"), ("NNE", "Nano Nuclear Energy"),
    ("OKLO", "Oklo"), ("SMR", "NuScale Power"), ("ASTS", "AST SpaceMobile"),
    ("RKLB", "Rocket Lab"), ("ACHR", "Archer Aviation"), ("JOBY", "Joby Aviation"),
    ("SERV", "Serve Robotics"), ("PONY", "Pony AI"), ("TEM", "Tempus AI"),
    ("CRML", "Critical Metals"), ("MARA", "MARA Holdings"), ("WULF", "TeraWulf"),
    ("APLD", "Applied Digital"), ("CIFR", "Cipher Mining"), ("HUT", "Hut 8"),
    ("VRT", "Vertiv"), ("POWL", "Powell Industries"), ("CRDO", "Credo Technology"),
]


def _score(ind, quote, structure: dict | None) -> tuple[float, list[str], str]:
    """0-100 explosive-setup score + the teachable reasons + stage."""
    s = 0.0
    reasons: list[str] = []
    st = structure or {}
    float_shares = st.get("float_shares")
    float_pct = st.get("float_pct")
    short = st.get("short_pct_float")
    hist_days = st.get("history_days")

    # ---- STRUCTURE (the fuel): up to 45 pts. A tiny float is the whole game.
    if float_shares:
        m = float_shares / 1e6
        if m <= 10:
            s += 35; reasons.append(f"Tiny {m:.0f}M-share float — MGRT ran on ~2M")
        elif m <= 20:
            s += 26; reasons.append(f"Low {m:.0f}M-share float — thin, moves fast")
        elif m <= 50:
            s += 15; reasons.append(f"Modest {m:.0f}M-share float")
        elif m <= 100:
            s += 6
    if float_pct is not None and float_pct <= 40:
        s += 6; reasons.append(f"Only {float_pct:.0f}% of shares float (insider-heavy)")
    if hist_days is not None and hist_days <= 260:
        s += 4; reasons.append("Recent IPO — little overhead supply")

    # ---- VELOCITY (the ignition): up to 40 pts.
    vr = ind.volume_ratio or 0
    if vr >= 4:
        s += 20; reasons.append(f"Volume {vr:.1f}x average — heavy accumulation")
    elif vr >= 2:
        s += 13; reasons.append(f"Volume {vr:.1f}x average")
    elif vr >= 1.5:
        s += 6
    r5 = ind.ret_5d_pct or 0
    r20 = ind.ret_20d_pct or 0
    if r5 >= 25:
        s += 14; reasons.append(f"+{r5:.0f}% in 5 days — already igniting")
    elif r5 >= 12:
        s += 9; reasons.append(f"+{r5:.0f}% in 5 days")
    elif r20 >= 30:
        s += 6; reasons.append(f"+{r20:.0f}% in 20 days — building")
    if ind.pct_from_52w_high is not None and ind.pct_from_52w_high >= -8:
        s += 6; reasons.append("At/near 52-week highs — blue-sky breakout")

    # ---- ACCELERANT: short squeeze fuel (up to 9 pts).
    if short is not None and short >= 0.20:
        s += 9; reasons.append(f"{short*100:.0f}% of float short — squeeze fuel")
    elif short is not None and short >= 0.10:
        s += 5; reasons.append(f"{short*100:.0f}% of float short")

    # ---- stage from where velocity/RSI sit
    rsi = ind.rsi
    if rsi is not None and rsi >= 82:
        stage = "extended"
    elif r5 >= 15 or vr >= 3:
        stage = "igniting"
    elif rsi is not None and rsi < 45 and r20 < 5:
        stage = "cooling"
    else:
        stage = "coiled"

    return round(min(s, 100), 1), reasons[:5], stage


def _caution(stage: str, float_shares) -> str:
    thin = float_shares and float_shares <= 20e6
    if stage == "extended":
        return ("Extended and vertical — chasing here is where bagholders are "
                "made. Wait for a higher-low, size tiny, hard stop.")
    if thin:
        return ("Thin float cuts both ways: a 10x setup is also a -90% trap "
                "with no bid. Lottery-ticket size only (<=1% of book), "
                "predefine your exit before entry.")
    return ("Momentum name — volume-confirm the entry and trail a stop; "
            "these reverse as fast as they run.")


def evaluate(symbol: str, name: str | None, md, theme: str | None = None) -> RunnerCandidate:
    ind = compute_indicators(md.history)
    quote = build_quote(md, ind)
    st = md.structure or {}
    score, reasons, stage = _score(ind, quote, st)
    return RunnerCandidate(
        symbol=symbol.upper(),
        name=name or quote.name,
        theme=theme,
        price=quote.price,
        change_pct=quote.change_pct,
        runner_score=score,
        stage=stage,
        float_shares=st.get("float_shares"),
        market_cap=st.get("market_cap"),
        short_pct_float=st.get("short_pct_float"),
        float_pct=st.get("float_pct"),
        recent_ipo=bool(st.get("history_days") and st["history_days"] <= 260),
        volume_ratio=ind.volume_ratio,
        ret_5d_pct=ind.ret_5d_pct,
        ret_20d_pct=ind.ret_20d_pct,
        rsi=ind.rsi,
        reasons=reasons,
        caution=_caution(stage, st.get("float_shares")),
    )


def radar(min_score: float = 0.0, limit: int = 40,
          extra: list[str] | None = None) -> dict:
    """Score the live market movers + curated seeds (+ user tickers).

    The universe is now dynamic: today's actual runners from the whole-market
    screener, so we score what IS moving instead of guessing what might."""
    movers = live_movers()
    live_count = len(movers)

    syms: list[tuple[str, str | None]] = []
    seen: set[str] = set()

    def push(sym: str, name: str | None):
        sym = sym.upper().strip()
        if sym and sym not in seen:
            syms.append((sym, name))
            seen.add(sym)

    for m in movers[:45]:          # today's real runners, hottest first
        push(m["symbol"], m["name"])
    for s, n in UNIVERSE:          # permanent watch seeds
        push(s, n)
    for e in (extra or []):        # user-added tickers
        push(e, None)

    market_data.warm_cache([s for s, _ in syms], max_workers=12)
    cands: list[RunnerCandidate] = []
    for sym, name in syms:
        try:
            md = market_data.get_market_data(sym)
            cands.append(evaluate(sym, name, md))
        except Exception as exc:
            print(f"[runner] skipping {sym}: {exc!r}")

    cands = [c for c in cands if c.runner_score >= min_score]
    cands.sort(key=lambda c: c.runner_score, reverse=True)
    source = "mock" if settings.DATA_MODE == "mock" else "live"
    return {"count": len(cands), "universe": len(syms),
            "live_movers": live_count, "source": source,
            "results": cands[:limit]}
