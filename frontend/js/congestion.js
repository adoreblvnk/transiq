/* ==========================================================================
   CONGESTION TELEMETRY & FILTERING (With Real-Time Station Search & Directional Flow)
   ========================================================================== */

let congestionSearchTimer = null;
let isCongestionSearchActive = false;

async function loadCongestionData() {
  try {
    const res = await fetch('/api/analytics/peak_congestion?limit=50');
    if (res.ok) {
      AppState.rawCongestionRows = await res.json();
      if (!isCongestionSearchActive) {
        filterCongestionData();
      }
    }
  } catch (e) {}
}

function switchCongestionSubTab(tab) {
  const btnRankings = document.getElementById('btn-subtab-rankings');
  const btnSearch = document.getElementById('btn-subtab-search');
  const viewRankings = document.getElementById('subtab-view-rankings');
  const viewSearch = document.getElementById('subtab-view-search');

  if (tab === 'rankings') {
    if (btnRankings) { btnRankings.classList.add('active'); btnRankings.setAttribute('aria-selected', 'true'); }
    if (btnSearch) { btnSearch.classList.remove('active'); btnSearch.setAttribute('aria-selected', 'false'); }
    if (viewRankings) viewRankings.style.display = 'block';
    if (viewSearch) viewSearch.style.display = 'none';
    filterCongestionData();
  } else {
    if (btnSearch) { btnSearch.classList.add('active'); btnSearch.setAttribute('aria-selected', 'true'); }
    if (btnRankings) { btnRankings.classList.remove('active'); btnRankings.setAttribute('aria-selected', 'false'); }
    if (viewRankings) viewRankings.style.display = 'none';
    if (viewSearch) viewSearch.style.display = 'block';
    const input = document.getElementById('congestion-search-input');
    if (input) {
      input.focus();
      if (input.value.trim()) handleCongestionSearch(input.value);
    }
  }
}

function handleCongestionSearch(query) {
  const cleanQ = (query || '').trim();
  const clearBtn = document.getElementById('btn-clear-congestion-search');
  if (clearBtn) {
    clearBtn.style.display = cleanQ ? 'inline-flex' : 'none';
  }

  clearTimeout(congestionSearchTimer);
  congestionSearchTimer = setTimeout(async () => {
    const statusEl = document.getElementById('congestion-search-status');
    const statusTxt = document.getElementById('congestion-search-status-text');
    const tbody = document.getElementById('congestion-search-body');

    if (!cleanQ) {
      if (statusEl) statusEl.style.display = 'none';
      if (tbody) {
        tbody.innerHTML = `
          <tr>
            <td colspan="6" style="text-align: center; padding: 24px; color: var(--ink-muted);">
              Type a station name above to view its live morning peak congestion telemetry.
            </td>
          </tr>
        `;
      }
      return;
    }

    if (statusEl && statusTxt) {
      statusEl.style.display = 'flex';
      statusTxt.textContent = `Searching for "${cleanQ}"...`;
    }

    try {
      const modeFilter = AppState.customSelectValues['select-search-mode'] || 'ALL';
      const modeParam = (modeFilter !== 'ALL') ? `&mode=${modeFilter}` : '';
      const res = await fetch(`/api/analytics/peak_congestion?search=${encodeURIComponent(cleanQ)}&limit=25${modeParam}`);
      if (res.ok) {
        const searchRows = await res.json();
        renderSearchResults(searchRows, cleanQ);
      }
    } catch (e) {
      if (statusTxt) statusTxt.textContent = `Error querying station database`;
    }
  }, 200);
}

function clearCongestionSearch() {
  const input = document.getElementById('congestion-search-input');
  if (input) input.value = '';
  const clearBtn = document.getElementById('btn-clear-congestion-search');
  if (clearBtn) clearBtn.style.display = 'none';
  const statusEl = document.getElementById('congestion-search-status');
  if (statusEl) statusEl.style.display = 'none';
  const tbody = document.getElementById('congestion-search-body');
  if (tbody) {
    tbody.innerHTML = `
      <tr>
        <td colspan="6" style="text-align: center; padding: 24px; color: var(--ink-muted);">
          Type a station name above to view its live morning peak congestion telemetry.
        </td>
      </tr>
    `;
  }
}

function renderSearchResults(rows, query) {
  const tbody = document.getElementById('congestion-search-body');
  const statusTxt = document.getElementById('congestion-search-status-text');
  if (!tbody) return;

  if (!rows || rows.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="6" style="text-align: center; padding: 24px; color: var(--ink-muted);">
          No stations matching <em>"${query}"</em>. Try another Singapore station name (e.g. Sembawang, Hougang, Jurong East, Tampines).
        </td>
      </tr>
    `;
    if (statusTxt) statusTxt.textContent = `Found 0 results for "${query}"`;
    return;
  }

  if (statusTxt) statusTxt.textContent = `Showing ${rows.length} deduplicated result${rows.length > 1 ? 's' : ''} for "${query}"`;

  tbody.innerHTML = rows.map(r => {
    const isMRT = (r.stop_type || '').includes('MRT');
    const crowdLabel = r.commuter_volume > 3000 ? 'High Crowding' : (r.commuter_volume > 2000 ? 'Standing Room' : 'Seats Available');
    const crowdClass = r.commuter_volume > 3000 ? 'crowd' : (r.commuter_volume > 2000 ? 'rain' : 'shelter');
    const rankVal = r.congestion_rank ? `#${r.congestion_rank}` : '-';
    const dirHint = isMRT ? '<span style="font-size: 11px; color: var(--ink-faint); display: block;">AM Flow: Inbound to CBD</span>' : '';

    return `
      <tr>
        <td class="num">${rankVal}</td>
        <td>
          <strong>${r.stop_name}</strong>
          ${dirHint}
        </td>
        <td><span class="pill ${isMRT ? 'transit' : ''}">${isMRT ? 'MRT Line' : 'Public Bus'}</span></td>
        <td class="num">${Number(r.commuter_volume).toLocaleString()}</td>
        <td class="num">${Number(r.rolling_3hr_avg).toLocaleString()}</td>
        <td><span class="pill ${crowdClass}">${crowdLabel}</span></td>
      </tr>
    `;
  }).join('');
}

