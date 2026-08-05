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
