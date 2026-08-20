"""If we alerted on every name running intraday, how much noise comes with it?

bigmovers_study.py established that ~0.6 tradeable big movers a session still
have 20%+ left after the open. That is the prize. This measures the price of
going after it: on a normal day, how many names trip a "+20% off the open on
real volume" trigger, and what fraction of those actually finish the day up 50%?

A screen is only worth building if that ratio is livable. Measuring it BEFORE
building is the whole point — the alternative is shipping a scanner that buzzes
forty times a day and calling it coverage.

Run:  cd backend && .venv/Scripts/python.exe bigmovers_signal.py
"""
from __future__ import annotations

import sys

import pandas as pd
import yfinance as yf

from app.services import universe

BATCH = 250
PERIOD = "3mo"

# The trigger an intraday scanner could actually fire on.
TRIGGER_PCT = 20.0          # up this much off the open, at some point in the day
MIN_PRICE = 5.00            # priced like a company, not a shell
MIN_DOLLAR_VOL = 1_000_000  # you can get a fill
BIG_DAY = 50.0              # what counts as a hit, close over prior close


def main() -> None:
    syms = universe.all_symbols()
    print(f"universe: {len(syms)}", file=sys.stderr)

    # date -> [triggers, hits]
    tally: dict[str, list[int]] = {}
    examples: list[tuple[str, str, float, float]] = []

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
                h = h.dropna(subset=["Open", "High", "Close", "Volume"])
            except Exception:
                continue
            if len(h) < 25:
                continue
            close, open_, high, vol = h["Close"], h["Open"], h["High"], h["Volume"]
            dollar = (vol * close).rolling(60, min_periods=20).mean()
            for j in range(20, len(h)):
                prev = float(close.iloc[j - 1])
                o = float(open_.iloc[j])
                if prev < MIN_PRICE or o <= 0:
                    continue
                if float(dollar.iloc[j - 1] or 0) < MIN_DOLLAR_VOL:
                    continue
                run_off_open = (float(high.iloc[j]) / o - 1) * 100
                if run_off_open < TRIGGER_PCT:
                    continue
                day = str(h.index[j].date())
                t = tally.setdefault(day, [0, 0])
                t[0] += 1
                day_move = (float(close.iloc[j]) / prev - 1) * 100
                if day_move >= BIG_DAY:
                    t[1] += 1
                    examples.append((day, sym, round(run_off_open, 1), round(day_move, 1)))
        print(f"  {min(i + BATCH, len(syms))}/{len(syms)}", file=sys.stderr)

    days = sorted(tally)
    trig = sum(v[0] for v in tally.values())
    hits = sum(v[1] for v in tally.values())
    print(f"=== trigger: +{TRIGGER_PCT:.0f}% off the open, "
          f"price >= ${MIN_PRICE:.0f}, prior volume >= ${MIN_DOLLAR_VOL/1e6:.0f}M/day ===")
    print(f"sessions measured : {len(days)}")
    print(f"alerts fired      : {trig}  ({trig/max(len(days),1):.1f} per session)")
    print(f"finished +{BIG_DAY:.0f}%    : {hits}  "
          f"({hits/max(trig,1)*100:.1f}% of alerts)")
    print(f"                    {hits/max(len(days),1):.2f} per session\n")

    busiest = sorted(tally.items(), key=lambda kv: -kv[1][0])[:5]
    print("busiest sessions (alert count, of which big):")
    for d, (t, hh) in busiest:
        print(f"  {d}  {t:3} alerts, {hh} big")
    print("\nthe hits:")
    for d, sym, off, mv in sorted(examples)[-20:]:
        print(f"  {d} {sym:6} peaked +{off:.0f}% off the open, closed +{mv:.0f}%")


if __name__ == "__main__":
    main()
