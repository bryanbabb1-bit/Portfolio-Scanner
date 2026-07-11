"""Options engine — turn a stock conviction into a defined-risk options trade.

The client wants to express high-conviction views by BUYING contracts (long
calls for bullish, long puts for bearish) so the risk is CAPPED at the premium
paid — no share assignment, no unlimited downside. This service fetches the
live chain (yfinance), picks a sensible expiration + strike for a thesis, and
computes the numbers that matter: cost, max risk (= premium), breakeven, delta,
and the payoff if the target is hit. Greeks are Black-Scholes (yfinance gives
IV, not Greeks). Everything here is deterministic — no Claude.
"""
from __future__ import annotations

import math
import time
from datetime import date, datetime

from ..config import settings

_RF = 0.04  # risk-free rate for Black-Scholes
_cache: dict[str, tuple[float, object]] = {}
_TTL = 300


def _f(v, default: float = 0.0) -> float:
    """NaN-safe float — yfinance leaves openInterest/bid/etc. as NaN, and
    `int(nan or 0)` throws because NaN is truthy."""
    try:
        x = float(v)
        return default if math.isnan(x) else x
    except (TypeError, ValueError):
        return default


def _norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _bs_delta(spot: float, strike: float, t_years: float, iv: float, call: bool) -> float | None:
    if t_years <= 0 or iv <= 0 or spot <= 0 or strike <= 0:
        return None
    d1 = (math.log(spot / strike) + (_RF + iv * iv / 2) * t_years) / (iv * math.sqrt(t_years))
    return round(_norm_cdf(d1) if call else _norm_cdf(d1) - 1, 3)


def _cache_get(key: str):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < _TTL:
        return hit[1]
    return None


def _cache_put(key: str, val):
    _cache[key] = (time.time(), val)


def _days(exp: str, today: date) -> int:
    return (datetime.strptime(exp, "%Y-%m-%d").date() - today).days


def _spot(tkr) -> float | None:
    try:
        p = tkr.fast_info.last_price
        if p:
            return float(p)
    except Exception:
        pass
    try:
        return float(tkr.history(period="1d")["Close"].iloc[-1])
    except Exception:
        return None


def suggest(symbol: str, side: str = "call", target: float | None = None,
            horizon_days: int = 120) -> dict | None:
    """A single defined-risk long-option trade for a thesis on `symbol`.

    side: 'call' (bullish) | 'put' (bearish). horizon_days: how long the thesis
    needs — picks the expiration nearest that (min ~25 days out). Strike is
    chosen near a ~0.60-delta (moves well with the stock without paying up for
    deep ITM), among liquid contracts.
    """
    symbol = symbol.upper()
    key = f"{symbol}:{side}:{target}:{horizon_days}"
    cached = _cache_get(key)
    if cached is not None:
        return cached
    if settings.DATA_MODE == "mock":
        _cache_put(key, None)
        return None
    try:
        import yfinance as yf
        tkr = yf.Ticker(symbol)
        exps = list(tkr.options or [])
        spot = _spot(tkr)
        if not exps or not spot:
            _cache_put(key, None)
            return None
        today = date.today()
        call = side == "call"
        usable = sorted(((e, _days(e, today)) for e in exps if _days(e, today) >= 25),
                        key=lambda x: abs(x[1] - horizon_days))
        if not usable:
            usable = sorted(((e, _days(e, today)) for e in exps),
                            key=lambda x: abs(x[1] - horizon_days))

        # Try the expiration nearest the horizon; if its chain has no live market
        # (stale IV / zero quotes — common on some far months), fall back to the
        # next-nearest until one is genuinely tradeable.
        best = None
        exp = None
        dte = None
        for e, d in usable[:8]:
            t_years = max(d, 1) / 365
            try:
                chain = tkr.option_chain(e)
                df = chain.calls if call else chain.puts
            except Exception:
                continue
            cand_best = None
            for _, row in df.iterrows():
                strike = _f(row.get("strike"))
                iv = _f(row.get("impliedVolatility"))
                bid = _f(row.get("bid"))
                ask = _f(row.get("ask"))
                oi = int(_f(row.get("openInterest")))
                vol = int(_f(row.get("volume")))
                if strike <= 0 or bid <= 0 or ask <= 0:
                    continue
                if iv < 0.05 or iv > 3.0 or oi < 100:
                    continue
                # a directional bet lives near the money — reject deep ITM/OTM
                # (which is also where the stale-data garbage hides).
                if not (0.6 * spot <= strike <= 1.6 * spot):
                    continue
                delta = _bs_delta(spot, strike, t_years, iv, call)
                if delta is None or not (0.35 <= abs(delta) <= 0.75):
                    continue
                score = abs(abs(delta) - 0.60)  # aim ~0.60 delta directional
                cand = {"strike": strike, "premium": round((bid + ask) / 2, 2),
                        "iv": round(iv, 3), "delta": delta, "open_interest": oi,
                        "volume": vol, "bid": bid, "ask": ask, "score": score}
                if cand["premium"] > 0 and (cand_best is None or score < cand_best["score"]):
                    cand_best = cand
            if cand_best:
                best, exp, dte = cand_best, e, d
                break
        if not best:
            _cache_put(key, None)
            return None

        strike = best["strike"]
        premium = best["premium"]
        cost = round(premium * 100)              # one contract controls 100 shares
        breakeven = round(strike + premium, 2) if call else round(strike - premium, 2)
        spread = best["ask"] - best["bid"]
        spread_pct = round(spread / premium * 100, 1) if premium and best["bid"] > 0 else None

        out = {
            "symbol": symbol, "side": side, "expiration": exp, "dte": dte,
            "strike": strike, "premium": premium,
            "cost_per_contract": cost,           # = MAX RISK per contract (capped)
            "breakeven": breakeven,
            "delta": best["delta"], "iv_pct": round(best["iv"] * 100, 1),
            "open_interest": best["open_interest"], "volume": best["volume"],
            "spread_pct": spread_pct, "spot": round(spot, 2),
        }
        if target:
            intrinsic = max(0.0, (target - strike) if call else (strike - target))
            value_at_target = round(intrinsic * 100)
            out["target"] = target
            out["value_at_target"] = value_at_target
            out["profit_at_target"] = value_at_target - cost
            out["return_at_target_x"] = round(value_at_target / cost, 1) if cost else None
        _cache_put(key, out)
        return out
    except Exception:
        _cache_put(key, None)
        return None


def expirations(symbol: str) -> list[dict]:
    """Available expirations with days-to-expiry, for the UI to browse."""
    if settings.DATA_MODE == "mock":
        return []
    try:
        import yfinance as yf
        today = date.today()
        return [{"date": e, "dte": _days(e, today)}
                for e in (yf.Ticker(symbol.upper()).options or [])]
    except Exception:
        return []
