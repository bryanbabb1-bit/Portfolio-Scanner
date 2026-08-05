"""Paper-trading simulation — a deterministic day-trading model on $1,000.

The point is not to make money on paper. It is to find out whether a fixed rule
set has an edge BEFORE any real money is involved, which means every decision
here has to be reproducible: same bars in, same trades out, no judgement
anywhere in the loop.

WHY A CASH ACCOUNT
------------------
$1,000 cannot day trade a margin account. Four or more day trades in five
business days makes you a Pattern Day Trader, which requires $25,000 minimum
equity. So this models a CASH account, where PDT does not apply but settlement
does:

  * a sale settles T+1 (trade date plus one business day),
  * you may only BUY with settled cash,
  * buying with unsettled proceeds and selling before they settle is a Good
    Faith Violation; three in twelve months restricts the account for 90 days.

Because buys draw only from settled cash, the engine cannot commit a GFV by
construction. The practical consequence is the one that shapes the strategy:

  the day's total notional budget is the settled cash you started the day with.

$1,000 buys two $500 round trips or four $250s — not unlimited trades. Blocked
entries are counted rather than quietly skipped, because "the model wanted to
trade and the account could not" is a real result, not an error.

SIZING, AND WHY 2% IS OFTEN UNREACHABLE
---------------------------------------
Risk per trade is a percentage of equity divided by the stop distance. On a
small account the cash cap usually binds first: at a 0.5%-wide stop, a $20 risk
budget implies a $4,000 position, and there is only $1,000. So realised risk per
trade is frequently well under the configured number, and the engine records
what it actually risked rather than what it was allowed to.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from datetime import date, timedelta

import pandas as pd

from ..config import settings
from .technical import _atr, _rsi

# Liquid, optionable, high-volume names. Day trading needs tight spreads and
# real depth; an illiquid name makes the fill assumptions here fiction.
# No crypto, by instruction.
UNIVERSE: tuple[str, ...] = (
    "SPY", "QQQ", "IWM", "AAPL", "MSFT", "NVDA", "AMD", "META", "AMZN", "GOOGL",
    "TSLA", "NFLX", "AVGO", "CRWD", "PANW", "COIN", "SMCI", "MU", "UBER", "XLE",
)


@dataclass
class PaperConfig:
    """Every knob the model has. Nothing is hard-coded in the logic below, so a
    parameter sweep changes numbers here and never touches the rules."""
    starting_cash: float = 1000.0
    risk_pct: float = 0.02              # of equity, per trade
    daily_stop_pct: float = 0.06        # flat for the day past this drawdown
    min_rr: float = 2.0                 # reject anything that can't pay 2:1
    max_open: int = 2
    max_trades_per_day: int = 4
    # 5-minute bars: three of them is the 15-minute opening range.
    opening_range_bars: int = 3
    # Minutes after the 09:30 open. No new entries late in the day (the trade
    # needs time to work), and everything is flat before the close because an
    # overnight hold is not a day trade and would tie up unsettled cash.
    entry_cutoff_min: int = 300         # 14:30 ET
    flat_by_min: int = 385              # 15:55 ET
    slippage: float = 0.05              # per share, each way
    atr_mult: float = 1.5
    scale_out_frac: float = 0.5         # half off at 1R, stop to breakeven
    vol_mult: float = 1.5               # breakout bar volume vs session average
    rsi_low: float = 50.0               # trend confirmation...
    rsi_high: float = 70.0              # ...but not already extended

    @classmethod
    def from_settings(cls) -> "PaperConfig":
        return cls(
            starting_cash=float(getattr(settings, "PAPER_START_CASH", 1000.0)),
            risk_pct=float(getattr(settings, "PAPER_RISK_PCT", 0.02)),
            daily_stop_pct=float(getattr(settings, "PAPER_DAILY_STOP_PCT", 0.06)),
            max_open=int(getattr(settings, "PAPER_MAX_OPEN", 2)),
            max_trades_per_day=int(getattr(settings, "PAPER_MAX_TRADES", 4)),
        )


# ------------------------------------------------------------------ settlement
def next_business_day(d: date) -> date:
    """T+1 in trading terms: the next weekday. Exchange holidays are not modelled
    — they would only ever make settlement slower, so this is the optimistic
    bound and never flatters a trade that settlement would have blocked."""
    nxt = d + timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += timedelta(days=1)
    return nxt


@dataclass
class Ledger:
    """Settled vs unsettled cash. The whole cash-account constraint lives here."""
    settled: float
    pending: list[tuple[date, float]] = field(default_factory=list)

    def settle_through(self, today: date) -> float:
        """Move everything whose settlement date has arrived into settled cash."""
        due = [(d, amt) for d, amt in self.pending if d <= today]
        self.pending = [(d, amt) for d, amt in self.pending if d > today]
        moved = sum(amt for _, amt in due)
        self.settled += moved
        return moved

    def buy(self, cost: float) -> bool:
        """Spend settled cash. Refuses rather than borrowing — this is the line
        that makes it a cash account instead of a margin account."""
        if cost > self.settled + 1e-9:
            return False
        self.settled -= cost
        return True

    def sell(self, proceeds: float, trade_day: date) -> None:
        self.pending.append((next_business_day(trade_day), proceeds))

    @property
    def unsettled(self) -> float:
        return sum(amt for _, amt in self.pending)

    @property
    def total(self) -> float:
        return self.settled + self.unsettled


# ----------------------------------------------------------------------- trades
@dataclass
class Trade:
    symbol: str
    day: str
    entry_time: str
    entry: float
    # The stop the trade was TAKEN with. Immutable: it defines the R the whole
    # review is denominated in. The breakeven move writes to current_stop, so a
    # scaled winner can still be audited against the risk it originally took.
    stop: float
    target: float
    shares: float
    risk_dollars: float          # what it ACTUALLY risked, not the budget
    setup: str
    exits: list[dict] = field(default_factory=list)
    realized: float = 0.0
    r_multiple: float | None = None
    exit_reason: str = ""
    open_shares: float = 0.0
    scaled: bool = False
    current_stop: float = 0.0    # the working stop; moves to breakeven on a scale

    @property
    def is_open(self) -> bool:
        return self.open_shares > 1e-9


# -------------------------------------------------------------------- indicators
def session_vwap(df: pd.DataFrame) -> pd.Series:
    """Volume-weighted average price, reset every session — an intraday anchor
    only means anything within its own day."""
    typical = (df["High"] + df["Low"] + df["Close"]) / 3.0
    pv = (typical * df["Volume"]).groupby(df.index.date).cumsum()
    vol = df["Volume"].groupby(df.index.date).cumsum()
    return pv / vol.replace(0, pd.NA)


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    """Attach every indicator the rules read. Vectorised and computed once per
    symbol, so a bar's decision is a row lookup and cannot peek ahead."""
    out = df.copy()
    out["vwap"] = session_vwap(out)
    out["ema20"] = out["Close"].ewm(span=20, adjust=False).mean()
    out["rsi"] = _rsi(out["Close"])
    # The "is it already extended" test has to read the bar BEFORE the break.
    # A decisive breakout is precisely what spikes RSI on 5-minute bars, so
    # testing the breakout bar itself rejects almost every real breakout — the
    # question is whether the name had already run going INTO the move.
    out["rsi_prev"] = out["rsi"].shift(1)
    out["atr"] = _atr(out)
    # Average session volume up to and including this bar — a like-for-like
    # comparison, since volume is front-loaded into the open.
    grp = out.groupby(out.index.date)["Volume"]
    out["vol_avg"] = grp.transform(lambda s: s.expanding().mean())
    return out


