/* ==========================================================================
   APP INITIALIZATION & GLOBAL NAVIGATION LISTENERS
   ========================================================================== */

window.addEventListener('DOMContentLoaded', () => {
  initMap();
  loadCongestionData();
  computeRoute();
});

function switchPage(pageId, btn) {
  document.querySelectorAll('.page-pane').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-tab').forEach(b => {
    b.classList.remove('active');
    b.setAttribute('aria-selected', 'false');
  });

  const target = document.getElementById('pane-' + pageId);
  if (target) target.classList.add('active');

  if (btn) {
    btn.classList.add('active');
    btn.setAttribute('aria-selected', 'true');
  }

  if (pageId === 'router' && AppState.leafletMap) {
    setTimeout(() => AppState.leafletMap.invalidateSize(), 50);
  }
}

function setMobileView(view) {
  const router = document.getElementById('pane-router');
  const btnItin = document.getElementById('btn-show-itinerary');
  const btnMap = document.getElementById('btn-show-map');

  if (view === 'map') {
    router.classList.add('show-map');
    btnMap.classList.add('active');
    btnItin.classList.remove('active');
    if (AppState.leafletMap) {
      setTimeout(() => AppState.leafletMap.invalidateSize(), 100);
    }
  } else {
    router.classList.remove('show-map');
    btnItin.classList.add('active');
    btnMap.classList.remove('active');
  }
}

function toggleCustomSelect(selectId) {
  const el = document.getElementById(selectId);
  const wasOpen = el.classList.contains('open');
  document.querySelectorAll('.custom-select').forEach(s => s.classList.remove('open'));
  if (!wasOpen) el.classList.add('open');
}

function selectCustomOption(selectId, value, label) {
  AppState.customSelectValues[selectId] = value;
  const el = document.getElementById(selectId);
  el.classList.remove('open');

  const triggerLabel = el.querySelector('.custom-select-trigger span');
  if (triggerLabel) triggerLabel.textContent = label;

  el.querySelectorAll('.custom-select-option').forEach(opt => {
    opt.classList.toggle('selected', opt.textContent.trim() === label.trim());
  });

  if (selectId === 'select-filter-mode' || selectId === 'select-filter-limit') {
    filterCongestionData();
  }
}

document.addEventListener('keydown', (e) => {
  const modal = document.getElementById('queryModal');
  if (modal && modal.classList.contains('open')) {
    if (e.key === 'Escape') closeModal();
  }
});
