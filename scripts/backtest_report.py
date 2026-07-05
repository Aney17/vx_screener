"""
Turns the accumulated snapshot log (data/history/snapshots.jsonl) into an
actual answer to "does this signal work" -- rather than just describing
today's state, this looks back at every past breakout signal that's now old
enough to have completed a full holding period, and computes what it
actually returned.

Run this periodically (e.g. weekly) once snapshots.jsonl has enough history
-- it needs BACKTEST_HOLDING_DAYS of *trading days* to have elapsed since a
signal fired before that signal can be scored, so this will report nothing
useful until the log is a few months old.
"""

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

from config import SNAPSHOT_LOG, BACKTEST_HOLDING_DAYS, OUTPUT_BACKTEST, BENCHMARK


def load_snapshots():
    if not os.path.exists(SNAPSHOT_LOG):
        return []
    records = []
    with open(SNAPSHOT_LOG) as f:
        for line in f:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def eligible_for_scoring(records):
    """Only signals old enough that BACKTEST_HOLDING_DAYS of trading days
    have plausibly elapsed. Trading days ~= calendar days * 5/7, so we pad
    generously with calendar days to be safe -- the actual scoring below
    still counts real trading days from the price history."""
    cutoff_calendar_days = int(BACKTEST_HOLDING_DAYS * 1.6) + 5
    today = datetime.now(timezone.utc).date()
    out = []
    for r in records:
        signal_date = datetime.fromisoformat(r["signal_date"]).date()
        if (today - signal_date).days >= cutoff_calendar_days:
            out.append(r)
    return out


def score_forward_returns(records):
    if not records:
        return []

    tickers = sorted(set(r["ticker"] for r in records) | {BENCHMARK})
    earliest_signal = min(datetime.fromisoformat(r["signal_date"]) for r in records)
    start = earliest_signal.strftime("%Y-%m-%d")

    raw = yf.download(tickers, start=start, auto_adjust=True, progress=False, group_by="ticker")
    price_history = {}
    for t in tickers:
        try:
            price_history[t] = raw[t]["Close"].dropna() if len(tickers) > 1 else raw["Close"]
        except (KeyError, IndexError):
            print(f"[backtest] WARNING: no price history for {t}", file=sys.stderr)

    if BENCHMARK not in price_history:
        raise RuntimeError(f"Could not load {BENCHMARK} history for backtest comparison.")

    scored = []
    for r in records:
        ticker = r["ticker"]
        if ticker not in price_history:
            continue
        close = price_history[ticker]
        bench = price_history[BENCHMARK]
        signal_date = pd.Timestamp(r["signal_date"])

        close_after = close[close.index >= signal_date]
        bench_after = bench[bench.index >= signal_date]
        if len(close_after) <= BACKTEST_HOLDING_DAYS or len(bench_after) <= BACKTEST_HOLDING_DAYS:
            continue  # not enough trading days actually elapsed yet

        entry_price = close_after.iloc[0]
        exit_price = close_after.iloc[BACKTEST_HOLDING_DAYS]
        bench_entry = bench_after.iloc[0]
        bench_exit = bench_after.iloc[BACKTEST_HOLDING_DAYS]

        stock_return = ((exit_price / entry_price) - 1) * 100
        bench_return = ((bench_exit / bench_entry) - 1) * 100

        scored.append({
            **r,
            "forward_return_pct": round(stock_return, 2),
            "benchmark_return_pct": round(bench_return, 2),
            "excess_return_pct": round(stock_return - bench_return, 2),
        })

    return scored


def summarize(scored):
    if not scored:
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "holding_period_days": BACKTEST_HOLDING_DAYS,
            "signal_count": 0,
            "message": "No signals old enough to score yet. Keep the pipeline running daily -- "
                       f"this needs roughly {int(BACKTEST_HOLDING_DAYS * 1.6)} calendar days of "
                       "history before the first cohort completes its holding period.",
        }

    df = pd.DataFrame(scored)
    win_rate = round(100 * (df["excess_return_pct"] > 0).mean(), 1)

    by_sector = (
        df.groupby("sector")["excess_return_pct"]
        .agg(["mean", "count"])
        .round(2)
        .reset_index()
        .rename(columns={"mean": "avg_excess_return_pct", "count": "signal_count"})
        .to_dict(orient="records")
    )

    leading_vs_lagging = (
        df.groupby("sector_leading")["excess_return_pct"]
        .agg(["mean", "count"])
        .round(2)
        .reset_index()
        .to_dict(orient="records")
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "holding_period_days": BACKTEST_HOLDING_DAYS,
        "signal_count": len(scored),
        "win_rate_pct_beat_spy": win_rate,
        "avg_forward_return_pct": round(df["forward_return_pct"].mean(), 2),
        "avg_benchmark_return_pct": round(df["benchmark_return_pct"].mean(), 2),
        "avg_excess_return_pct": round(df["excess_return_pct"].mean(), 2),
        "by_sector": by_sector,
        "by_sector_leading_at_entry": leading_vs_lagging,
        "signals": scored,
    }


def main():
    records = load_snapshots()
    eligible = eligible_for_scoring(records)
    scored = score_forward_returns(eligible)
    summary = summarize(scored)

    with open(OUTPUT_BACKTEST, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"[backtest] {summary['signal_count']} signal(s) scored, wrote {OUTPUT_BACKTEST}")
    if summary["signal_count"]:
        print(f"[backtest] win rate vs SPY: {summary['win_rate_pct_beat_spy']}%, "
              f"avg excess return: {summary['avg_excess_return_pct']}%")


if __name__ == "__main__":
    main()