# --------------------------------------------------------------------- strategy
def opening_range(bars: pd.DataFrame, n: int) -> tuple[float, float] | None:
    if len(bars) < n:
        return None
    first = bars.iloc[:n]
    return float(first["High"].max()), float(first["Low"].min())


def entry_signal(row: pd.Series, or_high: float, cfg: PaperConfig) -> str | None:
    """The setup, as one boolean expression. Returns the reason it fired, or None.

    Long-only opening-range breakout, aligned with intraday trend. Every clause
    exists to reject a different way the breakout fails: below VWAP the sellers
    still own the day, below the 20 EMA there is no trend to join, thin volume
    means nobody is behind the break, and an RSI already through the ceiling
    BEFORE the break means the move happened without you.
    """
    close = float(row["Close"])
    if not (close > or_high):
        return None
    for value in (row.get("vwap"), row.get("ema20"), row.get("rsi_prev"),
                  row.get("vol_avg"), row.get("atr")):
        if value is None or pd.isna(value):
            return None
    if close <= float(row["vwap"]):
        return None
    if close <= float(row["ema20"]):
        return None
    if float(row["Volume"]) < cfg.vol_mult * float(row["vol_avg"]):
        return None
    rsi_prev = float(row["rsi_prev"])
    if not (cfg.rsi_low <= rsi_prev <= cfg.rsi_high):
        return None
    return (f"ORB {close:.2f} > OR high {or_high:.2f}, above VWAP and 20EMA, "
            f"{float(row['Volume']) / float(row['vol_avg']):.1f}x volume, "
            f"RSI {rsi_prev:.0f} into the break")


