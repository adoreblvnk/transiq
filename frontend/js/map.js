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
  if (!AppState.leafletMap || !route) return;

  AppState.mapLayers.forEach(l => AppState.leafletMap.removeLayer(l));
  AppState.mapLayers = [];

  // Draw active route with distinct multi-modal leg colors
  let activeBounds = null;
  if (route.steps && route.steps.length > 0) {
    route.steps.forEach(step => {
      if (!step.coordinates || step.coordinates.length < 2) return;
      let color = '#1D4ED8';
      let weight = 5;
      let dashArray = null;
      let opacity = 0.95;

      if (step.step_type === 'WALK') {
        if (step.is_sheltered) {
          color = '#0F6738';
          weight = 5;
        } else {
          color = '#D97706';
          weight = 4.5;
          dashArray = '5, 7';
        }
      } else if (step.step_type === 'TRANSIT') {
        if (step.transit_mode === 'BUS') {
          color = '#7C3AED';
          weight = 5;
        } else {
          color = '#1D4ED8';
          weight = 6;
        }
      } else if (step.step_type === 'TRANSFER') {
        color = '#475569';
        weight = 3.5;
        dashArray = '4, 4';
      }

      const legPoly = L.polyline(step.coordinates, {
        color: color,
        weight: weight,
        opacity: opacity,
        dashArray: dashArray
      }).addTo(AppState.leafletMap);

      const modeTitle = step.transit_mode || step.step_type;
      const svcInfo = step.service ? ` [${step.service}]` : '';
      const shBadge = step.is_sheltered ? '☂ Sheltered' : '☀ Unsheltered';
      legPoly.bindTooltip(`<strong>${modeTitle}${svcInfo}</strong><br>${step.from_name} → ${step.to_name}<br>${Math.round(step.distance_m || 0)}m &bull; ${step.duration_min} min &bull; ${shBadge}`, { sticky: true });

      AppState.mapLayers.push(legPoly);
      if (!activeBounds) {
        activeBounds = legPoly.getBounds();
      } else {
        activeBounds.extend(legPoly.getBounds());
      }
    });
  }

  // Fallback if steps had no individual coordinates
  if (!activeBounds && route.coordinates && route.coordinates.length > 0) {
    const poly = L.polyline(route.coordinates, {
      color: route.unsheltered_m === 0 ? '#0F6738' : '#1D4ED8',
      weight: 5,
      opacity: 0.95
    }).addTo(AppState.leafletMap);
    AppState.mapLayers.push(poly);
    activeBounds = poly.getBounds();
  }

  // 3. Add origin and destination markers
  if (route.coordinates && route.coordinates.length > 0) {
    const startCoord = route.coordinates[0];
    const endCoord = route.coordinates[route.coordinates.length - 1];

    const startMarker = L.circleMarker(startCoord, {
      radius: 7,
      fillColor: '#111827',
      color: '#FFFFFF',
      weight: 2,
      fillOpacity: 1
    }).addTo(AppState.leafletMap).bindPopup(`<strong>Origin:</strong> ${AppState.originText}`);
    AppState.mapLayers.push(startMarker);

    const endMarker = L.circleMarker(endCoord, {
      radius: 8,
      fillColor: '#9A3412',
      color: '#FFFFFF',
      weight: 2,
      fillOpacity: 1
    }).addTo(AppState.leafletMap).bindPopup(`<strong>Destination:</strong> ${AppState.destText}`);
    AppState.mapLayers.push(endMarker);
  }

  if (activeBounds && activeBounds.isValid()) {
    AppState.leafletMap.fitBounds(activeBounds, { padding: [40, 40] });
  }
}
