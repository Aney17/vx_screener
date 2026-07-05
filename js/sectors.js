const WINDOW_LABELS = { daily: 'Daily', weekly: 'Weekly', monthly: 'Monthly', quarterly: '3M', semiannual: '6M', yearly: 'Yearly' };
const RS_COLUMNS = ['daily', 'weekly', 'monthly', 'quarterly', 'semiannual', 'yearly'];
let SECTOR_DATA = null;
let CURRENT_SORT = { key: 'yearly', dir: 'desc' };

function scaleMaxFor(sectors, key) {
  const vals = sectors.map(s => Math.abs(s.relative_strength[key] || 0));
  return Math.max(...vals, 1);
}

function breadthCell(row) {
  const pct = row.breadth_pct_outperforming;
  if (pct === null || pct === undefined) return '<span class="pill muted">—</span>';
  const cls = pct >= 60 ? 'positive' : (pct <= 30 ? 'negative' : 'neutral');
  const count = row.breadth_stock_count ? ` (${row.breadth_stock_count} stocks)` : '';
  return `<span class="rs-value ${cls}" title="Share of this sector's own stocks currently RS-outperforming SPY${count}">${pct.toFixed(0)}%</span>`;
}

function renderSectorTable() {
  const tbody = document.getElementById('sector-tbody');
  const accessor = (row, key) => key === 'breadth' ? row.breadth_pct_outperforming : row.relative_strength[key];
  const sectors = sortRows(SECTOR_DATA.sectors, CURRENT_SORT.key, CURRENT_SORT.dir, accessor);

  const scaleMax = {};
  RS_COLUMNS.forEach(k => { scaleMax[k] = scaleMaxFor(SECTOR_DATA.sectors, k); });

  tbody.innerHTML = sectors.map(row => {
    const cells = RS_COLUMNS.map(k =>
      `<td class="num">${rsCell(row.relative_strength[k], scaleMax[k])}</td>`
    ).join('');

    return `
      <tr data-sector="${encodeURIComponent(row.sector)}">
        <td>
          <span class="rank-cell">#${row.rs_rank ?? '—'}</span>
          <span class="sector-name">${row.sector}</span>
          <span class="sector-ticker">${row.ticker}</span>
        </td>
        <td class="num">$${fmtNum(row.last_close)}</td>
        ${cells}
        <td class="num">${breadthCell(row)}</td>
      </tr>
    `;
  }).join('');

  tbody.querySelectorAll('tr').forEach(tr => {
    tr.addEventListener('click', () => {
      const sector = tr.getAttribute('data-sector');
      window.location.href = `stocks.html?sector=${sector}`;
    });
  });
}

async function initSectorPage() {
  const snapshot = getSnapshotParam();
  initHistoryWidget('history-bar');

  try {
    SECTOR_DATA = await loadJSON(dataSourcePath('sectors.json'));
  } catch (e) {
    document.getElementById('sector-panel').innerHTML = snapshot ? `
      <div class="empty-state">
        No backup found for <strong>${snapshot}</strong>. It may be outside the 90-day
        retention window, or the pipeline wasn't run that day.
        <a href="index.html">Return to live data</a>.
      </div>` : `
      <div class="empty-state">
        No sector data yet. Run <code>python scripts/fetch_sector_rs.py</code> locally,
        or trigger the <strong>Update sector &amp; stock screener data</strong> workflow
        from the repo's Actions tab.
      </div>`;
    return;
  }

  setLastUpdated(SECTOR_DATA.generated_at);
  renderSectorTable();
  wireTopScrollbar('sector-scroll-top', 'sector-scroll-main');

  const thead = document.getElementById('sector-thead');
  thead.querySelector(`th[data-sort-key="yearly"]`).classList.add('sort-active');
  wireSortableHeaders(thead, (key, dir) => {
    CURRENT_SORT = { key, dir };
    renderSectorTable();
  });
}

document.addEventListener('DOMContentLoaded', initSectorPage);
