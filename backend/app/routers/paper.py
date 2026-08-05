"""Paper-trading simulation endpoints."""
from __future__ import annotations

import json
import statistics as st
import time

from fastapi import APIRouter

from ..config import settings
from ..services import paper as paper_service

router = APIRouter(prefix="/api/paper", tags=["paper"])

_CACHE_FILE = settings.PORTFOLIO_FILE.parent / "paper_backtest.json"
# The replay pulls 60 days of 5-minute bars for twenty symbols, so it is far too
# slow to run on a page load.
_TTL = 12 * 3600


def _significance(trades: list[dict]) -> dict:
    """Is the result distinguishable from luck?

    A profit curve means nothing without this. An expectancy of +0.09R on 53
    trades and one of +0.09R on 500 trades are completely different claims, and
    only the second is evidence.
    """
    rs = [t["r_multiple"] for t in trades if t.get("r_multiple") is not None]
    if len(rs) < 2:
        return {"n": len(rs), "verdict": "not enough trades to say anything"}
    mean, sd = st.mean(rs), st.stdev(rs)
    se = sd / (len(rs) ** 0.5)
    t_stat = mean / se if se else 0.0
    # Trades needed to resolve an edge THIS SIZE at 95% confidence.
    #
    # Only meaningful for a POSITIVE measured edge: "how long until we can prove
    # -0.04R" is not a question anyone wants answered, and a plausible-looking
    # session count next to a losing expectancy reads as a plan when it is
    # nothing of the kind. Past a thousand trades the honest answer is that no
    # realistic run settles it, so this reports nothing rather than a number.
    needed = None
    if mean > 1e-6:
        n_needed = int((2 * sd / mean) ** 2)
        needed = n_needed if n_needed <= 1000 else None
    return {
        "n": len(rs),
        "mean_r": round(mean, 3),
        "sd_r": round(sd, 3),
        "std_error": round(se, 3),
        "t_stat": round(t_stat, 2),
        "significant": abs(t_stat) >= 2.0,
        "trades_needed_for_95pct": needed,
        "verdict": ("edge is statistically significant" if abs(t_stat) >= 2.0
                    else "indistinguishable from zero — not proven"),
    }


def _load_cached() -> dict | None:
    try:
        with open(_CACHE_FILE, encoding="utf-8") as f:
            blob = json.load(f)
        if time.time() - blob.get("cached_at", 0) < _TTL:
            return blob
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return None


@router.get("/backtest")
def backtest(force: bool = False):
    """Replay the rule set over the deepest intraday history available.

    This runs BEFORE any forward paper trading. Spending two to four weeks
    forward-testing a rule set that never had an edge spends the two to four
    weeks and learns nothing.
    """
    if not force:
        cached = _load_cached()
        if cached:
            return cached

    res = paper_service.backtest()
    # Keep the curve out of the payload; it is ~30k points and the page charts
    # daily closes, not every five-minute mark.
    daily: dict[str, float] = {}
    for point in res.equity_curve:
        daily[point["time"][:10]] = point["equity"]

    blob = {
        "cached_at": time.time(),
        "config": res.config,
        "metrics": res.metrics,
        "significance": _significance(res.trades),
        "blocked": res.blocked,
        "days": res.days,
        "symbols": res.symbols,
        "trades": res.trades,
        "daily_equity": [{"day": d, "equity": e} for d, e in sorted(daily.items())],
        "trades_per_session": round(len(res.trades) / max(res.days, 1), 2),
    }
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(blob, f, indent=2)
    except OSError as exc:
        print(f"[paper] could not cache backtest: {exc!r}")
    return blob


_SWING_CACHE = settings.PORTFOLIO_FILE.parent / "swing_backtest.json"


