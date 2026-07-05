let STOCK_DATA = null;
let ALL_ROWS = [];
let CURRENT_SORT = { key: 'rs_vs_spy_1m_pct', dir: 'desc' };

function flattenRows(data) {
  const rows = [];
  Object.entries(data.sectors).forEach(([sector, list]) => {
    list.forEach(r => rows.push(r));
  });
  return rows;
}

function applyFilters(rows) {
  const sectorFilter = document.getElementById('sector-filter').value;
  const search = document.getElementById('search-box').value.trim().toUpperCase();
  const breakoutOnly = document.getElementById('breakout-only').checked;
  const hideGuardrails = document.getElementById('hide-guardrails').checked;

  const trendFilter = document.getElementById('trend-filter').value;
  const minRs1m = parseFloat(document.getElementById('min-rs1m').value);
  const minRelVol = parseFloat(document.getElementById('min-relvol').value);
  const maxRsi = parseFloat(document.getElementById('max-rsi').value);

  return rows.filter(r => {
    if (sectorFilter !== 'all' && r.sector !== sectorFilter) return false;
    if (breakoutOnly && !r.currently_outperforming) return false;
    if (hideGuardrails && (r.extended_guardrail || r.low_liquidity_guardrail)) return false;
    if (trendFilter !== 'all' && r.trend !== trendFilter) return false;
    if (!isNaN(minRs1m) && (r.rs_vs_spy_1m_pct === null || r.rs_vs_spy_1m_pct < minRs1m)) return false;
    if (!isNaN(minRelVol) && (r.relative_volume === null || r.relative_volume < minRelVol)) return false;
    if (!isNaN(maxRsi) && (r.rsi14 === null || r.rsi14 > maxRsi)) return false;
    if (search) {
      const hay = `${r.ticker} ${r.name}`.toUpperCase();
      if (!hay.includes(search)) return false;
    }
    return true;
  });
}

function renderStatStrip(rows) {
  const total = rows.length;
  const outperforming = rows.filter(r => r.currently_outperforming).length;
  const strongUptrend = rows.filter(r => r.trend === 'strong uptrend').length;
  const avgRsr = rows.length
    ? (rows.reduce((sum, r) => sum + (r.rs_vs_spy_1m_pct || 0), 0) / rows.length)
    : 0;

  document.getElementById('stat-strip').innerHTML = `
    <div class="stat-chip"><div class="label">Stocks shown</div><div class="value">${total}</div></div>
    <div class="stat-chip"><div class="label">RS breakouts active</div><div class="value" style="color:var(--amber)">${outperforming}</div></div>
    <div class="stat-chip"><div class="label">Strong uptrend</div><div class="value" style="color:var(--gain)">${strongUptrend}</div></div>
    <div class="stat-chip"><div class="label">Avg 1M RS vs SPY</div><div class="value ${pctClass(avgRsr)}">${fmtPct(avgRsr)}</div></div>
  `;
}

function extensionCell(r) {
  if (r.extension_atrs === null || r.extension_atrs === undefined) return '—';
  const cls = r.extended_guardrail ? 'guardrail-warn' : pctClass(r.extension_atrs);
  const flag = r.extended_guardrail ? ' ⚠' : '';
  return `<span class="${cls}" title="Price is ${fmtNum(r.extension_atrs, 1)} ATRs above its 50-day SMA${r.extended_guardrail ? ' — historically extended, higher pullback risk' : ''}">${fmtNum(r.extension_atrs, 1)}${flag}</span>`;
}

function breakoutCell(r) {
  if (!r.currently_outperforming) return `<span class="pill muted">not leading</span>`;
  const age = r.rs_breakout_age_days;
  const ageLabel = age !== null && age !== undefined ? ` (${age}d)` : '';
  return `<span class="pill amber breakout-date">since ${r.rs_outperform_since}${ageLabel}</span>`;
}

