"""
Technical indicator and relative-strength helpers shared by the sector
screener (part 1) and the stock screener (part 2).

All functions take/return pandas Series indexed by date, aligned to the
close-price series passed in.
"""

import numpy as np
import pandas as pd


def pct_change_over(series: pd.Series, periods: int) -> float:
    """% change from `periods` trading days ago to the latest value."""
    if len(series) <= periods:
        return None
    latest = series.iloc[-1]
    past = series.iloc[-1 - periods]
    if past == 0 or pd.isna(past) or pd.isna(latest):
        return None
    return round(((latest / past) - 1) * 100, 2)


def relative_strength_line(price: pd.Series, benchmark: pd.Series) -> pd.Series:
    """RS line = price / benchmark, aligned on shared dates."""
    aligned = pd.concat([price, benchmark], axis=1, join="inner")
    aligned.columns = ["price", "benchmark"]
    return aligned["price"] / aligned["benchmark"]


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out.fillna(100)  # if avg_loss is 0, RSI -> 100


def macd(series: pd.Series, fast=12, slow=26, signal=9):
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def relative_volume(volume: pd.Series, avg_period: int = 20) -> float:
    """Latest volume vs its trailing average, as a multiple (1.0 = average)."""
    if len(volume) < avg_period + 1:
        return None
    avg = volume.iloc[-avg_period - 1:-1].mean()  # average excluding today
    if avg == 0 or pd.isna(avg):
        return None
    return round(volume.iloc[-1] / avg, 2)


def rs_breakout_date(rs_line: pd.Series, ma_period: int = 50, lookback_days: int = 252):
    """
    Finds the most recent date the RS line crossed *above* its own moving
    average and has remained above it ever since (i.e. the start of the
    current period of the stock/sector outperforming the benchmark).

    Returns an ISO date string, or None if the RS line is not currently
    above its moving average (no active outperformance streak) or there
    isn't enough history.
    """
    ma = sma(rs_line, ma_period)
    combined = pd.concat([rs_line, ma], axis=1).dropna()
    combined.columns = ["rs", "ma"]
    if combined.empty:
        return None

    above = combined["rs"] > combined["ma"]
    if not above.iloc[-1]:
        return None  # not currently outperforming -> no active breakout date

    # walk backwards from the end while still above; the breakout date is the
    # first date of the current unbroken "above" streak.
    window = above.iloc[-lookback_days:] if len(above) > lookback_days else above
    streak_start = window.index[-1]
    for date, is_above in window.iloc[::-1].items():
        if not is_above:
            break
        streak_start = date
    return str(streak_start.date())


def rs_breakout_age(rs_line: pd.Series, ma_period: int = 50, lookback_days: int = 252):
    """
    Trading days since the current RS-outperformance streak began (i.e. how
    "fresh" the breakout is). Returns None if not currently outperforming.
    A breakout that started 2 days ago is a meaningfully different entry
    than one that's been running for 4 months -- the latter has likely
    already made most of its move for a fresh 60-day hold.
    """
    ma = sma(rs_line, ma_period)
    combined = pd.concat([rs_line, ma], axis=1).dropna()
    combined.columns = ["rs", "ma"]
    if combined.empty:
        return None

    above = combined["rs"] > combined["ma"]
    if not above.iloc[-1]:
        return None

    window = above.iloc[-lookback_days:] if len(above) > lookback_days else above
    age = 0
    for is_above in window.iloc[::-1]:
        if not is_above:
            break
        age += 1
    return age


def trend_state(close: pd.Series, sma_fast: pd.Series, sma_slow: pd.Series) -> str:
    """Simple human-readable trend classification from price vs its SMAs."""
    if pd.isna(sma_fast.iloc[-1]) or pd.isna(sma_slow.iloc[-1]):
        return "insufficient data"
    price = close.iloc[-1]
    fast = sma_fast.iloc[-1]
    slow = sma_slow.iloc[-1]
    if price > fast > slow:
        return "strong uptrend"
    if price > fast and fast <= slow:
        return "emerging uptrend"
    if price < fast < slow:
        return "strong downtrend"
    if price < fast and fast >= slow:
        return "emerging downtrend"
    return "mixed / consolidating"


def momentum_factor(close: pd.Series, lookback: int = 252, skip: int = 21) -> float:
    """
    Academic-style momentum: total return over `lookback` trading days,
    excluding the most recent `skip` days. Skipping the last ~month is
    standard in momentum-factor construction because very short-term returns
    tend to mean-revert and would otherwise dilute the signal.
    """
    needed = lookback + 1
    if len(close) <= needed:
        return None
    start = close.iloc[-1 - lookback]
    end = close.iloc[-1 - skip]
    if start == 0 or pd.isna(start) or pd.isna(end):
        return None
    return round(((end / start) - 1) * 100, 2)


def rs_slope(rs_line: pd.Series, window: int = 10) -> float:
    """
    Whether relative-strength outperformance is accelerating or fading.
    Expressed as the % change in the RS line's own value over `window` days
    -- simple and robust rather than a fitted regression slope, since this
    is meant to be a quick "still gaining ground?" read, not a precision
    estimate.
    """
    return pct_change_over(rs_line, window)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Average True Range (Wilder smoothing) -- used to normalize how far
    price has stretched away from its moving average."""
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def extension_in_atrs(close: pd.Series, sma_fast: pd.Series, atr_series: pd.Series) -> float:
    """
    How many ATRs price is currently sitting above (or below) its 50-day
    SMA. A guardrail against chasing names that are already historically
    stretched -- these are the ones most prone to a sharp pullback right
    as you'd be entering a fresh momentum position.
    """
    price = close.iloc[-1]
    fast = sma_fast.iloc[-1]
    a = atr_series.iloc[-1]
    if pd.isna(price) or pd.isna(fast) or pd.isna(a) or a == 0:
        return None
    return round((price - fast) / a, 2)


def dollar_volume(close: pd.Series, volume: pd.Series, period: int = 20) -> float:
    """Average daily dollar volume over `period` days -- a liquidity guardrail."""
    window = min(period, len(close))
    if window == 0:
        return None
    avg_price = close.iloc[-window:].mean()
    avg_vol = volume.iloc[-window:].mean()
    if pd.isna(avg_price) or pd.isna(avg_vol):
        return None
    return round(avg_price * avg_vol, 0)


def up_down_volume_ratio(close: pd.Series, volume: pd.Series, period: int = 20) -> float:
    """
    Sum of volume on up days divided by sum of volume on down days, over the
    trailing `period`. A single volume spike can just as easily be a
    news-driven pop that fades as it can be real accumulation; this instead
    checks whether volume has skewed toward up days or down days over a
    longer stretch, which is a sturdier signal for a 60+ day hold.
    """
    if len(close) < period + 1:
        return None
    change = close.diff().iloc[-period:]
    vol = volume.iloc[-period:]
    up_vol = vol[change > 0].sum()
    down_vol = vol[change < 0].sum()
    if down_vol == 0:
        return None
    return round(up_vol / down_vol, 2)