def _benchmark(curve: list[dict], years: float) -> dict:
    """Buy-and-hold SPY over the identical window.

    Without this a CAGR is a number with nothing to be better than. A strategy
    that trails the index it could have simply bought is a hobby, however good
    its t-statistic looks.
    """
    import datetime as dt

    from ..services import market_data

    if not curve:
        return {}
    try:
        spy = market_data.get_deep_history("SPY", years=5)
        if spy.source != "live":
            return {}
        h = spy.history
        a = dt.date.fromisoformat(curve[0]["day"])
        b = dt.date.fromisoformat(curve[-1]["day"])
        win = h[(h.index.date >= a) & (h.index.date <= b)]
        if win.empty:
            return {}
        p0, p1 = float(win["Close"].iloc[0]), float(win["Close"].iloc[-1])
        peak = dd = 0.0
        for v in win["Close"]:
            peak = max(peak, float(v))
            dd = max(dd, (peak - float(v)) / peak)
        return {
            "symbol": "SPY",
            "return_pct": round((p1 / p0 - 1) * 100, 2),
            "cagr_pct": round(((p1 / p0) ** (1 / years) - 1) * 100, 2) if years > 0.5 else None,
            "max_drawdown_pct": round(dd * 100, 2),
        }
    except Exception as exc:
        print(f"[paper] benchmark failed: {exc!r}")
        return {}


def _by_year(curve: list[dict]) -> list[dict]:
    """Per-calendar-year strategy return against the same year of SPY.

    The headline number hides the whole character of this model — it is
    counter-cyclical, and only a year-by-year split shows that.
    """
    import datetime as dt

    from ..services import market_data

    out: list[dict] = []
    if not curve:
        return out
    equity = {c["day"]: c["equity"] for c in curve}
    days = sorted(equity)
    try:
        h = market_data.get_deep_history("SPY", years=5).history
    except Exception:
        h = None
    for yr in sorted({d[:4] for d in days}):
        span = [d for d in days if d.startswith(yr)]
        if len(span) < 20:
            continue
        row = {"year": yr,
               "strategy_pct": round((equity[span[-1]] / equity[span[0]] - 1) * 100, 1),
               "benchmark_pct": None}
        if h is not None:
            win = h[(h.index.date >= dt.date.fromisoformat(span[0]))
                    & (h.index.date <= dt.date.fromisoformat(span[-1]))]
            if not win.empty:
                row["benchmark_pct"] = round(
                    (float(win["Close"].iloc[-1]) / float(win["Close"].iloc[0]) - 1) * 100, 1)
        out.append(row)
    return out


@router.get("/swing")
def swing_backtest(force: bool = False):
    """The multi-day model — the one with a measurable edge.

    Replaces day trading, which the intraday backtest showed could not work on
    this account: PDT-blocked, settlement-throttled, and physically unable to
    risk more than ~0.23% per trade against a 2% budget.
    """
    if not force:
        try:
            with open(_SWING_CACHE, encoding="utf-8") as f:
                blob = json.load(f)
            if time.time() - blob.get("cached_at", 0) < _TTL:
                return blob
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    from ..services import swing as swing_service

    res = swing_service.backtest(years=5)
    years = res.extra.get("years") or 5
    blob = {
        "cached_at": time.time(),
        "config": res.config,
        "metrics": res.metrics,
        "extra": res.extra,
        "significance": _significance(res.trades),
        "benchmark": _benchmark(res.daily_equity, years),
        "by_year": _by_year(res.daily_equity),
        "blocked": res.blocked,
        "days": res.days,
        "symbols": res.symbols,
        "trades": res.trades,
        "daily_equity": res.daily_equity[::5],   # weekly points are enough to plot
    }
    try:
        _SWING_CACHE.parent.mkdir(parents=True, exist_ok=True)
        with open(_SWING_CACHE, "w", encoding="utf-8") as f:
            json.dump(blob, f, indent=2)
    except OSError as exc:
        print(f"[paper] could not cache swing backtest: {exc!r}")
    return blob


_REGIME_CACHE = settings.PORTFOLIO_FILE.parent / "regime_backtest.json"


