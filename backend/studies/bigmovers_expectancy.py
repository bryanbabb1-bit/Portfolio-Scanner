"""Would trading those alerts have made money?

A 9% hit rate is not an edge, it is a statistic. The edge question is what the
average alert RETURNS when you actually take it — the nine that fade have to be
paid for by the one that runs. This buys every alert at the trigger level
(+20% off the open, the price you could realistically have paid) and sells at
the close the same day, then reports the distribution rather than the highlight.

No stop, no target, no discretion: the crudest possible version of the rule.
If the crude version has no expectancy, a cleverer version of the same idea is
a story about the exceptions, not a strategy.

Run:  cd backend && .venv/Scripts/python.exe bigmovers_expectancy.py
"""
from __future__ import annotations

import statistics as st
import sys

import pandas as pd
import yfinance as yf

from app.services import universe

BATCH = 250
PERIOD = "3mo"
TRIGGER_PCT = 20.0
MIN_PRICE = 5.00
MIN_DOLLAR_VOL = 1_000_000


def main() -> None:
    syms = universe.all_symbols()
    trades: list[dict] = []

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
            except Exception:
                continue
            if len(h) < 25:
                continue
            close, open_, high, low = h["Close"], h["Open"], h["High"], h["Low"]
            dollar = (h["Volume"] * close).rolling(60, min_periods=20).mean()
            for j in range(20, len(h)):
                prev = float(close.iloc[j - 1])
                o = float(open_.iloc[j])
                if prev < MIN_PRICE or o <= 0:
                    continue
                if float(dollar.iloc[j - 1] or 0) < MIN_DOLLAR_VOL:
                    continue
                entry = o * (1 + TRIGGER_PCT / 100)
                if float(high.iloc[j]) < entry:
                    continue                     # never traded up to the trigger
                exit_ = float(close.iloc[j])
                trades.append({
                    "date": str(h.index[j].date()), "symbol": sym,
                    "entry": round(entry, 2), "exit": round(exit_, 2),
                    "ret": (exit_ / entry - 1) * 100,
                    # How far it went against you before the close — the number
                    # that decides whether any stop would have survived.
                    "mae": (float(low.iloc[j]) / entry - 1) * 100,
                })
        print(f"  {min(i + BATCH, len(syms))}/{len(syms)}", file=sys.stderr)

    if not trades:
        print("no trades")
        return

    rets = [t["ret"] for t in trades]
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r <= 0]
    days = len({t["date"] for t in trades})

    print(f"=== buy at +{TRIGGER_PCT:.0f}% off the open, sell at the close ===")
    print(f"trades          : {len(trades)} over {days} sessions "
          f"({len(trades)/days:.1f}/session)")
    print(f"win rate        : {len(wins)/len(trades)*100:.1f}%")
    print(f"average trade   : {st.mean(rets):+.2f}%")
    print(f"median trade    : {st.median(rets):+.2f}%")
    print(f"average win     : {st.mean(wins):+.2f}%" if wins else "")
    print(f"average loss    : {st.mean(losses):+.2f}%" if losses else "")
    gross_win = sum(wins)
    gross_loss = -sum(losses)
    print(f"profit factor   : {gross_win/gross_loss:.2f}" if gross_loss else "")
    # Is the average distinguishable from zero, or is it one lucky trade?
    sd = st.pstdev(rets)
    t_stat = st.mean(rets) / (sd / len(rets) ** 0.5) if sd else 0
    print(f"std dev         : {sd:.2f}%")
    print(f"t-statistic     : {t_stat:.2f}   "
          f"({'significant' if abs(t_stat) >= 2 else 'NOT significant'} at 2.0)")

    best = sorted(trades, key=lambda t: -t["ret"])[:5]
    worst = sorted(trades, key=lambda t: t["ret"])[:5]
    print("\nbest:")
    for t in best:
        print(f"  {t['date']} {t['symbol']:6} {t['ret']:+7.1f}%")
    print("worst:")
    for t in worst:
        print(f"  {t['date']} {t['symbol']:6} {t['ret']:+7.1f}%")

    # Does the whole result rest on one trade?
    without_best = [t["ret"] for t in trades if t is not best[0]]
    print(f"\naverage excluding the single best trade: "
          f"{st.mean(without_best):+.2f}%")
    top5 = {id(t) for t in best}
    rest = [t["ret"] for t in trades if id(t) not in top5]
    print(f"average excluding the top 5 trades     : {st.mean(rest):+.2f}%")
    print(f"\nworst drawdown inside a winning day (avg MAE): "
          f"{st.mean([t['mae'] for t in trades]):.1f}%")


if __name__ == "__main__":
    main()
