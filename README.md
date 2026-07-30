# Nifty 50 F&O Analyzer

Educational dashboard for the Nifty 50 index: historical charts, technical
indicators, a theoretical (Black-Scholes) option chain, a 30-day projection cone,
a plain-English sentiment gauge, a labelled 3D option-premium landscape, and a
daily prediction-accuracy scoreboard.

**Not investment advice.** All projections and option prices are model outputs,
not live market quotes. No model reliably forecasts index prices. F&O trading can
lose your entire capital.

## How it runs in the cloud (no laptop needed)

A GitHub Actions workflow (`.github/workflows/daily.yml`) runs every weekday at
13:30 UTC (19:00 IST). Each run:

1. `fetch_close.py` pulls the latest Nifty close from Yahoo (with retries).
2. `nifty_build.py --add <date> <close>` scores yesterday's prediction,
   recalibrates the drift, logs a new next-day prediction, and rebuilds
   `index.html`.
3. The workflow commits the updated `index.html` and `nifty50_state.json`.
4. GitHub Pages republishes `index.html` automatically.

## The prediction model, and what "accurate" means here

`predict_log_return()` in `nifty_build.py` is the whole model:

    drift = mean log return over the entire history (~19 years)
    predict down if the last two sessions were both down, else predict up

Both halves were chosen by `backtest.py`, which walk-forward tests every
candidate over 3,373 sessions since 2012 using only data available on the day of
each prediction:

| model                             | directional accuracy |
|-----------------------------------|----------------------|
| old 120-day drift                 | 51.9%                |
| always guess "up"                 | 53.6%                |
| follow yesterday's direction      | 54.3%                |
| **shipped: drift + 2-down-streak**| **54.6%**            |

Read that table honestly. **50% is not the bar** &mdash; Nifty closes up on 53.6%
of days, so a model that always says "up" scores 53.6% while knowing nothing. The
real edge over that baseline is ~1 percentage point, or one extra correct call per
100 sessions. It is consistent (better than the old model in 10 of 15 calendar
years, and it improves mean absolute error slightly), but it is nowhere near
tradeable on its own, and a few dozen live predictions will not be enough to
detect it. The old model's problem was that a 120-day drift window is mostly
noise: it made confident "down" calls on 28% of sessions and got most of them
wrong.

The **30-day projection cone** had the same bug and gained far more from the fix,
because drift dominates noise as the horizon lengthens:

| 30-day cone drift | direction | mean abs error | 80% band actually covers |
|-------------------|-----------|----------------|--------------------------|
| old 120-day       | 53.0%     | 608            | 74.0%                    |
| **full history**  | **65.1%** | **532**        | **80.0%**                |

The cone still takes its *width* from the recent 120-day volatility &mdash; that
part was right; only the centre line was being steered by noise.

Rerun `python backtest.py` before changing the model. It asserts that the shipped
model still beats the old drift, the always-up baseline, and wins a majority of
years, and that the cone's 80% band stays calibrated.

## One-time setup

1. Create a new **public** repo on GitHub (e.g. `nifty-fno-analyzer`).
2. Upload every file in this folder, keeping the `.github/workflows/` path intact.
3. **Settings → Actions → General → Workflow permissions →** select
   **Read and write permissions**, save. (Lets the job commit results.)
4. **Settings → Pages → Build and deployment → Source: Deploy from a branch →**
   branch `main`, folder `/ (root)`, save.
5. **Actions** tab → open "Daily Nifty Update" → **Run workflow** to test now.
6. Your app will be live at `https://<your-username>.github.io/<repo-name>/`.

Files: `index.html` (the app / Pages entry point), `nifty_build.py` (source of
truth, regenerates the HTML), `fetch_close.py` (cloud data fetch),
`nifty50_state.json` (price history + prediction log).

Data source: Yahoo Finance (^NSEI), daily closes. Not affiliated with NSE.
