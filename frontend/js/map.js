/* ==========================================================================
   LEAFLET MAP CONTROLLER (SLA OneMap Tiles & Route Polylines)
   ========================================================================== */

function initMap() {
  const mapEl = document.getElementById('leaflet-map');
  if (!mapEl || typeof L === 'undefined') return;

  AppState.leafletMap = L.map('leaflet-map', {
    center: [1.3440, 103.7100],
    zoom: 14,
    zoomControl: true
  });

  // Position zoom controls cleanly at bottom-left avoiding telemetry collision
  AppState.leafletMap.zoomControl.setPosition('bottomleft');

  L.tileLayer('https://www.onemap.gov.sg/maps/tiles/Default/{z}/{x}/{y}.png', {
    attribution: '&copy; <a href="https://www.onemap.gov.sg" target="_blank" rel="noopener">OneMap</a> &copy; Singapore Land Authority',
    maxZoom: 19
  }).addTo(AppState.leafletMap);
}

function renderMap(route) {
  if (!AppState.leafletMap || !route.coordinates || route.coordinates.length === 0) return;

  AppState.mapLayers.forEach(l => AppState.leafletMap.removeLayer(l));
  AppState.mapLayers = [];

  const coords = route.coordinates;

  const poly = L.polyline(coords, {
    color: route.unsheltered_m === 0 ? '#0F6738' : '#1D4ED8',
    weight: 5,
    opacity: 0.95
  }).addTo(AppState.leafletMap);
  AppState.mapLayers.push(poly);

  const startMarker = L.circleMarker(coords[0], {
    radius: 7,
    fillColor: '#111827',
    color: '#FFFFFF',
    weight: 2,
    fillOpacity: 1
  }).addTo(AppState.leafletMap).bindPopup(`<strong>Origin:</strong> ${AppState.originText}`);
  AppState.mapLayers.push(startMarker);

  const endMarker = L.circleMarker(coords[coords.length - 1], {
    radius: 8,
    fillColor: '#9A3412',
    color: '#FFFFFF',
    weight: 2,
    fillOpacity: 1
  }).addTo(AppState.leafletMap).bindPopup(`<strong>Destination:</strong> ${AppState.destText}`);
  AppState.mapLayers.push(endMarker);

  AppState.leafletMap.fitBounds(poly.getBounds(), { padding: [40, 40] });
}
