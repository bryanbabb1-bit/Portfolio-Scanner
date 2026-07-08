"""Relationship graph — how tightly the book's holdings move together.

Builds a correlation web from daily returns so the dashboard can show, at a
glance, that (e.g.) the AI-chip names are one tightly-coupled block rather than
diversified bets. Nodes = holdings (sized by weight, colored by theme), edges =
pairwise return correlation above a threshold.
"""
from __future__ import annotations

import pandas as pd

from . import market_data
from . import portfolio as pf

# instrument types that break correlation / aren't real equity bets
_EXCLUDE = {"SGOV"}


def build_graph(min_corr: float = 0.5) -> dict:
    summary, reports = pf.portfolio_summary()
    total = summary.total_market_value or 1
    held = [r for r in reports
            if (r.market_value or 0) > 0 and r.symbol not in _EXCLUDE]

    rets: dict[str, pd.Series] = {}
    for r in held:
        try:
            close = market_data.get_price_data(r.symbol).history["Close"].dropna()
            if len(close) > 30:
                rets[r.symbol] = close.pct_change().dropna()
        except Exception:
            continue

    nodes = [{"symbol": r.symbol, "theme": r.theme or "Other",
              "weight": round((r.market_value or 0) / total, 4)}
             for r in held if r.symbol in rets]

    edges: list[dict] = []
    corrs: list[float] = []
    if len(rets) >= 2:
        df = pd.DataFrame(rets).dropna(how="any")
        if len(df) >= 20:
            cm = df.corr()
            cols = list(cm.columns)
            for i in range(len(cols)):
                for j in range(i + 1, len(cols)):
                    c = cm.iloc[i, j]
                    if pd.isna(c):
                        continue
                    c = float(c)
                    corrs.append(c)
                    if c >= min_corr:
                        edges.append({"a": cols[i], "b": cols[j], "corr": round(c, 3)})

    avg = round(sum(corrs) / len(corrs), 3) if corrs else None
    return {
        "nodes": nodes,
        "edges": edges,
        "avg_corr": avg,
        "pairs": len(corrs),
        "source": summary.source,
    }