function renderTable() {
  const filtered = applyFilters(ALL_ROWS);
  renderStatStrip(filtered);

  const sorted = sortRows(filtered, CURRENT_SORT.key, CURRENT_SORT.dir, (row, key) => row[key]);
  const tbody = document.getElementById('stock-tbody');

  if (sorted.length === 0) {
    tbody.innerHTML = `<tr><td colspan="16"><div class="empty-state">No stocks match the current filters.</div></td></tr>`;
    return;
  }

  tbody.innerHTML = sorted.map(r => {
    const liquidityFlag = r.low_liquidity_guardrail ? ' <span class="pill muted" title="Average dollar volume is below the liquidity guardrail threshold">thin</span>' : '';
    return `
    <tr>
      <td>
        <span class="ticker-cell">${r.ticker}</span>${liquidityFlag}
        <span class="name-sub">${r.name || ''} · ${r.sector}</span>
      </td>
      <td class="num">$${fmtNum(r.last_close)}</td>
      <td><span class="trend-tag ${trendClass(r.trend)}">${r.trend}</span></td>
      <td class="num">${r.rsi14 !== null ? fmtNum(r.rsi14, 1) : '—'}</td>
      <td class="num ${pctClass(r.macd_hist)}">${r.macd_hist !== null ? fmtNum(r.macd_hist, 3) : '—'}</td>
      <td class="num ${pctClass(r.roc_1m_pct)}">${fmtPct(r.roc_1m_pct)}</td>
      <td class="num ${pctClass(r.momentum_12m_skip1m_pct)}">${fmtPct(r.momentum_12m_skip1m_pct)}</td>
      <td class="num">${r.relative_volume !== null ? fmtNum(r.relative_volume, 2) + '×' : '—'}</td>
      <td class="num">${r.up_down_volume_ratio !== null ? fmtNum(r.up_down_volume_ratio, 2) + '×' : '—'}</td>
      <td class="num ${pctClass(r.rs_vs_spy_1m_pct)}">${fmtPct(r.rs_vs_spy_1m_pct)}</td>
      <td class="num ${pctClass(r.rs_vs_spy_3m_pct)}">${fmtPct(r.rs_vs_spy_3m_pct)}</td>
      <td class="num ${pctClass(r.rs_vs_spy_6m_pct)}">${fmtPct(r.rs_vs_spy_6m_pct)}</td>
      <td class="num ${pctClass(r.rs_vs_spy_1y_pct)}">${fmtPct(r.rs_vs_spy_1y_pct)}</td>
      <td class="num ${pctClass(r.rs_slope_10d_pct)}">${fmtPct(r.rs_slope_10d_pct)}</td>
      <td>${breakoutCell(r)}</td>
      <td class="num">${extensionCell(r)}</td>
    </tr>
  `;
  }).join('');
}

function populateSectorFilter(data) {
  const select = document.getElementById('sector-filter');
  const sectors = Object.keys(data.sectors).sort();
  select.innerHTML = `<option value="all">All sectors</option>` +
    sectors.map(s => `<option value="${s}">${s}</option>`).join('');

  const params = new URLSearchParams(window.location.search);
  const preset = params.get('sector');
  if (preset && sectors.includes(preset)) {
    select.value = preset;
  }
}

async function initStockPage() {
  const snapshot = getSnapshotParam();
  initHistoryWidget('history-bar');

  try {
    STOCK_DATA = await loadJSON(dataSourcePath('stocks.json'));
  } catch (e) {
    document.getElementById('stock-panel').innerHTML = snapshot ? `
      <div class="empty-state">
        No backup found for <strong>${snapshot}</strong>. It may be outside the 90-day
        retention window, or the pipeline wasn't run that day.
        <a href="stocks.html">Return to live data</a>.
      </div>` : `
      <div class="empty-state">
        No stock screener data yet. Add holdings CSVs to <code>data/holdings/</code>,
        then run <code>python scripts/fetch_stock_screener.py</code> locally,
        or trigger the <strong>Update sector &amp; stock screener data</strong> workflow
        from the repo's Actions tab.
      </div>`;
    document.getElementById('filters-row').style.display = 'none';
    document.getElementById('filters-row-2').style.display = 'none';
    return;
  }

  setLastUpdated(STOCK_DATA.generated_at);
  ALL_ROWS = flattenRows(STOCK_DATA);
  populateSectorFilter(STOCK_DATA);

  document.getElementById('sector-filter').addEventListener('change', renderTable);
  document.getElementById('search-box').addEventListener('input', renderTable);
  document.getElementById('breakout-only').addEventListener('change', renderTable);
  document.getElementById('hide-guardrails').addEventListener('change', renderTable);
  document.getElementById('trend-filter').addEventListener('change', renderTable);
  document.getElementById('min-rs1m').addEventListener('input', renderTable);
  document.getElementById('min-relvol').addEventListener('input', renderTable);
  document.getElementById('max-rsi').addEventListener('input', renderTable);

  document.getElementById('reset-filters').addEventListener('click', () => {
    document.getElementById('sector-filter').value = 'all';
    document.getElementById('search-box').value = '';
    document.getElementById('breakout-only').checked = false;
    document.getElementById('hide-guardrails').checked = false;
    document.getElementById('trend-filter').value = 'all';
    document.getElementById('min-rs1m').value = '';
    document.getElementById('min-relvol').value = '';
    document.getElementById('max-rsi').value = '';
    renderTable();
  });

  const thead = document.getElementById('stock-thead');
  thead.querySelector(`th[data-sort-key="rs_vs_spy_1m_pct"]`).classList.add('sort-active');
  wireSortableHeaders(thead, (key, dir) => {
    CURRENT_SORT = { key, dir };
    renderTable();
  });

  renderTable();
  wireTopScrollbar('stock-scroll-top', 'stock-scroll-main');
}

document.addEventListener('DOMContentLoaded', initStockPage);
