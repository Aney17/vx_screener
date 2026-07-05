# Vanguard Sector & Stock Screener

A two-part screener built for identifying momentum breakouts intended to be held for
60+ trading days:

1. **Sector Rotation** (`index.html`) — the 11 Vanguard sector ETFs ranked by relative
   strength vs SPY across daily/weekly/monthly/3M/6M/yearly windows, plus breadth (what
   share of each sector's own stocks are actually outperforming, not just a couple of
   mega-caps carrying it).
2. **Total Market Screener** (`stocks.html`) — every stock held across those 11 ETFs,
   grouped by sector, with trend/momentum/volume signals and guardrails against chasing
   overextended or illiquid names.

Runs on [yfinance](https://github.com/ranaroussi/yfinance). Hosted for free on GitHub
Pages; data refreshes via a scheduled GitHub Actions job (with a manual "Run workflow"
button too).

## 1. Run it locally first

```bash
pip install -r scripts/requirements.txt
```

**Step 1 — get holdings files.** For each of the 11 tickers below, go to its fund page
(e.g. `https://institutional.vanguard.com/investments/products/<ticker>`), open
**Portfolio & Management → Portfolio holdings**, and download the export. Vanguard
gives you an `.xlsx` file — save each one as `data/holdings/<TICKER>.xlsx` (a plain
`.csv` with a clean header row also works if you have one from elsewhere; `.xlsx`
takes precedence if both exist):

```
VOX  VCR  VDC  VDE  VFH  VHT  VIS  VGT  VAW  VNQ  VPU
```

You only need to do this every few months — holdings don't change daily. The stock
screener will run fine with a subset of these files if you want to test with just one
or two sectors first; it'll warn about the rest and skip them. Expect somewhere
around 2,000–2,500 unique stocks once all 11 are loaded (there's real overlap between
funds, e.g. mega-caps sometimes straddle sector boundaries) — the first
`fetch_stock_screener.py` run against that many tickers can take a while since
yfinance downloads in batches of 100.

**Step 2 — run the pipeline** (works whether you run it from the repo root or from
inside `scripts/` — paths are resolved relative to the project root either way):

```bash
cd scripts
python fetch_sector_rs.py        # writes ../data/sectors.json
python fetch_stock_screener.py   # writes ../data/stocks.json, patches sector breadth
                                  # back into sectors.json, and logs any fresh RS
                                  # breakouts to ../data/history/snapshots.jsonl
```

**Step 3 — preview the site:**

```bash
cd ..
python -m http.server 8080
```

Open `http://localhost:8080`. (Placeholder sample data is already committed in
`data/*.json` so the site renders something immediately — running the scripts above
overwrites it with real data.)

> Note: `scripts/test_with_synthetic_data.py` is a standalone sanity check for the
> indicator math (RSI, MACD, ATR, momentum factor, RS breakout detection, etc.) using
> fabricated price series — it doesn't call yfinance. Useful if you want to verify the
> calculations without waiting on a network call. Safe to delete once you trust the
> real pipeline.

## 2. Deploy to GitHub

```bash
git init
git add .
git commit -m "Initial commit: sector + stock screener"
git branch -M main
git remote add origin https://github.com/<your-username>/<repo-name>.git
git push -u origin main
```

Then in the repo settings: **Settings → Pages → Source → Deploy from a branch →
`main` / root.** Your site will be live at
`https://<your-username>.github.io/<repo-name>/`.

## 3. Keep data updating

The workflow at `.github/workflows/update-data.yml` runs automatically on trading days
and commits fresh `data/sectors.json` / `data/stocks.json` back to the repo, which
GitHub Pages then serves. No secrets or API keys are needed — yfinance doesn't require
one, and the workflow's default `GITHUB_TOKEN` has enough permission to commit.

To trigger a refresh manually: repo → **Actions** tab → **Update sector & stock
screener data** → **Run workflow**. (This is the "button" — GitHub Pages can't run
Python on click for anonymous visitors, so the trigger lives in the Actions tab. The
site's "Run update" link in the top bar points there.)

To change the schedule, edit the `cron` line in that workflow file (it runs in UTC).

## 4. Building an actual track record (backtesting)

Every time `fetch_stock_screener.py` runs and finds a stock whose RS breakout started
*that day*, it appends a row to `data/history/snapshots.jsonl` — ticker, sector, entry
price, and the state of every other signal at that moment. This is an append-only log
that accumulates for as long as the scheduled workflow keeps running.

Once a signal is old enough that a full holding period has actually elapsed, run:

```bash
python scripts/backtest_report.py    # writes data/backtest_summary.json
```

This looks up what each aged signal actually returned over the next `BACKTEST_HOLDING_DAYS`
(60, matching the target holding period) trading days, versus what SPY did over the same
window, and reports a win rate and average excess return — broken out by sector and by
whether the sector was leading at entry. It'll report nothing useful for the first couple
of months (there's nothing old enough to score yet) — that's expected. This is what turns
the screener from "here's what's happening" into "here's what has actually worked", and
is the single most important thing to keep running if you want confidence in these signals
rather than just a plausible-looking dashboard.

## 5. Looking back at any prior day (the history calendar)

Every time the workflow runs, `backup_snapshots.py` archives that day's full `sectors.json`
and `stocks.json` into `data/history/daily/YYYY-MM-DD/`, and updates
`data/history/daily/manifest.json` — a small index of which dates have a backup, since a
static site can't list a directory itself.

Both pages have a **Historical snapshots** control near the top. Opening it shows a month
calendar: dates with an archived backup get a blue ring, the date you're currently viewing
(if any) is filled solid blue, and today gets a subtle gray ring. Clicking any ringed date
reloads the page showing that day's data instead of live data — the sector rotation and
stock screener pages both understand `?snapshot=YYYY-MM-DD` in the URL, and switching
between the two tabs while browsing history carries the same date across automatically. A
**Return to live data** button clears it.

Backups are kept for a rolling `HISTORY_RETENTION_DAYS` window (90 days by default, set in
`config.py`) — `backup_snapshots.py` prunes anything older on every run, so the repo doesn't
grow without bound. Every commit still exists in git history regardless; this setting only
controls what the live calendar can serve. Raise it if you want a longer visible window.

## How the numbers are calculated

- **Relative strength (RS)** = `price / SPY price`, tracked as its own line over time.
  A rising RS line means the sector/stock is *outpacing* the S&P 500, independent of
  whether its raw price is up or down. Tracked across daily/weekly/monthly/3M/6M/yearly
  windows — the 3M/6M windows were added specifically because they're the range academic
  momentum research finds most predictive of subsequent multi-month returns, which matters
  more for a 60+ day hold than the noisier daily/weekly windows.
- **RS breakout date & age** = the most recent date a stock's RS line crossed above its
  own 50-day moving average and hasn't fallen back below it since, plus how many trading
  days it's held that streak. A 2-day-old breakout and a 4-month-old one are very
  different entries even though both show as "currently outperforming".
- **RS slope** = % change in the RS line itself over the last 10 days — whether
  outperformance is accelerating or already fading.
- **Sector breadth** = % of a sector's own stocks currently RS-outperforming SPY — tells
  you whether a sector's strength is broad-based or just a couple of mega-caps.
- **Trend** = price vs its 50-day and 200-day simple moving averages.
- **Momentum** = RSI-14, MACD histogram, 1-month ROC, and a 12-month-minus-1-month
  momentum factor (the standard academic construction — excluding the most recent month
  specifically avoids short-term reversal noise contaminating a longer momentum read).
- **Volume** = today's volume vs its trailing 20-day average, plus a 20-day up/down
  volume ratio (volume on up days ÷ down days) — a sturdier accumulation signal than a
  single day's spike, which is just as likely to be a news pop that fades.
- **Guardrails (flagged, not filtered)**: `extension_atrs` = how many ATRs price sits
  above its 50-day SMA (very stretched readings mean higher pullback risk right as
  you'd be entering); `avg_dollar_volume` flags thin/illiquid names. Both are shown so
  you can apply judgment rather than being silently excluded from the list.

## Project structure

```
scripts/
  config.py                 - tickers, windows, thresholds, guardrail, retention settings
  holdings.py                - loads data/holdings/*.xlsx or .csv into a sector map
  indicators.py               - RSI, MACD, SMA, ATR, RS line, momentum factor, breakout detection
  fetch_sector_rs.py          - Part 1 pipeline
  fetch_stock_screener.py     - Part 2 pipeline; also patches sector breadth and logs breakouts
  backup_snapshots.py         - archives the day's data for the history calendar; prunes old ones
  backtest_report.py          - scores aged signals against actual forward returns
  test_with_synthetic_data.py - offline math sanity check
data/
  holdings/<TICKER>.xlsx      - you provide these (see step 1 above)
  history/snapshots.jsonl     - append-only log of fresh breakouts, for backtesting
  history/daily/YYYY-MM-DD/   - full daily backups, for the calendar picker
  history/daily/manifest.json - index of which dates have a backup
  sectors.json                - generated (live)
  stocks.json                 - generated (live)
  backtest_summary.json       - generated by backtest_report.py once signals have aged
index.html / stocks.html      - the two pages
css/style.css                 - front end styling
js/app.js                     - shared helpers (formatting, sorting, snapshot routing)
js/history.js                 - the historical snapshot calendar widget
js/sectors.js / js/stocks.js   - per-page rendering logic
.github/workflows/update-data.yml
```
