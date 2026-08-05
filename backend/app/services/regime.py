"""Regime-switching model: own the index when it is rising, hunt when it isn't.

THE PROBLEM THIS SOLVES
-----------------------
The pullback model has a statistically real edge (+0.233R, t 2.48) and still
lost to buying SPY, because it sits in cash about a quarter of the time and
therefore cannot keep up with a rising tide. Its year split says exactly what it
is:

    2022  +17.7%  vs  SPY -18.6%      it wins when the index falls
    2023   +7.9%  vs  SPY +26.7%      it lags badly when the index runs

Nothing about the rules fixes that — a long-only strategy that is frequently
flat will always trail a bull market. So stop asking it to. Participate in the
rise by simply owning the index, and deploy the hunting strategy only when
owning the index is the losing move.

    SPY above its 200-day  ->  hold SPY. Take the beta, do nothing clever.
    SPY below its 200-day  ->  run the pullback model on names still in uptrends.

The 200-day is not tuned; it is the same filter the pullback rules already use
and the most widely documented regime line there is. Picking it because it is
conventional is the point: a threshold chosen by searching would be fitted to
this sample and would not survive contact with the next one.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict, field

import pandas as pd

from .paper import Ledger, Trade, _metrics
from .swing import SwingConfig, entry_signal, prepare


@dataclass
class RegimeConfig(SwingConfig):
    index_symbol: str = "SPY"
    regime_sma: int = 200
    # Confirmation days before flipping. A single close over the line is noise;
    # this is the one parameter with any freedom in it, so it is deliberately
    # small and reported rather than searched.
    confirm_days: int = 3
    # Whether risk-off hunts pullbacks or simply sits in cash. Kept as a switch
    # so the question "does the hunting earn its place?" can be answered by
    # ablation rather than argued about.
    hunt_in_risk_off: bool = True
    # Cash earns something when it is not deployed. Zero by default because the
    # rate varied from ~0% to ~5% across this window and assuming today's rate
    # for all fifteen years would invent return that never existed.
    cash_yield_pct: float = 0.0


def regime_series(index_df: pd.DataFrame, cfg: RegimeConfig) -> dict:
    """date -> True when the index is in an uptrend (risk-on)."""
    sma = index_df["Close"].rolling(cfg.regime_sma).mean()
    above = index_df["Close"] > sma
    # Require N consecutive closes on the same side before flipping.
    confirmed = above.rolling(cfg.confirm_days).sum()
    out: dict = {}
    state = False
    for ts, c in confirmed.items():
        if pd.isna(c):
            out[ts.date()] = False
            continue
        if c == cfg.confirm_days:
            state = True
        elif c == 0:
            state = False
        out[ts.date()] = state
    return out


@dataclass
class Result:
    config: dict
    trades: list[dict]
    daily_equity: list[dict]
    metrics: dict
    days: int
    symbols: list[str]
    extra: dict = field(default_factory=dict)


def simulate(frames: dict[str, pd.DataFrame], cfg: RegimeConfig | None = None) -> Result:
    cfg = cfg or RegimeConfig()
    prepped = {s: prepare(df, cfg) for s, df in frames.items()
               if df is not None and not df.empty}
    idx_df = prepped.get(cfg.index_symbol)
    if idx_df is None:
        raise ValueError(f"{cfg.index_symbol} is required for the regime filter")

    risk_on = regime_series(idx_df, cfg)
    ledger = Ledger(settled=cfg.starting_cash)
    trades: list[Trade] = []
    open_trades: dict[str, Trade] = {}
    curve: list[dict] = []
    pending: dict[str, dict] = {}
    held_days: dict[str, int] = {}
    want_index = False          # set on the close, acted on the next open
    days_on = 0

    sessions = sorted({ts.date() for df in prepped.values() for ts in df.index})

    def close_at(t: Trade, price: float, reason: str, day, ts) -> None:
        proceeds = t.open_shares * price * (1 - cfg.slippage_pct)
        ledger.sell(proceeds, day)
        t.realized += proceeds - t.open_shares * t.entry
        t.exits.append({"time": str(ts), "shares": round(t.open_shares, 6),
                        "price": round(price, 4), "reason": reason})
        t.open_shares = 0.0
        t.exit_reason = reason
        t.r_multiple = (round(t.realized / t.risk_dollars, 3)
                        if t.risk_dollars > 0 else None)
        open_trades.pop(t.symbol, None)
        held_days.pop(t.symbol, None)

    def equity_on(day) -> float:
        held = 0.0
        for sym, t in open_trades.items():
            df = prepped[sym]
            i = df.index[df.index.date <= day]
            if len(i):
                held += t.open_shares * float(df.loc[i[-1], "Close"])
        return ledger.total + held

    for day in sessions:
        ledger.settle_through(day)
        on = risk_on.get(day, False)
        days_on += 1 if on else 0
        opened_today = 0

        def bar(sym):
            df = prepped.get(sym)
            if df is None:
                return None, None
            i = df.index[df.index.date == day]
            if not len(i):
                return None, None
            r = df.loc[i[0]]
            return (r.iloc[0] if isinstance(r, pd.DataFrame) else r), i[0]

        # ---------- risk-ON: be in the index, and nothing else
        if on:
            for sym in list(open_trades):
                if sym == cfg.index_symbol:
                    continue
                row, ts = bar(sym)
                if row is not None:
                    close_at(open_trades[sym], float(row["Open"]),
                             "regime flip", day, ts)
            pending.clear()
            if cfg.index_symbol not in open_trades:
                row, ts = bar(cfg.index_symbol)
                if row is not None and want_index and ledger.settled > 1.0:
                    price = float(row["Open"]) * (1 + cfg.slippage_pct)
                    shares = math.floor((ledger.settled / price) * 1e6) / 1e6
                    if shares * price >= 1.0 and ledger.buy(shares * price):
                        t = Trade(symbol=cfg.index_symbol, day=str(day),
                                  entry_time=str(ts), entry=round(price, 4),
                                  stop=0.0, target=0.0, shares=round(shares, 6),
                                  risk_dollars=0.0,
                                  setup="risk-on: index above its 200-day",
                                  open_shares=shares, current_stop=0.0)
                        trades.append(t)
                        open_trades[cfg.index_symbol] = t
            want_index = True
            curve.append({"day": str(day), "equity": round(equity_on(day), 2),
                          "risk_on": True})
            continue

        # ---------- risk-OFF: out of the index, hunt pullbacks
        want_index = False
        if cfg.index_symbol in open_trades:
            row, ts = bar(cfg.index_symbol)
            if row is not None:
                close_at(open_trades[cfg.index_symbol], float(row["Open"]),
                         "regime flip", day, ts)

        for sym, df in prepped.items():
            row, ts = bar(sym)
            if row is None:
                continue
            o, h, l, c = (float(row["Open"]), float(row["High"]),
                          float(row["Low"]), float(row["Close"]))

            want = pending.pop(sym, None)
            if want is not None and sym not in open_trades:
                if (ledger.settled >= 1.0 and len(open_trades) < cfg.max_open
                        and opened_today < cfg.max_new_per_day):
                    entry = o * (1 + cfg.slippage_pct)
                    atr = float(row["atr"])
                    stop = entry - cfg.atr_stop * atr
                    rps = entry - stop
                    if rps > 0:
                        target = entry + cfg.target_r * rps
                        shares = (equity_on(day) * cfg.risk_pct) / rps
                        cap = min(ledger.settled,
                                  equity_on(day) / max(cfg.max_open, 1)) / entry
                        shares = math.floor(min(shares, cap) * 1e6) / 1e6
                        if shares * entry >= 1.0 and ledger.buy(shares * entry):
                            t = Trade(symbol=sym, day=str(day), entry_time=str(ts),
                                      entry=round(entry, 4), stop=round(stop, 4),
                                      target=round(target, 4),
                                      shares=round(shares, 6),
                                      risk_dollars=round(shares * rps, 2),
                                      setup=want["reason"], open_shares=shares,
                                      current_stop=round(stop, 4))
                            trades.append(t)
                            open_trades[sym] = t
                            opened_today += 1
                            if l <= t.current_stop:
                                close_at(t, t.current_stop, "stop", day, ts)
                            continue

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
                elif one_r > 0 and (c - t.entry) / one_r >= cfg.trail_after_r:
                    t.current_stop = round(
                        max(t.current_stop, c - cfg.trail_atr * float(row["atr"])), 4)
                continue

            if sym == cfg.index_symbol or sym in pending or not cfg.hunt_in_risk_off:
                continue
            reason = entry_signal(row, cfg)
            if reason:
                pending[sym] = {"reason": reason, "day": day}

        curve.append({"day": str(day), "equity": round(equity_on(day), 2),
                      "risk_on": False})

    if sessions:
        last = sessions[-1]
        for t in list(open_trades.values()):
            df = prepped[t.symbol]
            i = df.index[df.index.date <= last]
            if len(i):
                close_at(t, float(df.loc[i[-1], "Close"]), "end of test", last, i[-1])

    years = len(sessions) / 252 if sessions else 0
    end = curve[-1]["equity"] if curve else cfg.starting_cash
    cagr = ((end / cfg.starting_cash) ** (1 / years) - 1) * 100 if years > 0.5 else None
    return Result(
        config=asdict(cfg),
        trades=[asdict(t) for t in trades],
        daily_equity=curve,
        metrics=_metrics(trades, [{"equity": p["equity"]} for p in curve],
                         cfg.starting_cash),
        days=len(sessions),
        symbols=sorted(prepped),
        extra={
            "years": round(years, 2),
            "cagr_pct": round(cagr, 2) if cagr is not None else None,
            "pct_risk_on": round(days_on / len(sessions) * 100, 1) if sessions else 0,
            "index_trades": sum(1 for t in trades if t.symbol == cfg.index_symbol),
            "hunt_trades": sum(1 for t in trades if t.symbol != cfg.index_symbol),
        },
    )


def load_frames(symbols: tuple[str, ...], years: int = 15) -> dict[str, pd.DataFrame]:
    from . import market_data

    frames: dict[str, pd.DataFrame] = {}
    for sym in symbols:
        try:
            md = market_data.get_deep_history(sym, years=years)
        except Exception as exc:
            print(f"[regime] {sym}: fetch failed ({exc!r})")
            continue
        if md.source != "live" or md.history is None or md.history.empty:
            continue
        frames[sym] = md.history
    return frames
