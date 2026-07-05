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

from ..models.schemas import RunnerCandidate
from . import market_data
from .technical import compute_indicators, build_quote

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
    """Score the curated runner universe (+ any user-added tickers)."""
    from . import portfolio as pf_service

    syms: list[tuple[str, str | None]] = [(s, n) for s, n in UNIVERSE]
    seen = {s for s, _ in syms}
    for e in (extra or []):
        e = e.upper().strip()
        if e and e not in seen:
            syms.append((e, None))
            seen.add(e)

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
    source = "mock" if any(
        market_data.get_market_data(c.symbol).source == "mock"
        for c in cands[:1]) else "live"
    return {"count": len(cands), "universe": len(syms),
            "source": source, "results": cands[:limit]}
