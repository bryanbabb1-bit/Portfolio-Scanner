"""Robustness matrix — does a rule's edge survive changing the assumptions?

A backtest produces one number per rule, and that number quietly bakes in
choices nobody argued for: WHICH forward horizon to grade at, and WHICH market
conditions happened to be in the sample. Change either and the number moves.
So the number is not a fact about the rule; it is a fact about the rule under
those choices.

This re-grades every rule across a grid:

    HORIZONS  5 / 20 / 60 sessions      (same signals, measured later)
    REGIMES   rising / flat / falling   (different signals, split by market)

Then you read the PATTERN instead of the number. A row that is negative
everywhere is a genuinely broken rule. A row that is negative in exactly one
cell is a bad test, not a bad rule.

The specific danger this exists to catch: `sharp-breakdown` and `trend-break`
are CRASH rules. Judging them over a sample with no crash and concluding they
do not work is like removing a smoke alarm because there was no fire this
year. The falling-market column is the only cell that can honestly rule on
them.

Regime is classified from the BENCHMARK's trailing return AT SIGNAL TIME, not
its forward return. That keeps the split causal — it is a condition you could
actually know when the signal fired, so "this rule works in downtrends" stays
an actionable statement rather than a hindsight one.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import market_data

BENCHMARK = "SPY"
HORIZONS = (5, 20, 60)
REGIMES = ("rising", "flat", "falling")

# Trailing benchmark return that defines each regime.
REGIME_LOOKBACK = 20
RISING_AT = 3.0      # SPY +3% or better over the trailing 20 sessions
FALLING_AT = -3.0    # SPY -3% or worse

# A cell below this many signals is reported but never carries a verdict.
MIN_CELL = 15


def regime_map(years: int = 5) -> dict[str, str]:
    """date string -> 'rising' | 'flat' | 'falling', from the benchmark."""
    try:
        md = market_data.get_deep_history(BENCHMARK, years=years)
    except Exception:
        return {}
    close = md.history["Close"].copy()
    idx = pd.to_datetime(close.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    close.index = idx.normalize()
    close = close[~close.index.duplicated(keep="last")]

    trail = (close / close.shift(REGIME_LOOKBACK) - 1) * 100
    out: dict[str, str] = {}
    for ts, val in trail.items():
        if val is None or (isinstance(val, float) and np.isnan(val)):
            continue
        if val >= RISING_AT:
            r = "rising"
        elif val <= FALLING_AT:
            r = "falling"
        else:
            r = "flat"
        out[pd.Timestamp(ts).strftime("%Y-%m-%d")] = r
    return out


def _cell(rows: list[dict], key: str) -> dict:
    """Grade one bucket of signals on one effective-return field."""
    vals = [r[key] for r in rows if r.get(key) is not None]
    if not vals:
        return {"n": 0, "avg": None, "win_rate": None, "thin": True}
    wins = sum(1 for v in vals if v > 0)
    return {
        "n": len(vals),
        "avg": round(sum(vals) / len(vals), 2),
        "win_rate": round(100 * wins / len(vals), 1),
        "thin": len(vals) < MIN_CELL,
    }


def _verdict(cells: dict) -> tuple[str, str]:
    """Read the pattern across a rule's row. Returns (verdict, reason)."""
    solid = {k: c for k, c in cells.items() if not c["thin"] and c["avg"] is not None}
    if len(solid) < 3:
        return "UNPROVEN", (
            f"Only {len(solid)} of {len(cells)} conditions have "
            f"{MIN_CELL}+ signals — not enough coverage to judge."
        )

    signs = {k: (c["avg"] > 0) for k, c in solid.items()}
    if all(signs.values()):
        return "ROBUST", (
            f"Positive in all {len(solid)} measurable conditions — the edge "
            "does not depend on the horizon or the market."
        )
    if not any(signs.values()):
        return "BROKEN", (
            f"Negative in all {len(solid)} measurable conditions — this is the "
            "rule, not the test."
        )
    good = [k for k, v in signs.items() if v]
    bad = [k for k, v in signs.items() if not v]
    return "FRAGILE", (
        f"Works in {', '.join(good)} but not {', '.join(bad)} — the single "
        "headline number was hiding a split."
    )


