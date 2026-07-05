"""
Archives that day's sectors.json + stocks.json into a dated folder under
data/history/daily/, so the front end's calendar picker can load any prior
day's full snapshot later. Run this after both fetch_sector_rs.py and
fetch_stock_screener.py have written the live data files for the day.

Also maintains data/history/daily/manifest.json -- a small index of which
dates have a backup and how big each one was -- since a static site can't
list a directory itself; the calendar reads this manifest to know which
dates to mark.

Backups older than HISTORY_RETENTION_DAYS are pruned automatically on each
run, so the repo doesn't grow without bound. Retention is a rolling window,
not permanent archival -- if you want it kept longer, raise
HISTORY_RETENTION_DAYS in config.py (git history itself still has every
commit regardless, this just controls what the live calendar can serve).
"""

import json
import os
import shutil
import sys
from datetime import datetime, timezone, timedelta

from config import (
    OUTPUT_SECTORS, OUTPUT_STOCKS, HISTORY_DAILY_DIR, HISTORY_MANIFEST,
    HISTORY_RETENTION_DAYS,
)


def load_manifest():
    if not os.path.exists(HISTORY_MANIFEST):
        return {"dates": {}}
    with open(HISTORY_MANIFEST) as f:
        return json.load(f)


def save_manifest(manifest):
    os.makedirs(os.path.dirname(HISTORY_MANIFEST), exist_ok=True)
    with open(HISTORY_MANIFEST, "w") as f:
        json.dump(manifest, f, indent=2)


def backup_today():
    if not os.path.exists(OUTPUT_SECTORS) or not os.path.exists(OUTPUT_STOCKS):
        raise RuntimeError(
            "Both data/sectors.json and data/stocks.json must exist before backing up. "
            "Run fetch_sector_rs.py and fetch_stock_screener.py first."
        )

    today = datetime.now(timezone.utc).date().isoformat()
    day_dir = os.path.join(HISTORY_DAILY_DIR, today)
    os.makedirs(day_dir, exist_ok=True)

    shutil.copy(OUTPUT_SECTORS, os.path.join(day_dir, "sectors.json"))
    shutil.copy(OUTPUT_STOCKS, os.path.join(day_dir, "stocks.json"))

    with open(OUTPUT_STOCKS) as f:
        stock_count = json.load(f).get("stock_count", 0)
    with open(OUTPUT_SECTORS) as f:
        sector_count = len(json.load(f).get("sectors", []))

    manifest = load_manifest()
    manifest["dates"][today] = {
        "stock_count": stock_count,
        "sector_count": sector_count,
        "archived_at": datetime.now(timezone.utc).isoformat(),
    }
    return manifest, today


def prune_old_backups(manifest):
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=HISTORY_RETENTION_DAYS)
    removed = []
    for date_str in list(manifest["dates"].keys()):
        try:
            date_val = datetime.fromisoformat(date_str).date()
        except ValueError:
            continue
        if date_val < cutoff:
            day_dir = os.path.join(HISTORY_DAILY_DIR, date_str)
            if os.path.exists(day_dir):
                shutil.rmtree(day_dir)
            del manifest["dates"][date_str]
            removed.append(date_str)
    return removed


def main():
    manifest, today = backup_today()
    removed = prune_old_backups(manifest)
    save_manifest(manifest)

    print(f"[backup] archived {today} ({manifest['dates'][today]['stock_count']} stocks, "
          f"{manifest['dates'][today]['sector_count']} sectors)")
    if removed:
        print(f"[backup] pruned {len(removed)} backup(s) older than "
              f"{HISTORY_RETENTION_DAYS} days: {', '.join(sorted(removed))}")
    print(f"[backup] manifest now has {len(manifest['dates'])} date(s) available")


if __name__ == "__main__":
    main()