@router.get("/regime")
def regime_backtest(force: bool = False, years: int = 15):
    """The regime model over 15 years, split in half.

    The out-of-sample half is reported separately and was used to choose
    nothing. A backtest without that split only tells you what already happened.
    """
    if not force:
        try:
            with open(_REGIME_CACHE, encoding="utf-8") as f:
                blob = json.load(f)
            if time.time() - blob.get("cached_at", 0) < _TTL:
                return blob
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    import datetime as dt

    from ..services import market_data
    from ..services import regime as regime_service
    from ..services import swing as swing_service
    from ..services.regime import RegimeConfig

    frames = regime_service.load_frames(swing_service.UNIVERSE, years=years)
    if "SPY" not in frames:
        return {"error": "no live SPY history — cannot establish the regime"}

    spy = frames["SPY"]
    days = sorted({ts.date() for d in frames.values() for ts in d.index})
    mid = days[len(days) // 2]

    def bench(a: dt.date, b: dt.date) -> dict:
        w = spy[(spy.index.date >= a) & (spy.index.date <= b)]
        if w.empty:
            return {}
        p0, p1 = float(w["Close"].iloc[0]), float(w["Close"].iloc[-1])
        yrs = len(w) / 252
        peak = dd = 0.0
        for v in w["Close"]:
            peak = max(peak, float(v))
            dd = max(dd, (peak - float(v)) / peak)
        return {"cagr_pct": round(((p1 / p0) ** (1 / yrs) - 1) * 100, 2),
                "max_drawdown_pct": round(dd * 100, 2),
                "return_pct": round((p1 / p0 - 1) * 100, 2)}

    def cut(a, b):
        return {s: d[(d.index.date >= a) & (d.index.date <= b)]
                for s, d in frames.items()}

    windows = []
    for label, a, b in (("full", days[0], days[-1]),
                        ("in_sample", days[0], mid),
                        ("out_of_sample", mid, days[-1])):
        r = regime_service.simulate(cut(a, b), RegimeConfig())
        windows.append({
            "window": label, "from": str(a), "to": str(b),
            "cagr_pct": r.extra["cagr_pct"],
            "max_drawdown_pct": r.metrics["max_drawdown_pct"],
            "trades": len(r.trades),
            "pct_risk_on": r.extra["pct_risk_on"],
            "benchmark": bench(a, b),
        })

    full = regime_service.simulate(frames, RegimeConfig())
    eq = {c["day"]: c["equity"] for c in full.daily_equity}
    ordered = sorted(eq)
    by_year = []
    for yr in sorted({d[:4] for d in ordered}):
        span = [d for d in ordered if d.startswith(yr)]
        if len(span) < 20:
            continue
        w = spy[(spy.index.date >= dt.date.fromisoformat(span[0]))
                & (spy.index.date <= dt.date.fromisoformat(span[-1]))]
        b = (round((float(w["Close"].iloc[-1]) / float(w["Close"].iloc[0]) - 1) * 100, 1)
             if not w.empty else None)
        by_year.append({"year": yr,
                        "strategy_pct": round((eq[span[-1]] / eq[span[0]] - 1) * 100, 1),
                        "benchmark_pct": b})

    blob = {
        "cached_at": time.time(),
        "config": full.config,
        "metrics": full.metrics,
        "extra": full.extra,
        "windows": windows,
        "by_year": by_year,
        "symbols": full.symbols,
        "days": full.days,
        "trades": full.trades[-40:],
        "daily_equity": full.daily_equity[::10],
    }
    try:
        _REGIME_CACHE.parent.mkdir(parents=True, exist_ok=True)
        with open(_REGIME_CACHE, "w", encoding="utf-8") as f:
            json.dump(blob, f, indent=2)
    except OSError as exc:
        print(f"[paper] could not cache regime backtest: {exc!r}")
    return blob


_SIZING_CACHE = settings.PORTFOLIO_FILE.parent / "sizing_study.json"


@router.get("/sizing")
def sizing_study(force: bool = False):
    """What the proven edge is worth at higher risk per trade.

    This is where the "took 10k to 1M" stories actually come from — bet size,
    not a better setup. It is reported with the ruin column attached and with a
    second table run at the bottom of the edge's confidence interval, because
    sizing for an edge you have overestimated is how the same maths that
    compounds an account destroys one.
    """
    if not force:
        try:
            with open(_SIZING_CACHE, encoding="utf-8") as f:
                blob = json.load(f)
            if time.time() - blob.get("cached_at", 0) < _TTL:
                return blob
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    from ..services import sizing as sizing_service
    from ..services import swing as swing_service

    res = swing_service.backtest(years=5)
    rs = [t["r_multiple"] for t in res.trades if t.get("r_multiple") is not None]
    if len(rs) < 30:
        return {"error": "not enough trades to study sizing"}

    blob = sizing_service.study(rs, trades_per_year=res.extra["trades_per_year"] or 30,
                                years=5.0, runs=20000)
    blob["cached_at"] = time.time()
    try:
        _SIZING_CACHE.parent.mkdir(parents=True, exist_ok=True)
        with open(_SIZING_CACHE, "w", encoding="utf-8") as f:
            json.dump(blob, f, indent=2)
    except OSError as exc:
        print(f"[paper] could not cache sizing study: {exc!r}")
    return blob


@router.get("/thesis")
def thesis_book():
    """The thesis book, marked to live prices.

    Deliberately live rather than cached: this is a real position being scored,
    and a stale mark on a concentrated book is how you avoid noticing a thesis
    has broken.
    """
    from ..services import market_data
    from ..services import thesis as thesis_service

    book = thesis_service.load()
    quotes: dict = {}
    for p in book.get("positions", []):
        if p.get("closed"):
            continue
        sym = p["symbol"]
        if sym in quotes:
            continue
        try:
            md = market_data.get_price_data(sym)
            quotes[sym] = {"price": float(md.history["Close"].iloc[-1]),
                           "source": md.source}
        except Exception as exc:
            print(f"[thesis] quote failed for {sym}: {exc!r}")
    return thesis_service.mark(book, quotes)


@router.get("/rules")
def rules():
    """The model, stated plainly. If it can't be written down it can't be tested."""
    cfg = paper_service.PaperConfig()
    return {
        "account": {
            "type": "cash",
            "why": ("$1,000 cannot day trade a margin account — four day trades in "
                    "five business days triggers the Pattern Day Trader rule, which "
                    "requires $25,000 minimum equity."),
            "settlement": "T+1. Buys draw only settled cash, so a Good Faith "
                          "Violation is impossible by construction.",
            "budget": "The day's notional budget is the settled cash you start with.",
        },
        "setup": [
            "Long only, opening-range breakout on 5-minute bars",
            f"Opening range = first {cfg.opening_range_bars * 5} minutes",
            "Entry bar must CLOSE above the range high",
            "Price above session VWAP and above the 20-period EMA",
            f"Breakout volume at least {cfg.vol_mult}x the session average",
            f"RSI(14) between {cfg.rsi_low:.0f} and {cfg.rsi_high:.0f} going INTO the break",
        ],
        "execution": [
            "Fill at the NEXT bar's open, never the breakout level",
            f"Slippage ${cfg.slippage:.2f} per share each way",
            f"Stop: tighter of the opening-range low and {cfg.atr_mult}x ATR",
            f"Target {cfg.min_rr:.0f}R"
            + (f", half off at 1R then stop to breakeven"
               if cfg.scale_out_frac else ""),
            f"No new entries after {cfg.entry_cutoff_min} minutes from the open",
            "Flat before the close — never overnight",
        ],
        "risk": [
            f"{cfg.risk_pct * 100:.0f}% of equity risked per trade",
            f"Any one position capped at 1/{cfg.max_open} of the book",
            f"Daily stop: flat for the day at -{cfg.daily_stop_pct * 100:.0f}%",
            f"Max {cfg.max_open} open positions, {cfg.max_trades_per_day} round trips per day",
        ],
        "universe": list(paper_service.UNIVERSE),
        "config": paper_service.PaperConfig().__dict__,
    }
