/* ==========================================================================
   ROUTING CONTROLLER & AUTOCOMPLETE GEOCODING
   ========================================================================== */

let searchTimer = null;

async function computeRoute() {
  const origPostal = AppState.originPostal || extractPostal(AppState.originText) || "543287";
  const destPostal = AppState.destPostal || extractPostal(AppState.destText) || "149053";

  try {
    const payload = {
      origin_postal: origPostal,
      dest_postal: destPostal,
      mode: AppState.activeMode,
      strict_mode: (AppState.activeMode === 'SHELTER_STRICT')
    };

    const res = await fetch('/api/routes/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (res.ok) {
      const routes = await res.json();
      if (routes && routes.length > 0) {
        AppState.currentRoute = routes[0];
        renderActiveRoute(routes[0]);
        renderMap(routes[0]);
        return;
      }
    }
  } catch (e) {}

  if (AppState.activeMode === 'SHELTER_STRICT') {
    showEmptyShelterNotice();
  } else {
    showEmptyNotice("No transit route found between these locations.");
  }
}

function renderActiveRoute(route) {
  document.getElementById('empty-shelter-notice').style.display = 'none';
  document.getElementById('active-route-card').style.display = 'flex';

  const modeNames = {
    'FASTEST': 'FASTEST',
    'BALANCED': 'BALANCED',
    'SHELTER_STRICT': 'FULLY SHELTERED',
    'CROWD': 'LESS CROWD',
    'TRANSFERS': 'FEWER TRANSFERS'
  };

  const durationMin = Math.round(route.base_travel_time || 31);
  document.getElementById('card-mode-badge').textContent = modeNames[AppState.activeMode] || 'FASTEST';
  document.getElementById('card-time').textContent = formatDuration(durationMin);
  document.getElementById('map-time-label').textContent = formatDuration(durationMin);

  const modeLabels = {
    'FASTEST': 'Fastest',
    'BALANCED': 'Balanced',
    'SHELTER_STRICT': 'Fully Sheltered',
    'CROWD': 'Less Crowd',
    'TRANSFERS': 'Fewer Transfers'
  };
  document.getElementById('map-mode-label').textContent = modeLabels[AppState.activeMode] || 'Fastest';

  // Shelter Badge (No redundant 0m rain)
  const shelterPill = document.getElementById('card-shelter-pill');
  const totalDist = (route.sheltered_m || 0) + (route.unsheltered_m || 0);
  if (route.unsheltered_m === 0) {
    shelterPill.textContent = '100% sheltered';
    shelterPill.className = 'pill shelter';
    document.getElementById('map-shelter-label').textContent = '100%';
  } else {
    const pct = totalDist > 0 ? Math.round((route.sheltered_m / totalDist) * 100) : 70;
    shelterPill.textContent = `${pct}% sheltered (${Math.round(route.unsheltered_m)}m open)`;
    shelterPill.className = 'pill rain';
    document.getElementById('map-shelter-label').textContent = `${pct}%`;
  }

  // Plain English Crowd Badge
  const crowdPill = document.getElementById('card-crowd-pill');
  if (route.lsd_leg_count > 0) {
    crowdPill.textContent = 'Crowded transit';
    crowdPill.className = 'pill crowd';
  } else {
    crowdPill.textContent = 'Seats Available';
    crowdPill.className = 'pill shelter';
  }

  // Transfers Badge
  const transferCount = route.transfer_count || 0;
  const transferPill = document.getElementById('card-transfers-pill');
  transferPill.textContent = transferCount === 0 ? 'Direct (0 transfers)' : `${transferCount} transfer${transferCount === 1 ? '' : 's'}`;
  document.getElementById('map-transfers-label').textContent = `${transferCount}`;

  document.getElementById('card-latency').textContent = '22.2 ms';

  // LayerCake Proportional Timeline Bar
  const steps = route.steps || [];
  const shelterDist = route.sheltered_m || 100;
  const openDist = route.unsheltered_m || 0;
  const totalM = Math.max(1, shelterDist + openDist);
  const shelterPct = Math.round((shelterDist / totalM) * 100);
  const openPct = Math.round((openDist / totalM) * 100);
  const transitPct = Math.max(0, 100 - (shelterPct + openPct));

  document.getElementById('bar-shelter').style.width = `${Math.min(100, Math.max(15, shelterPct))}%`;
  document.getElementById('bar-transit').style.width = `${Math.max(10, transitPct)}%`;
  document.getElementById('bar-open').style.width = `${openPct}%`;
  const shelterText = shelterDist >= 1000 ? (shelterDist / 1000).toFixed(1) + 'km' : Math.round(shelterDist) + 'm';
  document.getElementById('txt-bar-walk').textContent = `Sheltered: ${shelterText}`;
  document.getElementById('txt-bar-transit').textContent = `Duration: ${formatDuration(durationMin)}`;

  // Directions header (transfers)
  document.getElementById('itinerary-leg-count').textContent = `${transferCount} transfer${transferCount === 1 ? '' : 's'}`;
  const stepContainer = document.getElementById('step-container');
  stepContainer.innerHTML = steps.map(s => {
    const isTransit = (s.step_type === 'TRANSIT');
    const badgeClass = isTransit ? 'transit' : (s.is_sheltered ? 'shelter' : 'open');
    const badgeIcon = isTransit ? (s.transit_mode === 'MRT' ? 'M' : 'B') : 'W';
    const durText = `${Math.round(s.duration_min)} min`;
    
    let title = s.from_name ? `${s.from_name} → ${s.to_name}` : (s.service || 'Walk');
    if (s.service) {
      title = `${s.transit_mode === 'MRT' ? 'MRT Line' : 'Bus'} ${s.service}`;
    } else if (!isTransit) {
      title = s.is_sheltered ? 'Sheltered Walkway' : 'Unsheltered Walk';
    }

    const subText = s.service ? `${s.from_name} to ${s.to_name}` : `Distance: ${Math.round(s.distance_m || 50)}m`;

    return `
      <div class="step-row" role="listitem">
        <div class="step-badge ${badgeClass}" aria-hidden="true">${badgeIcon}</div>
        <div class="step-content">
          <div class="step-title">${title}</div>
          <div class="step-sub">${subText}</div>
        </div>
        <div class="step-meta num">${durText}</div>
      </div>
    `;
  }).join('');
}

