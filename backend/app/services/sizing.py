"""How much upside is available from position SIZE, given a proven edge.

WHY THIS EXISTS
---------------
The pullback model has a statistically real edge (+0.233R, t 2.48) and was run
at 2% risk per trade, which is a smoothness setting, not a growth setting. The
question "why do people take 10k to 1M when our backtest trails SPY" is mostly
answered here rather than in the rules: with a positive edge, terminal wealth is
driven far more by bet SIZE than by finding a better setup.

The Kelly criterion gives the bet fraction that maximises the long-run growth
rate. For a distribution of R-multiples it is approximately

    f* = mean(R) / variance(R)

At +0.233R with a 1.185 standard deviation that is about 16.6% of equity risked
per trade. The model was running at 2% — roughly a TENTH of the growth-optimal
size. That is the headroom, and it is large.

WHY THIS IS ALSO DANGEROUS
--------------------------
Two reasons, both of which this module measures rather than asserts.

1. Kelly is optimal only if the edge estimate is CORRECT. The 95% confidence
   interval on this edge runs +0.050R to +0.424R. Sized for the top of that
   range while the truth is the bottom, you are massively over-betting, and
   over-betting past 2x Kelly has a NEGATIVE growth rate — you lose money with a
   winning system. So every result here is also run at the pessimistic end of
   the interval.

2. Median and mean outcomes diverge wildly at high bet fractions. The average
   ending balance can look spectacular while the typical one is a loss, because
   the mean is dragged up by a handful of enormous paths. Reporting a mean here
   would be the single most misleading number available, so the percentiles are
   what get reported.
"""
from __future__ import annotations

import random
import statistics as st
from dataclasses import dataclass


@dataclass
class SizingResult:
    risk_pct: float
    median_final: float
    p10: float
    p25: float
    p75: float
    p90: float
    p99: float
    median_cagr: float
    prob_ruin: float          # ended below 10% of starting capital
    prob_loss: float
    prob_10x: float
    prob_100x: float
    median_max_dd: float


def kelly_fraction(rs: list[float]) -> float:
    """Growth-optimal risk per trade for this R distribution."""
    if len(rs) < 2:
        return 0.0
    var = st.pvariance(rs)
    return st.mean(rs) / var if var > 0 else 0.0


def simulate_sizing(rs: list[float], risk_pct: float, trades_per_year: float,
                    years: float, runs: int = 5000, start: float = 1000.0,
                    seed: int = 7) -> SizingResult:
    """Bootstrap terminal wealth by resampling the ACTUAL trade outcomes.

    Resampling the real R-multiples keeps the fat tails and the losing streaks
    that a normal-distribution assumption would quietly smooth away — and those
    streaks are exactly what decides whether an aggressive bet size survives.
    """
    rng = random.Random(seed)
    n = max(1, int(round(trades_per_year * years)))
    finals: list[float] = []
    dds: list[float] = []

    for _ in range(runs):
        equity = start
        peak = start
        worst = 0.0
        for _ in range(n):
            r = rs[rng.randrange(len(rs))]
            # Risk a FIXED FRACTION of current equity: the position shrinks after
            # losses, which is what makes ruin asymptotic rather than certain.
            equity *= (1 + risk_pct * r)
            if equity <= start * 0.01:
                equity = start * 0.01      # effectively wiped out; stop compounding
                break
            peak = max(peak, equity)
            worst = max(worst, (peak - equity) / peak)
        finals.append(equity)
        dds.append(worst)

    finals.sort()
    dds.sort()

    def pct(v: list[float], p: float) -> float:
        return v[min(len(v) - 1, int(len(v) * p))]

    median = pct(finals, 0.50)
    return SizingResult(
        risk_pct=risk_pct,
        median_final=round(median, 2),
        p10=round(pct(finals, 0.10), 2),
        p25=round(pct(finals, 0.25), 2),
        p75=round(pct(finals, 0.75), 2),
        p90=round(pct(finals, 0.90), 2),
        p99=round(pct(finals, 0.99), 2),
        median_cagr=round(((median / start) ** (1 / years) - 1) * 100, 2) if years > 0 else 0.0,
        prob_ruin=round(sum(1 for f in finals if f <= start * 0.10) / len(finals) * 100, 1),
        prob_loss=round(sum(1 for f in finals if f < start) / len(finals) * 100, 1),
        prob_10x=round(sum(1 for f in finals if f >= start * 10) / len(finals) * 100, 1),
        prob_100x=round(sum(1 for f in finals if f >= start * 100) / len(finals) * 100, 1),
        median_max_dd=round(pct(dds, 0.50) * 100, 1),
    )


def study(rs: list[float], trades_per_year: float, years: float = 5.0,
          levels: tuple[float, ...] = (0.02, 0.05, 0.10, 0.15, 0.20, 0.25, 0.33),
          runs: int = 5000) -> dict:
    """Run the risk ladder at the MEASURED edge and at the pessimistic end of its
    confidence interval. The second table is the one that matters — it answers
    "what if the edge is really at the bottom of what the data supports"."""
    mean = st.mean(rs)
    sd = st.stdev(rs)
    se = sd / (len(rs) ** 0.5)
    low = mean - 1.96 * se          # bottom of the 95% interval

    # Shift the whole distribution down so its mean equals the pessimistic edge,
    # keeping the observed shape and variance intact.
    shift = low - mean
    pessimistic = [r + shift for r in rs]

    return {
        "n_trades": len(rs),
        "measured_edge_r": round(mean, 3),
        "pessimistic_edge_r": round(low, 3),
        "sd_r": round(sd, 3),
        "kelly_pct": round(kelly_fraction(rs) * 100, 1),
        "kelly_pessimistic_pct": round(kelly_fraction(pessimistic) * 100, 1),
        "trades_per_year": trades_per_year,
        "years": years,
        "measured": [vars(simulate_sizing(rs, lv, trades_per_year, years, runs))
                     for lv in levels],
        "pessimistic": [vars(simulate_sizing(pessimistic, lv, trades_per_year,
                                             years, runs))
                        for lv in levels],
    }
