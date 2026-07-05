/* ---------------------------------------------------------------
   Historical snapshot calendar picker.

   Shared by both index.html and stocks.html. Reads
   data/history/daily/manifest.json to know which dates have an archived
   backup, renders a month calendar with those dates marked, and navigates
   to ?snapshot=YYYY-MM-DD on the current page when one is selected.
   Navigation is a full page load rather than in-place data swapping --
   simpler and avoids the render pipeline needing two code paths.
--------------------------------------------------------------- */

let HISTORY_MANIFEST = null;
let HISTORY_VIEW_MONTH = null; // {year, month} currently displayed in the popover, independent of the selected snapshot

function pad2(n) { return String(n).padStart(2, '0'); }
function isoDate(year, month, day) { return `${year}-${pad2(month + 1)}-${pad2(day)}`; }

async function initHistoryWidget(containerId) {
  const container = document.getElementById(containerId);
  if (!container) return;

  const selected = getSnapshotParam();
  const today = new Date();

  try {
    HISTORY_MANIFEST = await loadJSON('data/history/daily/manifest.json');
  } catch (e) {
    HISTORY_MANIFEST = { dates: {} };
  }

  const initialDate = selected ? new Date(selected + 'T00:00:00') : today;
  HISTORY_VIEW_MONTH = { year: initialDate.getFullYear(), month: initialDate.getMonth() };

  container.innerHTML = `
    <div class="history-control">
      <button class="btn btn-ghost" id="history-toggle" type="button">
        ${selected ? `Viewing ${selected}` : 'Historical snapshots'}
      </button>
      <div class="history-popover" id="history-popover" hidden>
        <div class="history-popover-header">
          <button class="cal-nav" id="cal-prev" type="button" aria-label="Previous month">&#8249;</button>
          <span class="cal-month-label" id="cal-month-label"></span>
          <button class="cal-nav" id="cal-next" type="button" aria-label="Next month">&#8250;</button>
        </div>
        <div class="history-cal-grid" id="cal-grid"></div>
        <div class="history-legend">
          <span><span class="cal-dot cal-dot-ring"></span>backup available</span>
          <span><span class="cal-dot cal-dot-solid"></span>viewing this date</span>
          <span><span class="cal-dot cal-dot-today"></span>today</span>
        </div>
      </div>
    </div>
    ${selected ? `
    <div class="history-banner" id="history-banner">
      Viewing snapshot &middot; <strong>${selected}</strong>
      ${HISTORY_MANIFEST.dates[selected] ? `&middot; ${HISTORY_MANIFEST.dates[selected].sector_count} sectors &middot; ${HISTORY_MANIFEST.dates[selected].stock_count} stocks` : ''}
      <button class="btn btn-ghost" id="history-return" type="button">Return to live data</button>
    </div>` : ''}
  `;

  renderCalendarGrid(selected, today);

  const toggle = document.getElementById('history-toggle');
  const popover = document.getElementById('history-popover');
  toggle.addEventListener('click', (e) => {
    e.stopPropagation();
    popover.hidden = !popover.hidden;
  });
  document.addEventListener('click', (e) => {
    if (!popover.hidden && !popover.contains(e.target) && e.target !== toggle) {
      popover.hidden = true;
    }
  });

  document.getElementById('cal-prev').addEventListener('click', () => shiftMonth(-1, selected, today));
  document.getElementById('cal-next').addEventListener('click', () => shiftMonth(1, selected, today));

  const returnBtn = document.getElementById('history-return');
  if (returnBtn) {
    returnBtn.addEventListener('click', () => {
      const url = new URL(window.location.href);
      url.searchParams.delete('snapshot');
      window.location.href = url.pathname + url.search;
    });
  }

  carrySnapshotParamInNav();
}

function shiftMonth(delta, selected, today) {
  let { year, month } = HISTORY_VIEW_MONTH;
  month += delta;
  if (month < 0) { month = 11; year -= 1; }
  if (month > 11) { month = 0; year += 1; }
  HISTORY_VIEW_MONTH = { year, month };
  renderCalendarGrid(selected, today);
}

function renderCalendarGrid(selected, today) {
  const { year, month } = HISTORY_VIEW_MONTH;
  const label = new Date(year, month, 1).toLocaleString(undefined, { month: 'long', year: 'numeric' });
  document.getElementById('cal-month-label').textContent = label;

  const firstWeekday = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const todayIso = isoDate(today.getFullYear(), today.getMonth(), today.getDate());

  const dayHeaders = ['S', 'M', 'T', 'W', 'T', 'F', 'S']
    .map(d => `<div class="cal-day-header">${d}</div>`).join('');

  let cells = '';
  for (let i = 0; i < firstWeekday; i++) cells += '<div></div>';

  for (let day = 1; day <= daysInMonth; day++) {
    const dateIso = isoDate(year, month, day);
    const hasBackup = !!(HISTORY_MANIFEST.dates && HISTORY_MANIFEST.dates[dateIso]);
    const isSelected = dateIso === selected;
    const isToday = dateIso === todayIso;

    let cls = 'cal-day';
    if (isSelected) cls += ' cal-day-selected';
    else if (hasBackup) cls += ' cal-day-has-backup';
    else cls += ' cal-day-empty';
    if (isToday && !isSelected) cls += ' cal-day-today';

    if (hasBackup) {
      const info = HISTORY_MANIFEST.dates[dateIso];
      cells += `<div class="cal-cell"><button type="button" class="${cls}" data-date="${dateIso}" title="${info.stock_count} stocks, ${info.sector_count} sectors">${day}</button></div>`;
    } else {
      cells += `<div class="cal-cell"><span class="${cls}">${day}</span></div>`;
    }
  }

  document.getElementById('cal-grid').innerHTML = dayHeaders + cells;

  document.querySelectorAll('button.cal-day').forEach(btn => {
    btn.addEventListener('click', () => {
      const date = btn.getAttribute('data-date');
      const url = new URL(window.location.href);
      url.searchParams.set('snapshot', date);
      window.location.href = url.pathname + url.search;
    });
  });
}