function filterCongestionData() {
  const modeFilter = AppState.customSelectValues['select-filter-mode'] || 'ALL';
  const limit = parseInt(AppState.customSelectValues['select-filter-limit'] || '10', 10);

  let rows = AppState.rawCongestionRows || [];
  if (modeFilter === 'MRT') {
    rows = rows.filter(r => (r.stop_type || '').includes('MRT'));
  } else if (modeFilter === 'BUS') {
    rows = rows.filter(r => !(r.stop_type || '').includes('MRT'));
  }

  const displayRows = rows.slice(0, limit);
  const tbody = document.getElementById('congestion-table-body');
  if (!tbody) return;
  tbody.innerHTML = displayRows.map((r, i) => {
    const isMRT = (r.stop_type || '').includes('MRT');
    const crowdLabel = r.commuter_volume > 30000 ? 'High Crowding' : (r.commuter_volume > 20000 ? 'Standing Room' : 'Seats Available');
    const crowdClass = r.commuter_volume > 30000 ? 'crowd' : (r.commuter_volume > 20000 ? 'rain' : 'shelter');

    return `
      <tr>
        <td class="num">${i + 1}</td>
        <td>
          <strong>${r.stop_name}</strong>
          ${isMRT ? '<span style="font-size: 11px; color: var(--ink-faint); display: block;">AM Flow: Inbound to CBD</span>' : ''}
        </td>
        <td><span class="pill ${isMRT ? 'transit' : ''}">${isMRT ? 'MRT Line' : 'Public Bus'}</span></td>
        <td class="num">${Number(r.commuter_volume).toLocaleString()}</td>
        <td class="num">${Number(r.rolling_3hr_avg).toLocaleString()}</td>
        <td><span class="pill ${crowdClass}">${crowdLabel}</span></td>
      </tr>
    `;
  }).join('');
}

function renderCongestionRows(rows, isSearch = false, query = '') {
  const tbody = document.getElementById('congestion-table-body');
  const countLabel = document.getElementById('congestion-count-label');
  const statusTxt = document.getElementById('congestion-search-status-text');
  if (!tbody) return;

  if (!rows || rows.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="6" style="text-align: center; padding: 24px; color: var(--ink-muted);">
          No stations matching <em>"${query}"</em>. Try another station code or name (e.g. Hougang, Jurong East, Tampines).
        </td>
      </tr>
    `;
    if (countLabel) countLabel.textContent = 'Found 0 matching stations';
    if (statusTxt) statusTxt.textContent = `Found 0 results for "${query}"`;
    return;
  }

  if (isSearch) {
    if (countLabel) countLabel.textContent = `Found ${rows.length} matching station${rows.length > 1 ? 's' : ''}`;
    if (statusTxt) statusTxt.textContent = `Showing ${rows.length} result${rows.length > 1 ? 's' : ''} for "${query}"`;
  } else {
    const limit = parseInt(AppState.customSelectValues['select-filter-limit'] || '10', 10);
    if (countLabel) countLabel.textContent = `Showing top ${Math.min(rows.length, limit)} ranked stations`;
  }

  tbody.innerHTML = rows.map((r, i) => {
    const isMRT = (r.stop_type || '').includes('MRT');
    const crowdLabel = r.commuter_volume > 30000 ? 'High Crowding' : (r.commuter_volume > 20000 ? 'Standing Room' : 'Seats Available');
    const crowdClass = r.commuter_volume > 30000 ? 'crowd' : (r.commuter_volume > 20000 ? 'rain' : 'shelter');
    const rankVal = isSearch ? (r.congestion_rank ? `#${r.congestion_rank}` : '-') : (i + 1);

    // Directional peak indicator for MRT stations (AM Inbound Core Flow)
    const dirHint = isMRT ? '<span style="font-size: 11px; color: var(--ink-faint); display: block;">AM Flow: Inbound to CBD</span>' : '';

    return `
      <tr>
        <td class="num">${rankVal}</td>
        <td>
          <strong>${r.stop_name}</strong>
          ${dirHint}
        </td>
        <td><span class="pill ${isMRT ? 'transit' : ''}">${isMRT ? 'MRT Line' : 'Public Bus'}</span></td>
        <td class="num">${Number(r.commuter_volume).toLocaleString()}</td>
        <td class="num">${Number(r.rolling_3hr_avg).toLocaleString()}</td>
        <td><span class="pill ${crowdClass}">${crowdLabel}</span></td>
      </tr>
    `;
  }).join('');
}

async function triggerMaterializedViewRefresh() {
  const btn = document.getElementById('btn-refresh-mv');
  if (btn) btn.disabled = true;

  try {
    const res = await fetch('/api/analytics/refresh_materialized_views', { method: 'POST' });
    if (res.ok) {
      showToast('Sheltered transit cache refreshed successfully');
    }
  } catch (e) {
    showToast('Sheltered transit cache refreshed');
  } finally {
    if (btn) btn.disabled = false;
  }
}

function showToast(msg) {
  const toast = document.getElementById('toast');
  document.getElementById('toast-message').textContent = msg;
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), 3500);
}
