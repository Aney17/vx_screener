/* ---------------------------------------------------------------
   Shared helpers
--------------------------------------------------------------- */

async function loadJSON(path) {
  const res = await fetch(path + '?_=' + Date.now()); // bust cache after each data refresh
  if (!res.ok) throw new Error(`Failed to load ${path}: ${res.status}`);
  return res.json();
}

// Reads ?snapshot=YYYY-MM-DD from the URL, if present -- this is how a page
// knows it should show a historical backup instead of the live data.
function getSnapshotParam() {
  const params = new URLSearchParams(window.location.search);
  const value = params.get('snapshot');
  return /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : null;
}

// Resolves the actual path to fetch for a given data file (sectors.json or
// stocks.json), depending on whether we're viewing live data or a historical
// snapshot from the calendar.
function dataSourcePath(filename) {
  const snapshot = getSnapshotParam();
  return snapshot ? `data/history/daily/${snapshot}/${filename}` : `data/${filename}`;
}

// Keeps the nav tabs pointed at the same snapshot date when the person
// switches between the sector rotation and stock screener pages while
// browsing history, rather than silently dropping them back to live data.
function carrySnapshotParamInNav() {
  const snapshot = getSnapshotParam();
  if (!snapshot) return;
  document.querySelectorAll('.nav-tabs a').forEach(a => {
    const url = new URL(a.href, window.location.href);
    url.searchParams.set('snapshot', snapshot);
    a.href = url.pathname + url.search;
  });
}

function fmtPct(value) {
  if (value === null || value === undefined) return '—';
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toFixed(2)}%`;
}

function pctClass(value) {
  if (value === null || value === undefined) return 'neutral';
  return value > 0 ? 'positive' : (value < 0 ? 'negative' : 'neutral');
}

function fmtNum(value, decimals = 2) {
  if (value === null || value === undefined) return '—';
  return value.toFixed(decimals);
}

function trendClass(trend) {
  return (trend || '').replace(/\s+\/\s+/g, '-').replace(/\s+/g, '-');
}

function setLastUpdated(iso) {
  const el = document.getElementById('last-updated');
  if (!el || !iso) return;
  const d = new Date(iso);
  const snapshot = getSnapshotParam();
  const formatted = d.toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
  });
  el.textContent = snapshot ? `Historical snapshot · ${formatted}` : `Data as of ${formatted}`;
  el.classList.toggle('snapshot-mode', !!snapshot);
}

// Renders a small horizontal bar representing an RS value against a shared
// scale, so magnitude is visually comparable across a whole column.
function rsBar(value, scaleMax) {
  const v = value || 0;
  const pct = Math.min(Math.abs(v) / scaleMax, 1) * 50; // half-track = full scale in one direction
  const color = v > 0 ? 'var(--gain)' : (v < 0 ? 'var(--loss)' : 'var(--text-faint)');
  const left = v >= 0 ? 50 : 50 - pct;
  const width = pct;
  return `<span class="rs-bar-track">
    <span class="rs-bar-fill" style="left:${left}%; width:${width}%; background:${color};"></span>
  </span>`;
}

function rsCell(value, scaleMax) {
  return `<span class="rs-cell">
    ${rsBar(value, scaleMax)}
    <span class="rs-value ${pctClass(value)}">${fmtPct(value)}</span>
  </span>`;
}

function sortRows(rows, key, dir, accessor) {
  const factor = dir === 'asc' ? 1 : -1;
  return [...rows].sort((a, b) => {
    const av = accessor(a, key);
    const bv = accessor(b, key);
    if (av === null || av === undefined) return 1;
    if (bv === null || bv === undefined) return -1;
    if (av < bv) return -1 * factor;
    if (av > bv) return 1 * factor;
    return 0;
  });
}

function wireSortableHeaders(theadEl, onSort) {
  theadEl.querySelectorAll('th[data-sort-key]').forEach(th => {
    th.addEventListener('click', () => {
      const key = th.getAttribute('data-sort-key');
      const currentDir = th.getAttribute('data-sort-dir') || 'desc';
      const nextDir = currentDir === 'desc' ? 'asc' : 'desc';
      theadEl.querySelectorAll('th').forEach(t => {
        t.classList.remove('sort-active');
        t.removeAttribute('data-sort-dir');
      });
      th.classList.add('sort-active');
      th.setAttribute('data-sort-dir', nextDir);
      onSort(key, nextDir);
    });
  });
}

/**
 * Mirrors a slim scrollbar at the top of a table with the real scrollable
 * container below it. With hundreds or thousands of rows, a bottom-only
 * scrollbar is effectively unreachable without scrolling all the way down
 * first -- this gives a way to scroll horizontally from the top of the page.
 * Call this once after the table's initial render; it keeps working
 * correctly across re-renders since it measures actual scrollWidth live.
 */
function wireTopScrollbar(topWrapperId, mainWrapperId) {
  const topEl = document.getElementById(topWrapperId);
  const mainEl = document.getElementById(mainWrapperId);
  if (!topEl || !mainEl) return;

  const inner = topEl.querySelector('.table-scroll-top-inner');
  const table = mainEl.querySelector('table');

  function syncWidth() {
    if (table) inner.style.width = table.scrollWidth + 'px';
  }

  let syncing = false;
  topEl.addEventListener('scroll', () => {
    if (syncing) return;
    syncing = true;
    mainEl.scrollLeft = topEl.scrollLeft;
    syncing = false;
  });
  mainEl.addEventListener('scroll', () => {
    if (syncing) return;
    syncing = true;
    topEl.scrollLeft = mainEl.scrollLeft;
    syncing = false;
  });

  // Table width can change as data loads/re-renders (e.g. filters changing
  // column content length) -- recheck on a short interval rather than
  // wiring a MutationObserver into every render path.
  syncWidth();
  window.addEventListener('resize', syncWidth);
  setInterval(syncWidth, 1000);
}
