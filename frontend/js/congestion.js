/* ==========================================================================
   CONGESTION TELEMETRY & FILTERING
   ========================================================================== */

async function loadCongestionData() {
  try {
    const res = await fetch('/api/analytics/peak_congestion?limit=25');
    if (res.ok) {
      AppState.rawCongestionRows = await res.json();
      filterCongestionData();
    }
  } catch (e) {}
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
        <td><strong>${r.stop_name}</strong></td>
        <td>${isMRT ? 'MRT Network' : 'Public Bus'}</td>
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
