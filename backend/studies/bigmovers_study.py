"""How many stocks run 50%+ in a day, and could any of them have been caught?

The question this answers is NOT "can we build a screen". It is the prior one:
what does the population of big movers actually look like, and how much of the
move is available AFTER the opening bell? A move that is fully gapped at the
open is not a trade you can be alerted into; it is a position you either had or
did not have. That distinction decides whether a scanner is worth building at
all, so it gets measured before anything gets built.

Run:  cd backend && .venv/Scripts/python.exe bigmovers_study.py
"""
from __future__ import annotations

import json
import sys

import pandas as pd
import yfinance as yf

from app.services import universe

MOVE_PCT = 50.0          # what counts as "it ran"
BATCH = 250
PERIOD = "3mo"


def fetch(symbols: list[str]) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    for i in range(0, len(symbols), BATCH):
        chunk = symbols[i : i + BATCH]
        try:
            df = yf.download(chunk, period=PERIOD, interval="1d",
                             auto_adjust=False, progress=False, threads=True,
                             group_by="ticker")
        except Exception as exc:
            print(f"  batch {i}: {exc!r}", file=sys.stderr)
            continue
        for sym in chunk:
            try:
                sub = df[sym] if isinstance(df.columns, pd.MultiIndex) else df
                sub = sub.dropna(subset=["Close", "Open"])
                if len(sub) >= 25:
                    frames[sym] = sub
            except Exception:
                continue
        print(f"  {min(i + BATCH, len(symbols))}/{len(symbols)} "
              f"({len(frames)} usable)", file=sys.stderr)
    return frames


def main() -> None:
    syms = universe.all_symbols()
    print(f"universe: {len(syms)} symbols, {PERIOD} of daily bars", file=sys.stderr)
    frames = fetch(syms)
    print(f"usable histories: {len(frames)}\n", file=sys.stderr)

    events: list[dict] = []
    for sym, h in frames.items():
        close, open_, vol = h["Close"], h["Open"], h["Volume"]
        for i in range(20, len(h)):
            prev = float(close.iloc[i - 1])
            if prev <= 0:
                continue
            move = (float(close.iloc[i]) / prev - 1) * 100
            if move < MOVE_PCT:
                continue
            o = float(open_.iloc[i])
            gap = (o / prev - 1) * 100                    # locked in before the bell
            intraday = (float(close.iloc[i]) / o - 1) * 100 if o else 0.0
            prior_vol = float(vol.iloc[max(0, i - 60) : i].mean())
            events.append({
                "symbol": sym,
                "date": str(h.index[i].date()),
                "move_pct": round(move, 1),
                "gap_pct": round(gap, 1),
                "intraday_pct": round(intraday, 1),
                "prev_close": round(prev, 2),
                "prior_avg_vol": int(prior_vol) if prior_vol == prior_vol else 0,
                "prior_dollar_vol": int(prior_vol * prev) if prior_vol == prior_vol else 0,
                "day_vol": int(vol.iloc[i]),
            })

    events.sort(key=lambda e: (e["date"], -e["move_pct"]))
    with open("bigmovers_events.json", "w", encoding="utf-8") as f:
        json.dump(events, f, indent=1)

    days = sorted({e["date"] for e in events})
    print(f"=== {len(events)} moves of +{MOVE_PCT:.0f}% or more, "
          f"over {len(days)} sessions ===")
    print(f"    {len(events) / max(len(days), 1):.1f} per session on average\n")

    # How much of the move was gapped away before anyone could act?
    fully_gapped = [e for e in events if e["gap_pct"] >= MOVE_PCT]
    mostly_gapped = [e for e in events if e["gap_pct"] >= e["move_pct"] * 0.5]
    intraday_run = [e for e in events if e["intraday_pct"] >= 20]
    print("WHERE THE MOVE HAPPENED")
    print(f"  already +{MOVE_PCT:.0f}% at the open (un-alertable): "
          f"{len(fully_gapped):4} ({len(fully_gapped)/len(events)*100:.0f}%)")
    print(f"  more than half the move gapped:                  "
          f"{len(mostly_gapped):4} ({len(mostly_gapped)/len(events)*100:.0f}%)")
    print(f"  still +20% or more available after the open:     "
          f"{len(intraday_run):4} ({len(intraday_run)/len(events)*100:.0f}%)\n")

    # Could you have traded it at all the day before?
    def bucket(e):
        dv = e["prior_dollar_vol"]
        if dv < 100_000:
            return "under $100k/day (untradeable)"
        if dv < 1_000_000:
            return "$100k-$1M/day (thin)"
        if dv < 10_000_000:
            return "$1M-$10M/day"
        return "over $10M/day (liquid)"

    print("PRIOR LIQUIDITY (60-day average dollar volume BEFORE the move)")
    counts: dict[str, int] = {}
    for e in events:
        counts[bucket(e)] = counts.get(bucket(e), 0) + 1
    for k in ("under $100k/day (untradeable)", "$100k-$1M/day (thin)",
              "$1M-$10M/day", "over $10M/day (liquid)"):
        n = counts.get(k, 0)
        print(f"  {k:34} {n:4} ({n/len(events)*100:.0f}%)")

    print("\nPRIOR PRICE")
    pb: dict[str, int] = {}
    for e in events:
        p = e["prev_close"]
        k = ("under $1" if p < 1 else "$1-$5" if p < 5 else
             "$5-$20" if p < 20 else "over $20")
        pb[k] = pb.get(k, 0) + 1
    for k in ("under $1", "$1-$5", "$5-$20", "over $20"):
        n = pb.get(k, 0)
        print(f"  {k:34} {n:4} ({n/len(events)*100:.0f}%)")

    # The subset that is actually investable: liquid enough to buy, priced like
    # a real company, and with real upside still on the table after the open.
    real = [e for e in events
            if e["prior_dollar_vol"] >= 1_000_000
            and e["prev_close"] >= 5
            and e["intraday_pct"] >= 20]
    print(f"\nBOTH TRADEABLE AND STILL AVAILABLE AFTER THE OPEN: "
          f"{len(real)} of {len(events)} "
          f"({len(real)/len(events)*100:.1f}%) — "
          f"{len(real)/max(len(days),1):.2f} per session")
    for e in real[-25:]:
        print(f"  {e['date']} {e['symbol']:6} +{e['move_pct']:.0f}% "
              f"(gap +{e['gap_pct']:.0f}%, intraday +{e['intraday_pct']:.0f}%) "
              f"prior ${e['prior_dollar_vol']/1e6:.1f}M/day @ ${e['prev_close']}")


if __name__ == "__main__":
    main()
