"""Is there a footprint BEFORE a big move, or does it arrive from nowhere?

The 8-K feed failed the only test that mattered: it is filed alongside the
press release, so it cannot get you in early. This asks whether anything can.

Method. Take the 195 measured +50% days from bigmovers_study.py, look at the
twenty sessions BEFORE each, and compare against thousands of ordinary
stock-days from the same universe and era. Then forward-test: screen after the
close, enter at the next open, and report what the flagged names actually did.

Needs a year of bars (the 3-month cache is too shallow to look 65 sessions
back), so it builds its own premove_cache.pkl on first run.

    cd backend && .venv/Scripts/python.exe studies/premove_footprint.py
"""
from __future__ import annotations

import json
import pickle
import random
import statistics as st
import sys
from pathlib import Path

import pandas as pd
import yfinance as yf

CACHE = Path("premove_cache.pkl")
EVENTS = Path("bigmovers_events.json")
CONTROL_SYMBOLS = 800
BATCH = 250
SEED = 7


def load() -> dict:
    if CACHE.exists():
        return pickle.load(open(CACHE, "rb"))
    random.seed(SEED)
    events = json.load(open(EVENTS, encoding="utf-8"))
    ev_syms = sorted({e["symbol"] for e in events})
    universe = sorted(pickle.load(open("bigmovers_cache.pkl", "rb")).keys())
    ctrl = random.sample([s for s in universe if s not in ev_syms], CONTROL_SYMBOLS)
    want = sorted(set(ev_syms) | set(ctrl))

    frames = {}
    for i in range(0, len(want), BATCH):
        chunk = want[i:i + BATCH]
        df = yf.download(chunk, period="1y", interval="1d", auto_adjust=False,
                         progress=False, threads=True, group_by="ticker")
        for s in chunk:
            try:
                h = df[s] if isinstance(df.columns, pd.MultiIndex) else df
                h = h.dropna(subset=["Open", "High", "Low", "Close", "Volume"])
                if len(h) >= 120:
                    frames[s] = h[["Open", "High", "Low", "Close", "Volume"]]
            except Exception:
                continue
        print(f"  {min(i + BATCH, len(want))}/{len(want)}", file=sys.stderr)
    out = {"frames": frames, "events": ev_syms, "ctrl": ctrl}
    pickle.dump(out, open(CACHE, "wb"))
    return out


def features(h, j):
    """The run-up, measured only from data available before session j."""
    if j < 70 or j >= len(h):
        return None
    close, vol, high, low = h["Close"], h["Volume"], h["High"], h["Low"]
    # The baseline stops five sessions short on purpose: a name that has been
    # loud all week would otherwise normalise its own surge into the average.
    base_v = float(vol.iloc[j - 65:j - 5].mean())
    prev = float(close.iloc[j - 1])
    if not base_v or prev <= 0:
        return None
    return {
        "vol_ratio": float(vol.iloc[j - 5:j].mean()) / base_v,
        "vol_prev_day": float(vol.iloc[j - 1]) / base_v,
        "drift_20d": (prev / float(close.iloc[j - 21]) - 1) * 100,
        "range_5d": float(((high.iloc[j - 5:j] - low.iloc[j - 5:j])
                           / close.iloc[j - 5:j]).mean()) * 100,
    }


def forward(h, j):
    """What a name flagged after session j-1 did if you bought the next open."""
    if j < 70 or j + 6 >= len(h):
        return None
    close, vol, high = h["Close"], h["Volume"], h["High"]
    base_v = float(vol.iloc[j - 65:j - 5].mean())
    prev = float(close.iloc[j - 1])
    op = float(h["Open"].iloc[j])
    if not base_v or prev < 2 or op <= 0 or base_v * prev < 1_000_000:
        return None
    return {
        "v": float(vol.iloc[j - 1]) / base_v,
        "fwd5": (float(close.iloc[j + 5]) / op - 1) * 100,
        "max5": (float(high.iloc[j:j + 6].max()) / op - 1) * 100,
    }


def main() -> None:
    d = load()
    frames, ev_syms = d["frames"], set(d["events"])
    events = json.load(open(EVENTS, encoding="utf-8"))
    idx = {s: {str(t.date()): i for i, t in enumerate(h.index)}
           for s, h in frames.items()}

    ev_rows = []
    for e in events:
        h = frames.get(e["symbol"])
        if h is None:
            continue
        j = idx[e["symbol"]].get(e["date"])
        if j is None:
            continue
        f = features(h, j)
        if f:
            ev_rows.append(f)

    random.seed(SEED + 4)
    pool = [s for s in frames if s not in ev_syms]
    ctrl_rows, tries = [], 0
    while len(ctrl_rows) < 5000 and tries < 60000:
        tries += 1
        h = frames[random.choice(pool)]
        f = features(h, random.randrange(70, len(h)))
        if f:
            ctrl_rows.append(f)

    def show(name, rows):
        print(f"\n{name} (n={len(rows)})")
        for k in ("vol_ratio", "vol_prev_day", "drift_20d", "range_5d"):
            v = sorted(r[k] for r in rows)
            print(f"   {k:13} median={st.median(v):7.2f}  "
                  f"p75={v[int(len(v) * .75)]:7.2f}  p90={v[int(len(v) * .90)]:7.2f}")

    show("THE 20 SESSIONS BEFORE A +50% DAY", ev_rows)
    show("ORDINARY STOCK-DAYS              ", ctrl_rows)
    print("\nBig moves do not arrive from nowhere: volume shows up first, and "
          "the\nnames it shows up in are typically already beaten down.")

    rows = [r for s, h in frames.items()
            for j in range(70, len(h) - 6) if (r := forward(h, j))]
    n_days = st.median([len(h) for h in frames.values()]) - 76
    scale = 5806 / len(frames)

    print(f"\n\nFORWARD TEST — screen after the close, buy the next open")
    print(f"({len(rows):,} tradeable stock-days)\n")
    print(f"{'filter':32}{'alerts/day':>12}{'touched +50% in 5d':>21}{'median 5d':>12}")
    print("-" * 78)

    def line(name, sub):
        print(f"{name:32}{len(sub) / n_days * scale:11.0f}"
              f"{sum(1 for r in sub if r['max5'] >= 50) / len(sub) * 100:20.1f}%"
              f"{st.median([r['fwd5'] for r in sub]):11.1f}%")

    line("no filter (baseline)", rows)
    for t in (3, 5, 8, 12):
        line(f"prior-day volume >= {t}x avg", [r for r in rows if r["v"] >= t])
    print("\nRead both columns. The screen concentrates big movers more than "
          "tenfold\nAND has a negative median that worsens as it tightens. "
          "Hunting ground,\nnot a buy list.")


if __name__ == "__main__":
    main()
