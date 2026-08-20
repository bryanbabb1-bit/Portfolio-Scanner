# Why the app never catches the 50% movers

Run order. All four read the whole US universe (5,865 symbols) through
`app.services.universe`; `bigmovers_variants.py` caches the bars to
`bigmovers_cache.pkl` so re-runs are instant.

    cd backend && .venv/Scripts/python.exe studies/bigmovers_study.py

| script | question | answer (43 sessions to 2026-08-19) |
|---|---|---|
| `bigmovers_study.py` | how many +50% days are there, and where does the move happen? | 195 events, **4.5 a session**. 59% are already +50% at the open. 12.8% are both tradeable and still have 20%+ left after the open — **0.58 a session** |
| `bigmovers_signal.py` | if we alerted on every intraday runner, how noisy is it? | **7.4 alerts a session**, 9.1% of them finish +50%. Livable alert volume |
| `bigmovers_expectancy.py` | would trading those alerts have made money? | **No.** -0.84% a trade, win rate 41%, profit factor 0.83 |
| `bigmovers_variants.py` | is any version of the chase positive? | **No.** Eight testable variants, all negative. Holding longer is significantly worse (t = -2.78 at 3 days) |

| `premove_footprint.py` | is there a footprint BEFORE the move? | **Yes.** Volume in the week before a +50% day runs 33x its own average at the 90th percentile, against 1.7x on an ordinary day, and the median name is **down 25% on the month** first. Screening on it concentrates big movers from 1.3% to 13.7% — but the median 5-day outcome is **-8.1%** |

## What this rules out, and what it does not

Ruled out: chasing a name that is already running. Not one variant cleared zero,
before spread or slippage, and these are wide-spread names. The desk's standing
"don't chase" ruling has been correct, which is also why the pipeline produces
nothing to act on — it is not broken, it is right.

The SEC filings feed was built and then removed: an 8-K is filed alongside the
press release, so it is complete, official, and incapable of getting you in
early. `premove_footprint.py` replaced it with the thing that does lead — but
read both of its columns before trusting it.

NOT ruled out, because it was never tested here: being positioned BEFORE the
move on a dated, knowable catalyst. MRNA on 2026-08-19 was not a momentum chase
— it was a Phase 3 readout at a $67B company whose trial partner (MRK) was
already in the book. That is a calendar problem, not a scanner problem, and the
calendar has never been built.

## Known limits

- Daily bars cannot sequence intraday, so a same-session stop is untestable
  here. Checking the entry bar stopped every trade out instantly — an artifact,
  not a result, and the reason those rows were removed rather than reported.
- 43 sessions is one regime. A negative result this consistent across variants
  is more robust than a positive one would be, but it is still one summer.
- Entry is the trigger price itself, which assumes a fill at the level. Real
  fills on names moving this fast are worse, so the real numbers are below these.
