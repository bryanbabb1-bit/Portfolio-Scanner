"""Position sizing: where the upside actually lives, and what it costs.

These tests pin the properties that make the study honest — that over-betting
is punished, that ruin is reported, and that the pessimistic case is genuinely
pessimistic. A sizing study that only ever looks encouraging would be a way to
talk yourself into 20% risk.
"""
from __future__ import annotations

import random

import pytest

from app.services import sizing


def _edge(mean_r: float, n: int = 400, sd: float = 1.2, seed: int = 3) -> list[float]:
    """A sample whose mean is EXACTLY mean_r.

    Drawn samples are re-centred on purpose: at n=400 and sd=1.2 the sample mean
    carries a standard error of 0.06, so an uncentred draw for a +0.05 edge lands
    negative often enough to make these tests flap for reasons that have nothing
    to do with the code under test.
    """
    rng = random.Random(seed)
    raw = [rng.gauss(mean_r, sd) for _ in range(n)]
    drift = sum(raw) / n - mean_r
    return [r - drift for r in raw]


def test_kelly_scales_with_the_edge():
    small, big = sizing.kelly_fraction(_edge(0.05)), sizing.kelly_fraction(_edge(0.30))
    assert 0 < small < big


def test_no_edge_means_no_bet():
    assert sizing.kelly_fraction(_edge(0.0)) == pytest.approx(0.0, abs=0.05)


def test_a_negative_edge_gives_a_negative_kelly():
    # Betting into a losing system has no optimal size; the number must be
    # negative rather than quietly clipped to something that looks bettable.
    assert sizing.kelly_fraction(_edge(-0.2)) < 0


def test_growth_rises_then_falls_past_kelly():
    # The whole point of the study: more risk is better until it abruptly isn't.
    rs = _edge(0.25)
    k = sizing.kelly_fraction(rs)
    conservative = sizing.simulate_sizing(rs, k * 0.3, 30, 5, runs=3000)
    near_optimal = sizing.simulate_sizing(rs, k, 30, 5, runs=3000)
    over = sizing.simulate_sizing(rs, min(k * 2.5, 0.9), 30, 5, runs=3000)

    assert near_optimal.median_final > conservative.median_final
    assert over.median_final < near_optimal.median_final


def test_ruin_is_reported_and_grows_with_risk():
    rs = _edge(0.10)
    low = sizing.simulate_sizing(rs, 0.02, 30, 5, runs=3000)
    high = sizing.simulate_sizing(rs, 0.40, 30, 5, runs=3000)
    assert low.prob_ruin <= high.prob_ruin
    assert high.prob_ruin > 0


def test_percentiles_are_ordered():
    r = sizing.simulate_sizing(_edge(0.2), 0.10, 30, 5, runs=3000)
    assert r.p10 <= r.p25 <= r.median_final <= r.p75 <= r.p90 <= r.p99


def test_the_study_reports_a_pessimistic_case_that_is_actually_worse():
    rs = _edge(0.25, n=150)
    s = sizing.study(rs, trades_per_year=30, years=5, levels=(0.02, 0.15), runs=2000)
    assert s["pessimistic_edge_r"] < s["measured_edge_r"]
    assert s["kelly_pessimistic_pct"] < s["kelly_pct"]
    for meas, pess in zip(s["measured"], s["pessimistic"]):
        assert pess["median_final"] <= meas["median_final"]


def test_results_are_deterministic():
    # Same seed, same answer — a sizing decision must not move between runs.
    rs = _edge(0.2)
    a = sizing.simulate_sizing(rs, 0.1, 30, 5, runs=2000)
    b = sizing.simulate_sizing(rs, 0.1, 30, 5, runs=2000)
    assert a.median_final == b.median_final


def test_a_wiped_out_path_stops_compounding():
    # Once the account is gone it must stay gone, not resurrect on a big winner.
    rs = _edge(-0.5, sd=1.5)
    r = sizing.simulate_sizing(rs, 0.5, 40, 5, runs=1500)
    assert r.p10 >= 10.0 - 1e-9      # floored at 1% of the $1,000 start
    assert r.prob_ruin > 50
