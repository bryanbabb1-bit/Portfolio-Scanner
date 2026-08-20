"""Is ANY version of chasing a runner positive, or is the whole family dead?

The baseline (buy +20% off the open, sell at the close, no stop) came out at
-0.84% a trade with a 0.83 profit factor. That kills the crudest version. It
does not, on its own, kill the idea — four obvious things were untested: a stop,
a longer hold, an earlier entry, and a liquidity floor.

So all of them get tested, and ALL of them get reported. Testing five variants
on 43 sessions means the best-looking one is expected to look good by chance;
the protection against fooling ourselves is publishing the whole table and
holding every result to the same t-statistic, not picking the winner afterwards.

The market data is cached to disk on first run so variants are cheap to iterate
without re-downloading 5,865 symbols.

Run:  cd backend && .venv/Scripts/python.exe bigmovers_variants.py
"""
from __future__ import annotations

import pickle
import statistics as st
import sys
from pathlib import Path

import pandas as pd
import yfinance as yf

from app.services import universe

CACHE = Path("bigmovers_cache.pkl")
BATCH = 250
PERIOD = "3mo"


def load_frames() -> dict[str, pd.DataFrame]:
    if CACHE.exists():
        print(f"using cached bars ({CACHE})", file=sys.stderr)
        with open(CACHE, "rb") as f:
            return pickle.load(f)
    syms = universe.all_symbols()
    frames: dict[str, pd.DataFrame] = {}
    for i in range(0, len(syms), BATCH):
        chunk = syms[i : i + BATCH]
        try:
            df = yf.download(chunk, period=PERIOD, interval="1d",
                             auto_adjust=False, progress=False, threads=True,
                             group_by="ticker")
        except Exception as exc:
            print(f"  batch {i}: {exc!r}", file=sys.stderr)
            continue
        for sym in chunk:
            try:
                h = df[sym] if isinstance(df.columns, pd.MultiIndex) else df
                h = h.dropna(subset=["Open", "High", "Low", "Close", "Volume"])
                if len(h) >= 25:
                    frames[sym] = h[["Open", "High", "Low", "Close", "Volume"]]
            except Exception:
                continue
        print(f"  {min(i + BATCH, len(syms))}/{len(syms)}", file=sys.stderr)
    with open(CACHE, "wb") as f:
        pickle.dump(frames, f)
    return frames


def run(frames, trigger_pct, min_price, min_dollar_vol, hold_days, stop_pct):
    """One variant. Returns the list of trade returns, in percent."""
    out: list[float] = []
    for sym, h in frames.items():
        close, open_, high, low = h["Close"], h["Open"], h["High"], h["Low"]
        dollar = (h["Volume"] * close).rolling(60, min_periods=20).mean()
        for j in range(20, len(h) - hold_days):
            prev = float(close.iloc[j - 1])
            o = float(open_.iloc[j])
            if prev < min_price or o <= 0:
                continue
            if float(dollar.iloc[j - 1] or 0) < min_dollar_vol:
                continue
            entry = o * (1 + trigger_pct / 100)
            if float(high.iloc[j]) < entry:
                continue
            exit_px = float(close.iloc[j + hold_days])
            if stop_pct:
                stop = entry * (1 - stop_pct / 100)
                # Stops are only checked on sessions AFTER the entry bar. A
                # daily bar cannot say whether its low came before or after the
                # entry print, and checking the entry bar made every trade stop
                # out instantly (the low of a day you bought +20% off the open
                # is almost always below the entry) — a 100% loss rate that was
                # an artifact of the data, not a result.
                for k in range(j + 1, j + hold_days + 1):
                    if float(low.iloc[k]) <= stop:
                        exit_px = stop
                        break
            out.append((exit_px / entry - 1) * 100)
    return out


def report(name: str, rets: list[float]) -> None:
    if not rets:
        print(f"{name:38} no trades")
        return
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r <= 0]
    gl = -sum(losses)
    pf = sum(wins) / gl if gl else float("inf")
    sd = st.pstdev(rets)
    t = st.mean(rets) / (sd / len(rets) ** 0.5) if sd else 0
    print(f"{name:38} n={len(rets):4}  avg={st.mean(rets):+6.2f}%  "
          f"med={st.median(rets):+6.2f}%  win={len(wins)/len(rets)*100:4.1f}%  "
          f"PF={pf:4.2f}  t={t:+5.2f}")


def main() -> None:
    frames = load_frames()
    print(f"symbols: {len(frames)}\n", file=sys.stderr)
    print("Every variant of 'chase the runner'. Entry is the trigger level "
          "itself,\nso these are prices that actually traded.\n")
    print(f"{'variant':38} {'stats'}")
    print("-" * 100)
    report("baseline +20% off open, exit close",
           run(frames, 20, 5, 1_000_000, 0, 0))
    # A same-day stop is not testable on daily bars — see run(). Intraday stops
    # need intraday data, so they are simply not claimed either way here.
    report("  ...hold 3 sessions",
           run(frames, 20, 5, 1_000_000, 3, 0))
    report("  ...hold 3 sessions, 20% stop",
           run(frames, 20, 5, 1_000_000, 3, 20))
    report("  ...hold 10 sessions, 20% stop",
           run(frames, 20, 5, 1_000_000, 10, 20))
    report("earlier entry +10% off open, exit close",
           run(frames, 10, 5, 1_000_000, 0, 0))
    report("liquid only ($10M/day), exit close",
           run(frames, 20, 5, 10_000_000, 0, 0))
    report("liquid + real price ($20), exit close",
           run(frames, 20, 20, 10_000_000, 0, 0))
    report("liquid, hold 10 sessions, 20% stop",
           run(frames, 20, 5, 10_000_000, 10, 20))
    print("-" * 100)
    print("t must clear +2.0 to be distinguishable from noise. Ten variants on "
          "43 sessions:\ntreat any single winner as a hypothesis, not a result.")


if __name__ == "__main__":
    main()