def plan_trade(row: pd.Series, fill: float, or_low: float,
               equity: float, buying_power: float,
               cfg: PaperConfig) -> tuple[float, float, float, float] | None:
    """Size the trade off the price actually paid. Returns
    (entry, stop, target, shares), or None if it can't be taken on this account.

    `fill` is the next bar's open, NOT the breakout level. The signal is only
    known once a bar has CLOSED above the range, so filling at the range high
    would be buying a price that has already gone by — which is exactly the
    look-ahead that produced a 90% win rate and a profit factor of 10 on the
    first run of this backtest.

    The stop is the TIGHTER of the opening-range low and an ATR stop: a wide
    opening range should not be allowed to quietly buy a huge position's worth
    of risk.
    """
    entry = fill + cfg.slippage
    atr = float(row["atr"])
    stop = max(or_low, entry - cfg.atr_mult * atr)
    risk_per_share = entry - stop
    if risk_per_share <= 0.01:
        return None                      # no definable risk, no trade
    target = entry + cfg.min_rr * risk_per_share

    budget = equity * cfg.risk_pct
    shares = budget / risk_per_share
    # The cash cap. On a small account this is usually what binds, not the risk
    # budget — which is why realised risk per trade often lands well under the
    # configured percentage.
    #
    # Floored, not rounded: at the cap, shares * entry lands a fraction of a cent
    # ABOVE buying power on binary floats, the ledger correctly refuses to lend,
    # and the trade silently books as blocked-by-settlement instead of filling.
    # Cap any one position at its share of the book. Without this the first
    # signal of the day spends the entire $1,000, max_open is unreachable in
    # practice, and the account rides on a single name every session.
    per_position = equity / max(cfg.max_open, 1)
    max_shares = min(buying_power, per_position) / entry
    shares = math.floor(min(shares, max_shares) * 1e6) / 1e6
    if shares * entry < 1.0:
        return None                      # position too small to be meaningful
    return entry, stop, target, shares


# ------------------------------------------------------------------- simulation
@dataclass
class Result:
    config: dict
    trades: list[dict]
    equity_curve: list[dict]
    metrics: dict
    blocked: dict
    days: int
    symbols: list[str]


def _metrics(trades: list[Trade], curve: list[dict], start: float) -> dict:
    closed = [t for t in trades if not t.is_open and t.exits]
    wins = [t for t in closed if t.realized > 0]
    losses = [t for t in closed if t.realized <= 0]
    gross_win = sum(t.realized for t in wins)
    gross_loss = -sum(t.realized for t in losses)
    rs = [t.r_multiple for t in closed if t.r_multiple is not None]
    equity = curve[-1]["equity"] if curve else start

    peak = start
    max_dd = 0.0
    for point in curve:
        peak = max(peak, point["equity"])
        if peak > 0:
            max_dd = max(max_dd, (peak - point["equity"]) / peak)

    return {
        "trades": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(closed) * 100, 1) if closed else 0.0,
        "gross_win": round(gross_win, 2),
        "gross_loss": round(gross_loss, 2),
        # The number that decides whether the model is worth real money.
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss > 0 else None,
        "avg_r": round(sum(rs) / len(rs), 2) if rs else None,
        "expectancy_r": round(sum(rs) / len(rs), 3) if rs else None,
        "net": round(equity - start, 2),
        "return_pct": round((equity - start) / start * 100, 2) if start else 0.0,
        "max_drawdown_pct": round(max_dd * 100, 2),
        "ending_equity": round(equity, 2),
    }


