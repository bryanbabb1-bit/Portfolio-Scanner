"""Swing-trading simulation — multi-day holds on a $1,000 cash account.

WHY THIS EXISTS INSTEAD OF THE DAY-TRADING MODEL
------------------------------------------------
The intraday version was the most constrained vehicle available: Pattern Day
Trader blocked, settlement-throttled to ~1.7 trades a session, position capped at
half the book, and intraday stops so tight that the account only ever risked
0.23% per trade against a 2% budget. It could not move the needle even if the
rules had been good, and they weren't.

Holding for days instead of hours removes every one of those limits at once:

  * PDT does not apply — these are not day trades, so no $25,000 minimum.
  * Settlement stops binding. A position held a week has long since settled by
    the time it is sold, so the full $1,000 stays deployable.
  * Stops sit 5-10% away instead of 0.5%, so a 2% risk budget is actually
    REACHABLE — the position size the risk implies now fits inside the account.
  * Daily bars go back years rather than the 60 days yfinance allows for
    5-minute data, so the sample is large enough to prove something.

THE RULES, AND WHY THESE ONES
-----------------------------
This is not a fresh guess. The learning loop's own five-year replay found every
BUY rule in this codebase profitable and every SELL rule losing, with
oversold-at-support at a 2.69 profit factor. That is a pullback-in-uptrend edge,
so this models it directly:

  buy weakness inside strength, never weakness on its own.

The regime filter is doing the heavy lifting. Buying an oversold stock is a good
idea in an uptrend and a catastrophe in a downtrend, and the difference between
the two is the 200-day.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from datetime import date

import pandas as pd

from .paper import Ledger, Trade, _metrics
from .technical import _atr, _rsi

# Liquid names with real multi-year history, spread across sectors so the result
# is not one sector's story. Survivorship is a known bias here: these are
# companies that DID well enough to still be liquid today, which flatters any
# long-only backtest. Treated as a caveat on the result, not a fixable defect.
UNIVERSE: tuple[str, ...] = (
    "SPY", "QQQ", "IWM", "XLE", "XLF", "XLV", "XLI",
    "AAPL", "MSFT", "NVDA", "AMD", "AVGO", "GOOGL", "META", "AMZN",
    "JPM", "BAC", "V", "MA", "UNH", "JNJ", "LLY", "MRK", "PFE",
    "CAT", "DE", "HON", "GE", "WMT", "COST", "HD", "MCD", "NKE",
    "XOM", "CVX", "COP", "NEE", "DUK", "CRM", "ADBE", "NFLX",
)


@dataclass
class SwingConfig:
    starting_cash: float = 1000.0
    risk_pct: float = 0.02          # now actually reachable, see module docstring
    max_open: int = 4               # diversification without dust-sized positions
    max_new_per_day: int = 2
    # Regime + setup
    trend_sma: int = 200            # the filter that separates a dip from a fall
    rsi_len: int = 14
    rsi_entry: float = 35.0         # oversold ENOUGH to be a real pullback
    # Exit
    atr_len: int = 14
    atr_stop: float = 2.5           # room to breathe across days
    target_r: float = 3.0
    max_hold_days: int = 20         # capital that isn't working gets recycled
    trail_after_r: float = 1.5      # trail once it has proven itself
    trail_atr: float = 2.0
    slippage_pct: float = 0.0005    # 5bp each way, realistic for liquid names


def prepare(df: pd.DataFrame, cfg: SwingConfig) -> pd.DataFrame:
    out = df.copy()
    out["sma200"] = out["Close"].rolling(cfg.trend_sma).mean()
    out["sma20"] = out["Close"].rolling(20).mean()
    out["rsi"] = _rsi(out["Close"], cfg.rsi_len)
    out["atr"] = _atr(out, cfg.atr_len)
    out["rsi_prev"] = out["rsi"].shift(1)
    return out


def entry_signal(row: pd.Series, cfg: SwingConfig) -> str | None:
    """Pullback inside an uptrend. Returns the reason, or None.

    Order matters for readability, not logic: regime first, because a stock below
    its 200-day is not a candidate no matter how oversold it gets.
    """
    for key in ("sma200", "sma20", "rsi", "rsi_prev", "atr"):
        v = row.get(key)
        if v is None or pd.isna(v):
            return None
    close = float(row["Close"])
    if close <= float(row["sma200"]):
        return None                             # not an uptrend; not our trade
    rsi, rsi_prev = float(row["rsi"]), float(row["rsi_prev"])
    if rsi_prev >= cfg.rsi_entry:
        return None                             # wasn't oversold going in
    if rsi <= rsi_prev:
        return None                             # still falling; wait for the turn
    return (f"pullback in uptrend: above 200d, RSI turned up "
            f"{rsi_prev:.0f} -> {rsi:.0f}")


def plan_trade(row: pd.Series, fill: float, equity: float, buying_power: float,
               cfg: SwingConfig) -> tuple[float, float, float, float] | None:
    entry = fill * (1 + cfg.slippage_pct)
    atr = float(row["atr"])
    stop = entry - cfg.atr_stop * atr
    risk_per_share = entry - stop
    if risk_per_share <= 0:
        return None
    target = entry + cfg.target_r * risk_per_share

    shares = (equity * cfg.risk_pct) / risk_per_share
    per_position = equity / max(cfg.max_open, 1)
    max_shares = min(buying_power, per_position) / entry
    shares = math.floor(min(shares, max_shares) * 1e6) / 1e6
    if shares * entry < 1.0:
        return None
    return entry, stop, target, shares


@dataclass
class Result:
    config: dict
    trades: list[dict]
    daily_equity: list[dict]
    metrics: dict
    blocked: dict
    days: int
    symbols: list[str]
    extra: dict = field(default_factory=dict)


def simulate(frames: dict[str, pd.DataFrame], cfg: SwingConfig | None = None) -> Result:
    """Replay daily bars across the universe on one shared cash account."""
    cfg = cfg or SwingConfig()
    prepped = {s: prepare(df, cfg) for s, df in frames.items()
               if df is not None and not df.empty}
    if not prepped:
        return Result(asdict(cfg), [], [], _metrics([], [], cfg.starting_cash), {}, 0, [])

    ledger = Ledger(settled=cfg.starting_cash)
    trades: list[Trade] = []
    open_trades: dict[str, Trade] = {}
    curve: list[dict] = []
    blocked = {"no_buying_power": 0, "max_open": 0, "max_new_per_day": 0, "no_size": 0}
    pending: dict[str, dict] = {}
    held_days: dict[str, int] = {}

    sessions = sorted({ts.date() for df in prepped.values() for ts in df.index})

    def close_at(t: Trade, price: float, reason: str, day: date, ts) -> None:
        proceeds = t.open_shares * price * (1 - cfg.slippage_pct)
        ledger.sell(proceeds, day)
        t.realized += proceeds - t.open_shares * t.entry
        t.exits.append({"time": str(ts), "shares": round(t.open_shares, 6),
                        "price": round(price, 4), "reason": reason})
        t.open_shares = 0.0
        t.exit_reason = reason
        t.r_multiple = round(t.realized / t.risk_dollars, 3) if t.risk_dollars > 0 else None
        open_trades.pop(t.symbol, None)
        held_days.pop(t.symbol, None)

    def equity_on(day: date) -> float:
        held = 0.0
        for sym, t in open_trades.items():
            df = prepped[sym]
            idx = df.index[df.index.date <= day]
            if len(idx):
                held += t.open_shares * float(df.loc[idx[-1], "Close"])
        return ledger.total + held

    for day in sessions:
        ledger.settle_through(day)
        opened_today = 0

        for sym, df in prepped.items():
            idx = df.index[df.index.date == day]
            if not len(idx):
                continue
            ts = idx[0]
            row = df.loc[ts]
            if isinstance(row, pd.DataFrame):
                row = row.iloc[0]
            o, h, l, c = (float(row["Open"]), float(row["High"]),
                          float(row["Low"]), float(row["Close"]))

            # ---- fill what triggered on yesterday's close, at today's open
            want = pending.pop(sym, None)
            if want is not None and sym not in open_trades:
                if ledger.settled < 1.0:
                    blocked["no_buying_power"] += 1
                elif len(open_trades) >= cfg.max_open:
                    blocked["max_open"] += 1
                elif opened_today >= cfg.max_new_per_day:
                    blocked["max_new_per_day"] += 1
                else:
                    plan = plan_trade(row, o, equity_on(day), ledger.settled, cfg)
                    if plan is None:
                        blocked["no_size"] += 1
                    else:
                        entry, stop, target, shares = plan
                        if not ledger.buy(shares * entry):
                            blocked["no_buying_power"] += 1
                        else:
                            t = Trade(symbol=sym, day=str(day), entry_time=str(ts),
                                      entry=round(entry, 4), stop=round(stop, 4),
                                      target=round(target, 4), shares=round(shares, 6),
                                      risk_dollars=round(shares * (entry - stop), 2),
                                      setup=want["reason"], open_shares=shares,
                                      current_stop=round(stop, 4))
                            trades.append(t)
                            open_trades[sym] = t
                            held_days[sym] = 0
                            opened_today += 1
                            # Only the adverse case on the entry bar — a same-day
                            # target would be the look-ahead the intraday model
                            # was caught doing.
                            if l <= t.current_stop:
                                close_at(t, t.current_stop, "stop", day, ts)
                            continue

            # ---- manage
            t = open_trades.get(sym)
            if t is not None:
                held_days[sym] = held_days.get(sym, 0) + 1
                one_r = t.entry - t.stop
                if l <= t.current_stop:
                    close_at(t, t.current_stop, "stop", day, ts)
                elif h >= t.target:
                    close_at(t, t.target, "target", day, ts)
                elif held_days[sym] >= cfg.max_hold_days:
                    close_at(t, c, "time", day, ts)
                else:
                    # Trail only after the trade has earned it, and never
                    # downward.
                    if one_r > 0 and (c - t.entry) / one_r >= cfg.trail_after_r:
                        trail = c - cfg.trail_atr * float(row["atr"])
                        t.current_stop = round(max(t.current_stop, trail), 4)
                continue

            # ---- look for tomorrow's entry
            if sym in pending:
                continue
            reason = entry_signal(row, cfg)
            if reason:
                pending[sym] = {"reason": reason, "day": day}

        curve.append({"day": str(day), "equity": round(equity_on(day), 2)})

    # Flat at the end so the final equity is cash, not a mark.
    if sessions:
        last = sessions[-1]
        for t in list(open_trades.values()):
            df = prepped[t.symbol]
            idx = df.index[df.index.date <= last]
            if len(idx):
                close_at(t, float(df.loc[idx[-1], "Close"]), "end of test", last, idx[-1])

    closed = [t for t in trades if t.exits]
    holds = []
    for t in closed:
        try:
            holds.append((pd.Timestamp(t.exits[-1]["time"]).date()
                          - pd.Timestamp(t.entry_time).date()).days)
        except Exception:
            pass
    years = len(sessions) / 252 if sessions else 0
    end = curve[-1]["equity"] if curve else cfg.starting_cash
    cagr = ((end / cfg.starting_cash) ** (1 / years) - 1) * 100 if years > 0.5 else None

    return Result(
        config=asdict(cfg),
        trades=[asdict(t) for t in trades],
        daily_equity=curve,
        metrics=_metrics(trades, [{"equity": p["equity"]} for p in curve],
                         cfg.starting_cash),
        blocked=blocked,
        days=len(sessions),
        symbols=sorted(prepped),
        extra={
            "years": round(years, 2),
            "cagr_pct": round(cagr, 2) if cagr is not None else None,
            "avg_hold_days": round(sum(holds) / len(holds), 1) if holds else None,
            "trades_per_year": round(len(closed) / years, 1) if years > 0.5 else None,
        },
    )


def backtest(symbols: tuple[str, ...] = UNIVERSE, years: int = 5,
             cfg: SwingConfig | None = None) -> Result:
    """Replay daily bars. Mock-sourced symbols are excluded — a backtest run on
    generated prices proves nothing."""
    from . import market_data

    frames: dict[str, pd.DataFrame] = {}
    for sym in symbols:
        try:
            md = market_data.get_deep_history(sym, years=years)
        except Exception as exc:
            print(f"[swing] {sym}: fetch failed ({exc!r})")
            continue
        if md.source != "live" or md.history is None or md.history.empty:
            print(f"[swing] {sym}: {md.source} data — excluded")
            continue
        frames[sym] = md.history
    return simulate(frames, cfg)
