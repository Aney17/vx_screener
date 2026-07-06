"""
Shared configuration for the sector + stock screener.
"""

import os

# Anchor all data paths to the project root (the parent of this scripts/
# folder) rather than the current working directory. Without this, running
# `cd scripts && python fetch_sector_rs.py` (as the README's local-dev
# instructions suggest) would silently look for/write data in scripts/data/
# instead of the real data/ folder at the project root.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _path(*parts):
    return os.path.join(_PROJECT_ROOT, *parts)


BENCHMARK = "SPY"  # S&P 500 proxy used for all relative-strength calculations

# The 11 Vanguard sector ETFs and the GICS sector each tracks.
SECTOR_ETFS = {
    "VOX": "Communication Services",
    "VCR": "Consumer Discretionary",
    "VDC": "Consumer Staples",
    "VDE": "Energy",
    "VFH": "Financials",
    "VHT": "Health Care",
    "VIS": "Industrials",
    "VGT": "Information Technology",
    "VAW": "Materials",
    "VNQ": "Real Estate",
    "VPU": "Utilities",
}

# Relative-strength lookback windows, expressed in trading days.
# 3-month / 6-month sit between the old "monthly" and "yearly" windows because
# that's the range academic momentum research (Jegadeesh & Titman and the
# large body of work since) finds most predictive of subsequent multi-month
# returns -- which is what a 60+ day holding period actually needs, versus
# the noisier daily/weekly windows that suit much shorter trades.
RS_WINDOWS = {
    "daily": 1,
    "weekly": 5,
    "monthly": 21,
    "quarterly": 63,
    "semiannual": 126,
    "yearly": 252,
}

# "12 month return, skipping the most recent month" -- the classic academic
# momentum factor construction. Skipping the last month specifically excludes
# short-term reversal effects that would otherwise contaminate a pure
# multi-month momentum read.
MOMENTUM_LOOKBACK = 252
MOMENTUM_SKIP = 21

# How much price history to pull. Needs to comfortably cover the longest
# RS window plus the moving averages used in the stock screener (SMA200).
HISTORY_PERIOD = "2y"

# Moving averages / oscillators used in the per-stock screener.
SMA_TREND_FAST = 50
SMA_TREND_SLOW = 200
RSI_PERIOD = 14
ROC_PERIOD = 21          # ~1 month rate of change
VOLUME_AVG_PERIOD = 20
RS_MA_PERIOD = 50        # moving average applied to the RS line for crossover detection
RS_SLOPE_WINDOW = 10     # trading days used to measure whether RS outperformance is accelerating
ATR_PERIOD = 14          # used for the "how extended is price" guardrail
UP_DOWN_VOLUME_WINDOW = 20  # accumulation/distribution proxy window

# A sector is treated as "leading" (for the stock screener's sector context
# filter) if its yearly RS rank is in the top third of the 11 sectors.
LEADING_SECTOR_RANK_CUTOFF = 4

# Liquidity guardrail: flag (not exclude) stocks whose recent average dollar
# volume is below this, since thin names are harder to enter/exit cleanly
# and more prone to gaps.
LOW_LIQUIDITY_DOLLAR_VOL = 5_000_000

# Extension guardrail: flag stocks trading more than this many ATRs above
# their 50-day SMA, since that's historically when momentum names are most
# prone to a sharp mean-reversion pullback right as you'd be entering.
EXTENSION_ATR_THRESHOLD = 3.0

# Focus-tier thresholds -- classify each stock into "high_focus" / "watch" /
# "skip" using signals already computed above. These are starting judgment
# calls, not derived from data yet; once backtest_report.py has enough
# history, check whether "high_focus" entries actually outperformed "watch"
# ones over the following BACKTEST_HOLDING_DAYS and retune these if not.
FOCUS_RSI_HEALTHY_MIN = 40      # below this, momentum may already be fading
FOCUS_RSI_HEALTHY_MAX = 75      # above this, treat as overbought caution
FOCUS_BREAKOUT_FRESH_DAYS = 15  # breakout younger than this counts as "fresh"
FOCUS_BREAKOUT_AGING_DAYS = 45  # breakout older than this is a caution flag

HOLDINGS_DIR = _path("data", "holdings")
OUTPUT_SECTORS = _path("data", "sectors.json")
OUTPUT_STOCKS = _path("data", "stocks.json")
OUTPUT_META = _path("data", "meta.json")

# Append-only log of each day's fresh RS breakouts, used later to compute
# actual forward returns once enough history has accumulated. This is the
# raw material for a real backtest instead of a snapshot-only screener.
SNAPSHOT_LOG = _path("data", "history", "snapshots.jsonl")
BACKTEST_HOLDING_DAYS = 60         # matches the target holding period
OUTPUT_BACKTEST = _path("data", "backtest_summary.json")

# Daily full-data backups (sectors.json + stocks.json), one dated folder per
# day, so the front end can time-travel back to any prior day's snapshot via
# the calendar picker. Kept for a rolling window rather than forever, so the
# repo doesn't grow without bound.
HISTORY_DAILY_DIR = _path("data", "history", "daily")
HISTORY_MANIFEST = _path("data", "history", "daily", "manifest.json")
HISTORY_RETENTION_DAYS = 90
