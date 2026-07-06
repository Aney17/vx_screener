"""
Part 2 -- Total market screener.

For every stock in the combined holdings of the 11 sector ETFs, downloads
price/volume history and computes:
  - trend state (price vs SMA50 / SMA200)
  - momentum: RSI-14, MACD histogram, 1-month ROC, plus longer academic-style
    momentum (12-month return skipping the most recent month) -- the window
    that actually correlates with multi-month forward returns
  - relative strength vs SPY across daily..yearly windows, its slope (is
    outperformance accelerating or fading), and the date/age of the current
    RS breakout
  - volume: relative volume, plus a 20-day up/down volume ratio as a sturdier
    accumulation signal than a single day's spike
  - guardrails: extension above SMA50 in ATRs, and average dollar volume,
    both flagged (not filtered) so thin or overextended names stand out
  - sector context: each sector's own RS rank, so a stock's breakout can be
    read in light of whether its sector is actually leading or lagging

Writes data/stocks.json, grouped by sector. Also patches sector breadth
(% of each sector's stocks currently RS-outperforming) back into
data/sectors.json, and appends any freshly-triggered breakouts to
data/history/snapshots.jsonl for future backtesting.
"""

import json
import os
import sys
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

from config import (
    BENCHMARK, HISTORY_PERIOD, SMA_TREND_FAST, SMA_TREND_SLOW,
    RSI_PERIOD, ROC_PERIOD, VOLUME_AVG_PERIOD, RS_MA_PERIOD, RS_SLOPE_WINDOW,
    ATR_PERIOD, UP_DOWN_VOLUME_WINDOW, MOMENTUM_LOOKBACK, MOMENTUM_SKIP,
    LEADING_SECTOR_RANK_CUTOFF, LOW_LIQUIDITY_DOLLAR_VOL, EXTENSION_ATR_THRESHOLD,
    FOCUS_RSI_HEALTHY_MIN, FOCUS_RSI_HEALTHY_MAX, FOCUS_BREAKOUT_FRESH_DAYS,
    FOCUS_BREAKOUT_AGING_DAYS, OUTPUT_STOCKS, OUTPUT_SECTORS, SNAPSHOT_LOG, RS_WINDOWS,
)
from holdings import build_master_list
from indicators import (
    sma, rsi, macd, relative_volume, relative_strength_line,
    rs_breakout_date, rs_breakout_age, trend_state, pct_change_over,
    momentum_factor, rs_slope, atr, extension_in_atrs, dollar_volume,
    up_down_volume_ratio, classify_focus_tier,
)

BATCH_SIZE = 100  # yfinance handles multi-ticker downloads better in batches