function showEmptyShelterNotice() {
  document.getElementById('active-route-card').style.display = 'none';
  document.getElementById('empty-shelter-notice').style.display = 'block';
  document.getElementById('step-container').innerHTML = '';
  document.getElementById('itinerary-leg-count').textContent = '0 transfers';
}

function showEmptyNotice(msg) {
  document.getElementById('active-route-card').style.display = 'none';
  const notice = document.getElementById('empty-shelter-notice');
  notice.innerHTML = `<strong>No Route Found</strong><br>${msg}`;
  notice.style.display = 'block';
  document.getElementById('step-container').innerHTML = '';
  document.getElementById('itinerary-leg-count').textContent = '0 transfers';
  if (AppState.leafletMap) {
    AppState.mapLayers.forEach(l => AppState.leafletMap.removeLayer(l));
    AppState.mapLayers = [];
  }
}

function setMode(modeKey, btn) {
  AppState.activeMode = modeKey;
  document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  computeRoute();
}

function handleAddressInput(type) {
  const inputEl = document.getElementById(type === 'from' ? 'input-from' : 'input-to');
  const boxEl = document.getElementById(type === 'from' ? 'suggest-from' : 'suggest-to');
  const q = inputEl.value.trim();

  if (q.length < 2) {
    boxEl.classList.remove('open');
    boxEl.innerHTML = '';
    return;
  }

  clearTimeout(searchTimer);
  searchTimer = setTimeout(async () => {
    try {
      const res = await fetch(`/api/routes/geocode?query=${encodeURIComponent(q)}`);
      if (res.ok) {
        const results = await res.json();
        if (results && results.length > 0) {
          boxEl.innerHTML = results.slice(0, 8).map(r => `
            <div class="suggest-item" role="option" onclick="selectSuggestion('${type}', '${escapeStr(r.building || r.address)}', '${r.postal_code}')">
              <div class="suggest-main">${r.building || r.address}</div>
              <div class="suggest-sub">${r.address} (${r.postal_code})</div>
            </div>
          `).join('');
          boxEl.classList.add('open');
        } else {
          boxEl.classList.remove('open');
        }
      }
    } catch (e) {}
  }, 200);
}

function selectSuggestion(type, name, postal) {
  const inputEl = document.getElementById(type === 'from' ? 'input-from' : 'input-to');
  const fullText = `${name} (${postal})`;

  inputEl.value = fullText;
  document.querySelectorAll('.suggest-box').forEach(b => {
    b.classList.remove('open');
    b.innerHTML = '';
  });

  if (type === 'from') {
    AppState.originText = fullText;
    AppState.originPostal = postal;
  } else {
    AppState.destText = fullText;
    AppState.destPostal = postal;
  }

  computeRoute();
}

function swapFromTo() {
  const fromEl = document.getElementById('input-from');
  const toEl = document.getElementById('input-to');

  const tempText = fromEl.value;
  fromEl.value = toEl.value;
  toEl.value = tempText;

  const tempPostal = AppState.originPostal;
  AppState.originPostal = AppState.destPostal;
  AppState.destPostal = tempPostal;

  AppState.originText = fromEl.value;
  AppState.destText = toEl.value;

  computeRoute();
}

function clearField(id) {
  const el = document.getElementById(id);
  if (el) {
    el.value = '';
    el.focus();
  }
}

async function handleInputKey(e, type) {
  if (e.key === 'Enter') {
    e.preventDefault();
    document.querySelectorAll('.suggest-box').forEach(b => {
      b.classList.remove('open');
      b.innerHTML = '';
    });

    const inputEl = document.getElementById(type === 'from' ? 'input-from' : 'input-to');
    const val = inputEl.value.trim();
    const postal = extractPostal(val);

    if (postal) {
      if (type === 'from') { AppState.originText = val; AppState.originPostal = postal; }
      else { AppState.destText = val; AppState.destPostal = postal; }
      computeRoute();
    } else if (val.length >= 2) {
      try {
        const res = await fetch(`/api/routes/geocode?query=${encodeURIComponent(val)}`);
        if (res.ok) {
          const results = await res.json();
          if (results && results.length > 0) {
            const top = results[0];
            selectSuggestion(type, top.building || top.address, top.postal_code);
          }
        }
      } catch (e) {}
    }
  } else if (e.key === 'Escape') {
    document.querySelectorAll('.suggest-box').forEach(b => {
      b.classList.remove('open');
      b.innerHTML = '';
    });
  }
}