def matrix(signals: list[dict], years: int = 5) -> dict:
    """Build the full rule x condition grid from raw replayed signals."""
    regimes = regime_map(years)
    if not regimes:
        return {"columns": [], "rules": [], "note": "Benchmark history unavailable."}

    by_rule: dict[str, list[dict]] = {}
    unclassified = 0
    for s in signals:
        r = regimes.get(s["date"])
        if r is None:
            unclassified += 1
            continue
        by_rule.setdefault(s["rule"], []).append({**s, "regime": r})

    columns = [f"{h}d" for h in HORIZONS] + list(REGIMES)
    rows = []
    for rule, rows_for_rule in sorted(by_rule.items()):
        cells: dict[str, dict] = {}
        # Horizon columns: every signal, measured at a different distance.
        for h in HORIZONS:
            cells[f"{h}d"] = _cell(rows_for_rule, f"eff_{h}")
        # Regime columns: the sample split, all graded at the headline horizon.
        for reg in REGIMES:
            cells[reg] = _cell([r for r in rows_for_rule if r["regime"] == reg], "eff_20")

        verdict, reason = _verdict(cells)
        rows.append({
            "rule": rule,
            "side": rows_for_rule[0]["side"],
            "signals": len(rows_for_rule),
            "cells": cells,
            "verdict": verdict,
            "reason": reason,
        })

    order = {"BROKEN": 0, "FRAGILE": 1, "UNPROVEN": 2, "ROBUST": 3}
    rows.sort(key=lambda r: (order.get(r["verdict"], 9), -r["signals"]))

    counts: dict[str, int] = {}
    for reg in REGIMES:
        counts[reg] = sum(1 for s in signals if regimes.get(s["date"]) == reg)

    return {
        "columns": columns,
        "horizons": [f"{h}d" for h in HORIZONS],
        "regimes": list(REGIMES),
        "rules": rows,
        "min_cell": MIN_CELL,
        "regime_signal_counts": counts,
        "unclassified": unclassified,
        "definition": (
            f"Regime is the benchmark's trailing {REGIME_LOOKBACK}-session "
            f"return at the moment the signal fired: rising >= +{RISING_AT:g}%, "
            f"falling <= {FALLING_AT:g}%, flat in between. Regime columns are "
            f"graded at 20 sessions."
        ),
    }


def crash_rule_warnings(matrix_result: dict, retired: set[str]) -> list[str]:
    """Flag retirements the falling-market column does not actually support.

    A rule retired on an average dominated by rising markets, whose falling
    cell is thin or positive, was not proven bad — it was untested where it
    was supposed to matter."""
    warnings: list[str] = []
    for row in matrix_result.get("rules", []):
        if row["rule"] not in retired:
            continue
        fall = row["cells"].get("falling") or {}
        if fall.get("n", 0) == 0:
            warnings.append(
                f"{row['rule']} is retired but NEVER fired in a falling market "
                "in this sample — the case against it comes entirely from "
                "rising and flat conditions."
            )
        elif fall.get("thin"):
            warnings.append(
                f"{row['rule']} is retired on {fall['n']} falling-market "
                f"signal(s), under the {MIN_CELL} needed to judge. Its "
                "protective value is still unproven, not disproven."
            )
        elif (fall.get("avg") or 0) > 0:
            warnings.append(
                f"{row['rule']} is retired, but it made {fall['avg']:+.2f}% on "
                f"{fall['n']} falling-market signals. It may be a crash rule "
                "that was judged in a market with no crash — reconsider."
            )
    return warnings