def chunked(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def fetch_ohlcv_batch(tickers):
    """Returns dict ticker -> DataFrame with High/Low/Close/Volume columns."""
    raw = yf.download(tickers, period=HISTORY_PERIOD, auto_adjust=True,
                       progress=False, group_by="ticker", threads=True)
    out = {}
    for t in tickers:
        try:
            df = raw[t][["High", "Low", "Close", "Volume"]].dropna()
            if not df.empty:
                out[t] = df
        except (KeyError, IndexError):
            print(f"[stock_screener] WARNING: no data for {t}", file=sys.stderr)
    return out


def load_sector_ranks():
    """Reads data/sectors.json (already written by fetch_sector_rs.py) to get
    each sector's yearly-RS rank, so stock rows can carry sector context."""
    if not os.path.exists(OUTPUT_SECTORS):
        print("[stock_screener] WARNING: data/sectors.json not found -- run "
              "fetch_sector_rs.py first. Sector rank fields will be blank.", file=sys.stderr)
        return {}
    with open(OUTPUT_SECTORS) as f:
        data = json.load(f)
    return {row["sector"]: row["rs_rank"] for row in data.get("sectors", [])}


def _score_stock_raw(ticker, df, benchmark_close, sector_info, sector_ranks):
    high, low, close, volume = df["High"], df["Low"], df["Close"], df["Volume"]

    fast_ma = sma(close, SMA_TREND_FAST)
    slow_ma = sma(close, SMA_TREND_SLOW)
    rsi_series = rsi(close, RSI_PERIOD)
    _, _, macd_hist = macd(close)
    rs_line = relative_strength_line(close, benchmark_close)
    atr_series = atr(high, low, close, ATR_PERIOD)

    breakout_date = rs_breakout_date(rs_line, RS_MA_PERIOD)
    breakout_age = rs_breakout_age(rs_line, RS_MA_PERIOD)

    sector = sector_info.get("sector")
    sector_rank = sector_ranks.get(sector)

    relative_strength = {label: pct_change_over(rs_line, window) for label, window in RS_WINDOWS.items()}

    return {
        "ticker": ticker,
        "name": sector_info.get("name", ""),
        "sector": sector,
        "etf": sector_info.get("etf"),
        "last_close": round(close.iloc[-1], 2),
        "trend": trend_state(close, fast_ma, slow_ma),
        "sma50": round(fast_ma.iloc[-1], 2) if pd.notna(fast_ma.iloc[-1]) else None,
        "sma200": round(slow_ma.iloc[-1], 2) if pd.notna(slow_ma.iloc[-1]) else None,
        "rsi14": round(rsi_series.iloc[-1], 1) if pd.notna(rsi_series.iloc[-1]) else None,
        "macd_hist": round(macd_hist.iloc[-1], 3) if pd.notna(macd_hist.iloc[-1]) else None,
        "roc_1m_pct": pct_change_over(close, ROC_PERIOD),
        "momentum_12m_skip1m_pct": momentum_factor(close, MOMENTUM_LOOKBACK, MOMENTUM_SKIP),
        "relative_volume": relative_volume(volume, VOLUME_AVG_PERIOD),
        "up_down_volume_ratio": up_down_volume_ratio(close, volume, UP_DOWN_VOLUME_WINDOW),
        "relative_strength": relative_strength,
        "rs_vs_spy_1m_pct": relative_strength.get("monthly"),
        "rs_vs_spy_3m_pct": relative_strength.get("quarterly"),
        "rs_vs_spy_6m_pct": relative_strength.get("semiannual"),
        "rs_vs_spy_1y_pct": relative_strength.get("yearly"),
        "rs_slope_10d_pct": rs_slope(rs_line, RS_SLOPE_WINDOW),
        "rs_outperform_since": breakout_date,
        "rs_breakout_age_days": breakout_age,
        "currently_outperforming": breakout_date is not None,
        "extension_atrs": extension_in_atrs(close, fast_ma, atr_series),
        "extended_guardrail": bool(
            extension_in_atrs(close, fast_ma, atr_series) is not None
            and extension_in_atrs(close, fast_ma, atr_series) > EXTENSION_ATR_THRESHOLD
        ),
        "avg_dollar_volume": dollar_volume(close, volume, VOLUME_AVG_PERIOD),
        "low_liquidity_guardrail": bool(
            dollar_volume(close, volume, VOLUME_AVG_PERIOD) is not None
            and dollar_volume(close, volume, VOLUME_AVG_PERIOD) < LOW_LIQUIDITY_DOLLAR_VOL
        ),
        "sector_rs_rank": sector_rank,
        "sector_leading": bool(sector_rank is not None and sector_rank <= LEADING_SECTOR_RANK_CUTOFF),
    }


def score_stock(ticker, df, benchmark_close, sector_info, sector_ranks):
    record = _score_stock_raw(ticker, df, benchmark_close, sector_info, sector_ranks)
    record["focus_tier"] = classify_focus_tier(
        currently_outperforming=record["currently_outperforming"],
        breakout_age_days=record["rs_breakout_age_days"],
        trend=record["trend"],
        rsi14=record["rsi14"],
        rs_1m_pct=record["rs_vs_spy_1m_pct"],
        rs_6m_pct=record["rs_vs_spy_6m_pct"],
        extended_guardrail=record["extended_guardrail"],
        low_liquidity_guardrail=record["low_liquidity_guardrail"],
        rsi_healthy_min=FOCUS_RSI_HEALTHY_MIN,
        rsi_healthy_max=FOCUS_RSI_HEALTHY_MAX,
        fresh_days=FOCUS_BREAKOUT_FRESH_DAYS,
        aging_days=FOCUS_BREAKOUT_AGING_DAYS,
    )
    return record


def build_stock_table():
    stock_sectors = build_master_list()
    if not stock_sectors:
        raise RuntimeError(
            "No holdings loaded. Add CSVs to data/holdings/<TICKER>.csv "
            "for at least one sector ETF before running this script."
        )

    sector_ranks = load_sector_ranks()

    tickers = sorted(stock_sectors.keys())
    all_needed = tickers + [BENCHMARK]

    price_data = {}
    for batch in chunked(all_needed, BATCH_SIZE):
        price_data.update(fetch_ohlcv_batch(batch))

    if BENCHMARK not in price_data:
        raise RuntimeError(f"Benchmark {BENCHMARK} failed to download; cannot compute relative strength.")

    benchmark_close = price_data[BENCHMARK]["Close"]

    results = []
    for ticker in tickers:
        if ticker not in price_data:
            continue
        df = price_data[ticker]
        if len(df) < SMA_TREND_FAST:  # not enough history to be useful
            continue
        try:
            results.append(score_stock(ticker, df, benchmark_close, stock_sectors[ticker], sector_ranks))
        except Exception as e:
            print(f"[stock_screener] WARNING: failed to score {ticker}: {e}", file=sys.stderr)

    # Sort so the strongest, most recent relative-strength breakouts surface first.
    results.sort(key=lambda r: (r["rs_vs_spy_1m_pct"] is None, -(r["rs_vs_spy_1m_pct"] or 0)))

    grouped = {}
    for r in results:
        grouped.setdefault(r["sector"], []).append(r)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "benchmark": BENCHMARK,
        "stock_count": len(results),
        "sectors": grouped,
    }


