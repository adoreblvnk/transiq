/* ==========================================================================
   TRANSIQ GLOBAL STATE & UTILITIES
   ========================================================================== */

const AppState = {
  activeMode: 'FASTEST', // Default mode as requested: Fastest
  originText: 'COMPASSVALE CAPE (543287)',
  originPostal: '543287',
  destText: 'QUEENSWAY SHOPPING CENTRE (149053)',
  destPostal: '149053',
  currentRoute: null,
  allRoutes: [],
  activeRouteIndex: 0,
  leafletMap: null,
  mapLayers: [],
  rawCongestionRows: [],
  customSelectValues: {
    'select-filter-mode': 'ALL',
    'select-filter-limit': '10',
    'select-durability-mode': 'async',
    'select-durability-batch': '500'
  },
  lastFocusedElement: null
};

function formatDuration(mins) {
  if (mins >= 60) {
    const h = Math.floor(mins / 60);
    const m = mins % 60;
    return m > 0 ? `${h} hr ${m} mins` : `${h} hr`;
  }
  return `${mins} min`;
}

function extractPostal(str) {
  const match = (str || '').match(/\b\d{6}\b/);
  return match ? match[0] : null;
}

function escapeStr(str) {
  return (str || '').replace(/'/g, "\\'");
}
