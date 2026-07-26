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
   recalibrates drift/volatility, logs a new next-day prediction, and rebuilds
   `index.html`.
3. The workflow commits the updated `index.html` and `nifty50_state.json`.
4. GitHub Pages republishes `index.html` automatically.

This is recalibration, not self-improving ML. Nifty is close to a random walk day
to day, so directional accuracy is expected to hover near 50%. The scoreboard
shows that honestly.

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