def patch_sector_breadth(stock_data):
    """Writes % of each sector's stocks currently RS-outperforming back into
    data/sectors.json, so the sector page can show whether a sector's move
    is broad-based or just a couple of names carrying it."""
    if not os.path.exists(OUTPUT_SECTORS):
        return
    with open(OUTPUT_SECTORS) as f:
        sectors_data = json.load(f)

    for row in sectors_data.get("sectors", []):
        stocks = stock_data["sectors"].get(row["sector"], [])
        if stocks:
            outperforming = sum(1 for s in stocks if s["currently_outperforming"])
            row["breadth_pct_outperforming"] = round(100 * outperforming / len(stocks), 1)
            row["breadth_stock_count"] = len(stocks)

    with open(OUTPUT_SECTORS, "w") as f:
        json.dump(sectors_data, f, indent=2)


def log_fresh_breakouts(stock_data):
    """
    Appends one JSON line per stock whose RS breakout started today (age 0)
    to an append-only history log. This is the raw material for eventually
    computing actual forward 60-day returns once enough runs have
    accumulated -- turning this from a snapshot screener into something that
    can be validated against real outcomes.
    """
    os.makedirs(os.path.dirname(SNAPSHOT_LOG), exist_ok=True)
    today = datetime.now(timezone.utc).date().isoformat()

    # avoid double-logging if the pipeline is re-run the same day
    already_logged_today = set()
    if os.path.exists(SNAPSHOT_LOG):
        with open(SNAPSHOT_LOG) as f:
            for line in f:
                try:
                    rec = json.loads(line)
                    if rec.get("signal_date") == today:
                        already_logged_today.add(rec["ticker"])
                except json.JSONDecodeError:
                    continue

    new_entries = []
    for sector, stocks in stock_data["sectors"].items():
        for s in stocks:
            if s.get("rs_breakout_age_days") == 0 and s["ticker"] not in already_logged_today:
                new_entries.append({
                    "signal_date": today,
                    "ticker": s["ticker"],
                    "sector": s["sector"],
                    "entry_price": s["last_close"],
                    "rsi14": s["rsi14"],
                    "relative_volume": s["relative_volume"],
                    "roc_1m_pct": s["roc_1m_pct"],
                    "rs_vs_spy_1m_pct": s["rs_vs_spy_1m_pct"],
                    "sector_rs_rank": s["sector_rs_rank"],
                    "sector_leading": s["sector_leading"],
                    "extension_atrs": s["extension_atrs"],
                })

    if new_entries:
        with open(SNAPSHOT_LOG, "a") as f:
            for entry in new_entries:
                f.write(json.dumps(entry) + "\n")
        print(f"[stock_screener] logged {len(new_entries)} fresh breakout(s) to {SNAPSHOT_LOG}")


def main():
    data = build_stock_table()
    with open(OUTPUT_STOCKS, "w") as f:
        json.dump(data, f, indent=2)
    print(f"[stock_screener] wrote {OUTPUT_STOCKS} with {data['stock_count']} stocks "
          f"across {len(data['sectors'])} sectors")

    patch_sector_breadth(data)
    log_fresh_breakouts(data)


if __name__ == "__main__":
    main()