def simulate(frames: dict[str, pd.DataFrame], cfg: PaperConfig | None = None) -> Result:
    """Replay 5-minute bars across a universe under cash-account rules.

    Bars are walked in strict timestamp order across every symbol at once, so the
    shared cash balance is spent in the order events actually happened. Running
    symbols one at a time would let each of them spend the same $1,000.
    """
    cfg = cfg or PaperConfig()
    prepped = {s: prepare(df) for s, df in frames.items() if df is not None and not df.empty}
    if not prepped:
        return Result(asdict(cfg), [], [], _metrics([], [], cfg.starting_cash),
                      {}, 0, [])

    ledger = Ledger(settled=cfg.starting_cash)
    trades: list[Trade] = []
    open_trades: dict[str, Trade] = {}
    curve: list[dict] = []
    blocked = {"unsettled_cash": 0, "daily_stop": 0, "max_open": 0,
               "max_trades": 0, "too_late": 0, "no_size": 0,
               "no_follow_through": 0, "no_buying_power": 0}
    # Signals fire on a bar CLOSE and fill on the NEXT bar's open, so a triggered
    # setup waits here for one bar. This is the difference between a backtest and
    # a fantasy.
    pending: dict[str, dict] = {}

    # One ordered timeline, so cash is spent in real sequence.
    stamps = sorted({ts for df in prepped.values() for ts in df.index})
    days = sorted({ts.date() for ts in stamps})
    or_cache: dict[tuple[str, date], tuple[float, float] | None] = {}

    day_start_equity = cfg.starting_cash
    current_day: date | None = None
    day_trades = 0
    day_halted = False

    def mark_to_market(ts) -> float:
        held = 0.0
        for sym, t in open_trades.items():
            df = prepped[sym]
            idx = df.index[df.index <= ts]
            if len(idx):
                held += t.open_shares * float(df.loc[idx[-1], "Close"])
        return ledger.total + held

    def close_out(t: Trade, shares: float, price: float, reason: str, ts) -> None:
        proceeds = shares * (price - cfg.slippage)
        ledger.sell(proceeds, ts.date())
        cost = shares * t.entry
        t.realized += proceeds - cost
        t.open_shares -= shares
        t.exits.append({"time": str(ts), "shares": round(shares, 6),
                        "price": round(price, 4), "reason": reason})
        if not t.is_open:
            t.exit_reason = reason
            risk = t.risk_dollars
            t.r_multiple = round(t.realized / risk, 3) if risk > 0 else None
            open_trades.pop(t.symbol, None)

    prev_ts = None
    for ts in stamps:
        day = ts.date()
        if day != current_day:
            # Nothing crosses a session boundary. The intraday flat-by rule
            # normally handles this, but a truncated or short session must not be
            # allowed to leak a position into the next day — that would be an
            # overnight hold this model does not take, and it would tie up cash
            # the settlement ledger has already promised elsewhere.
            if prev_ts is not None:
                for t in list(open_trades.values()):
                    df = prepped[t.symbol]
                    idx = df.index[df.index <= prev_ts]
                    if len(idx):
                        close_out(t, t.open_shares, float(df.loc[idx[-1], "Close"]),
                                  "session end", prev_ts)
            current_day = day
            ledger.settle_through(day)
            day_start_equity = mark_to_market(ts)
            day_trades = 0
            day_halted = False
            pending.clear()      # yesterday's trigger is not today's trade

        minutes = ts.hour * 60 + ts.minute - (9 * 60 + 30)

        for sym, df in prepped.items():
            if ts not in df.index:
                continue
            row = df.loc[ts]
            if isinstance(row, pd.DataFrame):      # duplicate stamp guard
                row = row.iloc[0]
            price_high, price_low = float(row["High"]), float(row["Low"])

            # ---- fill anything that triggered on the previous bar's close
            want = pending.pop(sym, None)
            if want is not None and want["day"] == day and sym not in open_trades:
                fill = float(row["Open"])
                if fill <= want["or_high"]:
                    # Gapped back inside the range overnight-of-a-bar: the break
                    # failed before it could be bought. You would not chase it.
                    blocked["no_follow_through"] += 1
                elif ledger.settled < 1.0:
                    # Distinct from a sizing rejection: the setup was valid and
                    # the account simply had no spendable cash — either it is
                    # already deployed, or yesterday's proceeds have not settled.
                    # This is THE cash-account constraint and it gets its own line.
                    blocked["no_buying_power"] += 1
                else:
                    equity = mark_to_market(ts)
                    plan = plan_trade(row, fill, want["or_low"], equity,
                                      ledger.settled, cfg)
                    if plan is None:
                        blocked["no_size"] += 1
                    else:
                        entry, stop, target, shares = plan
                        if not ledger.buy(shares * entry):
                            # The constraint biting: the model wanted this trade
                            # and the cash was still settling. Counted, never
                            # silently dropped.
                            blocked["unsettled_cash"] += 1
                        else:
                            trade = Trade(
                                symbol=sym, day=str(day), entry_time=str(ts),
                                entry=round(entry, 4), stop=round(stop, 4),
                                target=round(target, 4), shares=round(shares, 6),
                                risk_dollars=round(shares * (entry - stop), 2),
                                setup=want["reason"], open_shares=shares,
                                current_stop=round(stop, 4),
                            )
                            trades.append(trade)
                            open_trades[sym] = trade
                            day_trades += 1
                            # On the fill bar only the ADVERSE case is checked.
                            # Allowing a same-bar scale or target would hand back
                            # the look-ahead this whole change removes.
                            if price_low <= trade.current_stop:
                                close_out(trade, trade.open_shares,
                                          trade.current_stop, "stop", ts)
                            continue

            # ---- manage what is already on, before considering anything new
            t = open_trades.get(sym)
            if t is not None:
                one_r = t.entry + (t.entry - t.stop)   # always off the ORIGINAL risk
                if price_low <= t.current_stop:
                    # Assume the stop fills at the stop, not the bar low. A 5m
                    # bar hides the path; this is the honest middle.
                    close_out(t, t.open_shares, t.current_stop, "stop", ts)
                elif not t.scaled and price_high >= one_r:
                    part = t.open_shares * cfg.scale_out_frac
                    close_out(t, part, one_r, "scale 1R", ts)
                    if t.is_open:
                        t.scaled = True
                        t.current_stop = t.entry      # breakeven on the rest
                elif price_high >= t.target:
                    close_out(t, t.open_shares, t.target, "target", ts)
                elif minutes >= cfg.flat_by_min:
                    close_out(t, t.open_shares, float(row["Close"]), "time", ts)
                continue        # one action per symbol per bar

            # ---- entries
            if day_halted or minutes < 0:
                continue
            key = (sym, day)
            if key not in or_cache:
                session = df[df.index.date == day]
                or_cache[key] = opening_range(session, cfg.opening_range_bars)
            rng = or_cache[key]
            if rng is None:
                continue
            or_high, or_low = rng
            # Only bars after the opening range can break it.
            session = df[df.index.date == day]
            if len(session) <= cfg.opening_range_bars or ts <= session.index[cfg.opening_range_bars - 1]:
                continue

            reason = entry_signal(row, or_high, cfg)
            if not reason:
                continue
            if minutes > cfg.entry_cutoff_min:
                blocked["too_late"] += 1
                continue
            if len(open_trades) >= cfg.max_open:
                blocked["max_open"] += 1
                continue
            if day_trades >= cfg.max_trades_per_day:
                blocked["max_trades"] += 1
                continue

            # Queue it. The fill happens on the next bar's open, above.
            pending[sym] = {"or_high": or_high, "or_low": or_low,
                            "reason": reason, "day": day}

        # ---- daily loss limit, checked on the shared equity curve
        equity = mark_to_market(ts)
        if not day_halted and day_start_equity > 0:
            if (day_start_equity - equity) / day_start_equity >= cfg.daily_stop_pct:
                day_halted = True
                for t in list(open_trades.values()):
                    df = prepped[t.symbol]
                    idx = df.index[df.index <= ts]
                    if len(idx):
                        close_out(t, t.open_shares, float(df.loc[idx[-1], "Close"]),
                                  "daily stop", ts)
                blocked["daily_stop"] += 1
        curve.append({"time": str(ts), "equity": round(mark_to_market(ts), 2)})
        prev_ts = ts

    # Flat at the end of the replay for the same reason.
    if prev_ts is not None:
        for t in list(open_trades.values()):
            df = prepped[t.symbol]
            idx = df.index[df.index <= prev_ts]
            if len(idx):
                close_out(t, t.open_shares, float(df.loc[idx[-1], "Close"]),
                          "session end", prev_ts)

    return Result(
        config=asdict(cfg),
        trades=[asdict(t) for t in trades],
        equity_curve=curve,
        metrics=_metrics(trades, curve, cfg.starting_cash),
        blocked=blocked,
        days=len(days),
        symbols=sorted(prepped),
    )


def backtest(symbols: tuple[str, ...] = UNIVERSE,
             cfg: PaperConfig | None = None) -> Result:
    """Replay the deepest intraday window yfinance will give (60 days of 5m bars).

    Anything returning mock bars is dropped rather than replayed: a backtest run
    on generated prices proves nothing, and this codebase has already been bitten
    once by mock data being graded as if it were real.
    """
    from . import market_data

    frames: dict[str, pd.DataFrame] = {}
    for sym in symbols:
        try:
            df, source = market_data.get_intraday(sym, "60d")
        except Exception as exc:
            print(f"[paper] {sym}: intraday fetch failed ({exc!r})")
            continue
        if source != "live":
            print(f"[paper] {sym}: {source} data — excluded from the backtest")
            continue
        if df is None or df.empty:
            continue
        frames[sym] = df
    return simulate(frames, cfg)
