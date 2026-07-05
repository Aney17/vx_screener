"""
Sanity-check harness for the indicator math using fabricated price series.
This does NOT hit yfinance — it's here so the calculation logic can be
verified in environments without internet access to Yahoo Finance.
Not part of the production pipeline; safe to delete once you've done a real
run locally with `python scripts/fetch_sector_rs.py`.
"""

import numpy as np
import pandas as pd

from indicators import (
    sma, rsi, macd, relative_volume, relative_strength_line,
    rs_breakout_date, rs_breakout_age, trend_state, pct_change_over,
    momentum_factor, rs_slope, atr, extension_in_atrs, dollar_volume,
    up_down_volume_ratio,
)

np.random.seed(7)
n = 400
dates = pd.date_range("2024-01-01", periods=n, freq="B")

# Benchmark: steady modest uptrend with noise.
bench = pd.Series(100 * (1 + 0.0003) ** np.arange(n) + np.random.normal(0, 0.4, n), index=dates)

# "Winner" stock: tracks benchmark early, then breaks out and outpaces it
# for the last ~80 trading days.
winner = bench.copy()
breakout_idx = n - 80
boost = np.concatenate([np.zeros(breakout_idx), np.linspace(0, 25, n - breakout_idx)])
winner = winner + boost + np.random.normal(0, 0.5, n)

volume = pd.Series(np.random.randint(1_000_000, 2_000_000, n), index=dates)
volume.iloc[-1] = 4_500_000  # simulate a volume spike today

print("=== indicator sanity checks ===")
print("1m return (21d) winner: ", pct_change_over(winner, 21), "%")
print("1y return (252d) winner:", pct_change_over(winner, 252), "%")

fast = sma(winner, 50)
slow = sma(winner, 200)
print("trend state:", trend_state(winner, fast, slow))

r = rsi(winner, 14)
print("RSI-14 (latest):", round(r.iloc[-1], 1))

_, _, hist = macd(winner)
print("MACD histogram (latest):", round(hist.iloc[-1], 3))

rv = relative_volume(volume, 20)
print("relative volume (latest, should be >1 given spike):", rv)

rs_line = relative_strength_line(winner, bench)
breakout_date = rs_breakout_date(rs_line, 50)
expected_calendar_date = dates[breakout_idx]
print(f"RS breakout date detected: {breakout_date} "
      f"(synthetic boost started ~{expected_calendar_date.date()}, "
      f"detection lags by the 50d MA smoothing period as expected)")

# A stock that never outperforms should return None.
loser = bench - np.linspace(0, 15, n) + np.random.normal(0, 0.5, n)
loser_rs = relative_strength_line(loser, bench)
print("Loser breakout date (should be None):", rs_breakout_date(loser_rs, 50))

print("\n=== new indicator checks (momentum / guardrails / sector context) ===")

age = rs_breakout_age(rs_line, 50)
print(f"RS breakout age (trading days since the current outperformance streak began): {age}")

mom = momentum_factor(winner, lookback=252, skip=21)
print("12m-skip-1m momentum factor, winner:", mom, "% (should be positive and sizeable)")

slope = rs_slope(rs_line, 10)
print("RS 10-day slope, winner (should be positive -- still gaining ground):", slope, "%")

loser_slope = rs_slope(loser_rs, 10)
print("RS 10-day slope, loser (should be negative or flat):", loser_slope, "%")

# Fabricate High/Low for ATR from the winner close series.
high = winner + np.random.uniform(0.2, 1.0, n)
low = winner - np.random.uniform(0.2, 1.0, n)
atr_series = atr(pd.Series(high, index=dates), pd.Series(low, index=dates), winner, 14)
print("ATR-14 (latest):", round(atr_series.iloc[-1], 2))

ext = extension_in_atrs(winner, fast, atr_series)
print("Extension in ATRs above SMA50 (winner, post-breakout, should be notably positive):", ext)

dv = dollar_volume(winner, volume, 20)
print(f"Avg dollar volume (20d): ${dv:,.0f}" if dv else "Avg dollar volume: None")

updown = up_down_volume_ratio(winner, volume, 20)
print("Up/down volume ratio, winner (should be >1 if up-day volume dominates):", updown)

print("\nAll checks ran without errors.")
