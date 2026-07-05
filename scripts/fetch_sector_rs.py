"""
Part 1 -- Sector rotation screener.

Downloads the 11 Vanguard sector ETFs plus SPY, computes each ETF's price
performance relative to SPY (its own RS line) over daily/weekly/monthly/
quarterly/semiannual/yearly windows, ranks sectors by yearly RS, and writes
data/sectors.json for the front-end.

Sector breadth (% of each sector's own stocks currently RS-outperforming)
is filled in afterwards by fetch_stock_screener.py, once it has scored the
individual stocks -- that script updates this same JSON file rather than
duplicating the sector RS calculation.
"""

import json
import sys
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

from config import SECTOR_ETFS, BENCHMARK, RS_WINDOWS, HISTORY_PERIOD, OUTPUT_SECTORS
from indicators import pct_change_over, relative_strength_line


def fetch_price_history(tickers, period=HISTORY_PERIOD):
    """Download adjusted close for a list of tickers as one DataFrame (columns = tickers)."""
    raw = yf.download(tickers, period=period, auto_adjust=True, progress=False, group_by="ticker")
    closes = {}
    if len(tickers) == 1:
        closes[tickers[0]] = raw["Close"]
    else:
        for t in tickers:
            try:
                closes[t] = raw[t]["Close"]
            except KeyError:
                print(f"[sector_rs] WARNING: no data returned for {t}", file=sys.stderr)
    return pd.DataFrame(closes).dropna(how="all")


def build_sector_table():
    all_tickers = list(SECTOR_ETFS.keys()) + [BENCHMARK]
    prices = fetch_price_history(all_tickers)

    if BENCHMARK not in prices.columns:
        raise RuntimeError(f"Benchmark {BENCHMARK} failed to download; cannot compute relative strength.")

    benchmark_close = prices[BENCHMARK]
    rows = []

    for etf, sector in SECTOR_ETFS.items():
        if etf not in prices.columns:
            continue
        close = prices[etf].dropna()
        rs_line = relative_strength_line(close, benchmark_close)

        row = {
            "ticker": etf,
            "sector": sector,
            "last_close": round(close.iloc[-1], 2),
            "raw_return": {},
            "relative_strength": {},
            # filled in by fetch_stock_screener.py once stock-level data exists
            "breadth_pct_outperforming": None,
        }
        for label, window in RS_WINDOWS.items():
            row["raw_return"][label] = pct_change_over(close, window)
            row["relative_strength"][label] = pct_change_over(rs_line, window)

        rows.append(row)

    # Rank sectors by yearly relative strength (leadership) then by daily
    # (recent momentum) as a tiebreak-ish secondary sort for display order.
    rows.sort(key=lambda r: (r["relative_strength"]["yearly"] if r["relative_strength"]["yearly"] is not None else -999), reverse=True)
    for i, row in enumerate(rows, start=1):
        row["rs_rank"] = i

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "benchmark": BENCHMARK,
        "windows": list(RS_WINDOWS.keys()),
        "sectors": rows,
    }


def main():
    data = build_sector_table()
    with open(OUTPUT_SECTORS, "w") as f:
        json.dump(data, f, indent=2)
    print(f"[sector_rs] wrote {OUTPUT_SECTORS} with {len(data['sectors'])} sectors")


if __name__ == "__main__":
    main()
