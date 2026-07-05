"""
Reads holdings exports (one per sector ETF) from data/holdings/{TICKER}.* and
builds a single deduplicated stock -> sector mapping.

Supports both formats Vanguard actually hands out:
  - .xlsx  -- the real "Portfolio holdings" export from institutional.vanguard.com
              (Portfolio & Management tab -> Download holdings). This is a
              single-sheet workbook with a few metadata rows at the top
              (download date, fund name, "as at" date), then a header row
              ("Ticker", "Holding name", "% of market value", "Sector",
              "Region", "Market value", "Shares"), then one data row per
              holding, terminated by a blank row and a disclaimer paragraph.
  - .csv   -- a plain CSV with a clean header row, in case you've exported
              from somewhere else or hand-built one for testing.

If both exist for a ticker, the .xlsx takes precedence since it's the
authoritative Vanguard export.
"""

import csv
import os
from config import SECTOR_ETFS, HOLDINGS_DIR

try:
    import openpyxl
except ImportError:
    openpyxl = None

# Common header spellings Vanguard has used across fund exports.
TICKER_HEADERS = {"ticker", "holding ticker", "symbol"}
NAME_HEADERS = {"holding name", "name", "security name"}

# Rows whose ticker cell matches one of these (case-insensitive) aren't real
# holdings and should be skipped if Vanguard ever includes them.
NON_HOLDING_TICKERS = {"CASH", "CASH_USD", "N/A", "USD", "FUTURES"}


def _clean_ticker(raw):
    """
    Normalizes a raw ticker string to what yfinance/Yahoo Finance expects.
    Vanguard's export uses a slash for share classes (e.g. "BRK/B", "HEI/A");
    Yahoo Finance uses a hyphen instead ("BRK-B", "HEI-A").

    Also filters out CUSIP-style identifiers Vanguard occasionally lists for
    holdings that don't trade under a normal ticker (private placements,
    restricted shares, escrow positions, etc.) -- these show up as
    alphanumeric codes starting with a digit, which no real US equity
    ticker does. Sending these to Yahoo Finance just produces a 404.
    """
    if not raw:
        return None
    ticker = str(raw).strip().upper().replace("/", "-")
    if not ticker or ticker in NON_HOLDING_TICKERS:
        return None
    if not all(c.isalnum() or c in ".-" for c in ticker):
        return None
    if ticker[0].isdigit():
        return None
    return ticker


def _find_column(fieldnames, candidates):
    lowered = {f.lower().strip(): f for f in fieldnames}
    for candidate in candidates:
        if candidate in lowered:
            return lowered[candidate]
    return None


def load_holdings_xlsx(path):
    """Return list of (ticker, name) tuples from a Vanguard .xlsx export."""
    if openpyxl is None:
        raise RuntimeError(
            "openpyxl is required to read .xlsx holdings files. "
            "Install it with: pip install openpyxl"
        )
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb.active

    rows = []
    header_idx = None
    ticker_col = name_col = None

    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if header_idx is None:
            # Look for the header row rather than assuming a fixed offset --
            # Vanguard has changed the number of preamble rows before.
            if row and row[0] and str(row[0]).strip().lower() in TICKER_HEADERS:
                header_idx = i
                header = [str(c).strip() if c else "" for c in row]
                ticker_col = header.index(next(c for c in header if c.lower() in TICKER_HEADERS))
                name_candidates = [c for c in header if c.lower() in NAME_HEADERS]
                name_col = header.index(name_candidates[0]) if name_candidates else None
            continue

        if row is None or all(c is None for c in row):
            break  # blank row marks the end of the holdings table

        ticker = _clean_ticker(row[ticker_col] if ticker_col < len(row) else None)
        if not ticker:
            continue
        name = ""
        if name_col is not None and name_col < len(row) and row[name_col]:
            name = str(row[name_col]).strip()
        rows.append((ticker, name))

    if header_idx is None:
        raise ValueError(f"Could not find a 'Ticker' header row in {path}.")

    return rows


def load_holdings_csv(path):
    """Return list of (ticker, name) tuples from one holdings CSV."""
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        ticker_col = _find_column(reader.fieldnames or [], TICKER_HEADERS)
        name_col = _find_column(reader.fieldnames or [], NAME_HEADERS)
        if not ticker_col:
            raise ValueError(f"Could not find a ticker column in {path}. "
                              f"Found columns: {reader.fieldnames}")
        for row in reader:
            ticker = _clean_ticker(row.get(ticker_col))
            if not ticker:
                continue
            name = (row.get(name_col) or "").strip() if name_col else ""
            rows.append((ticker, name))
    return rows


def load_holdings_file(base_path_no_ext):
    """Tries .xlsx first (the real Vanguard export), then .csv."""
    xlsx_path = base_path_no_ext + ".xlsx"
    csv_path = base_path_no_ext + ".csv"
    if os.path.exists(xlsx_path):
        return load_holdings_xlsx(xlsx_path), xlsx_path
    if os.path.exists(csv_path):
        return load_holdings_csv(csv_path), csv_path
    return None, None


def build_master_list(holdings_dir=HOLDINGS_DIR):
    """
    Returns:
        stock_sectors: dict ticker -> {"sector": ..., "etf": ..., "name": ..., "in_sectors": [etf,...]}
    A stock can technically appear in more than one sector fund only in edge
    cases (fund reclassification lag); we keep the first sector we see and
    record any others in in_sectors for transparency.
    """
    stock_sectors = {}
    missing = []

    for etf, sector in SECTOR_ETFS.items():
        base_path = os.path.join(holdings_dir, etf)
        rows, used_path = load_holdings_file(base_path)
        if rows is None:
            missing.append(etf)
            continue

        for ticker, name in rows:
            if ticker not in stock_sectors:
                stock_sectors[ticker] = {
                    "sector": sector,
                    "etf": etf,
                    "name": name,
                    "in_sectors": [etf],
                }
            else:
                if etf not in stock_sectors[ticker]["in_sectors"]:
                    stock_sectors[ticker]["in_sectors"].append(etf)

    if missing:
        print(f"[holdings] WARNING: no holdings file found for: {', '.join(missing)}. "
              f"Expected {holdings_dir}/<TICKER>.xlsx or .csv. These sectors will be "
              f"skipped in the stock screener until you add them.")

    return stock_sectors


if __name__ == "__main__":
    result = build_master_list()
    print(f"Loaded {len(result)} unique stocks across available sector holdings files.")
