const map = L.map("map", { preferCanvas: true, zoomSnap: 0.25, minZoom: 1, maxZoom: 20, scrollWheelZoom: false });
map.setView([0, 0], 2);
L.control.scale({ imperial: false }).addTo(map);

const mapNode = document.getElementById("map");
new ResizeObserver(() => map.invalidateSize({ pan: false, debounceMoveend: true })).observe(mapNode);

const basemapControl = document.getElementById("layer-basemap");
const basemapNote = document.getElementById("basemap-note");
const basemap = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>',
  maxNativeZoom: 19,
  maxZoom: 20,
  updateWhenIdle: true,
  opacity: 0.9,
});
let tileFailed = false;
let tileLoaded = false;

function setBasemapNote(message = "") {
  basemapNote.textContent = message;
  basemapNote.hidden = !message;
}

basemap.on("loading", () => {
  tileFailed = false;
  tileLoaded = false;
  setBasemapNote();
});
basemap.on("tileerror", () => { tileFailed = true; });
basemap.on("tileload", () => { tileLoaded = true; });
basemap.on("load", () => {
  if (!tileFailed) return;
  setBasemapNote(tileLoaded
    ? "Some street tiles could not load. The trip layers are available."
    : "Street tiles could not load. The trip layers are available.");
});
basemapControl.addEventListener("change", () => {
  if (basemapControl.checked) basemap.addTo(map);
  else {
    basemap.remove();
    setBasemapNote();
  }
});

const styles = {
  network: { color: "#9ca49d", opacity: 0.9, weight: 1.25, interactive: false },
  reference: { color: "#ad5e07", opacity: 0.95, weight: 7, dashArray: "5 7" },
  matched: { color: "#007d76", opacity: 0.92, weight: 3 },
};
const names = ["network", "reference", "matched", "observations"];
const layers = {};
const observationMarkers = new Map();
for (const [index, name] of names.entries()) {
  const pane = map.createPane(name);
  pane.style.zIndex = 400 + index;
  layers[name] = L.geoJSON(null, {
    pane: name,
    style: () => ({ ...styles[name], pane: name }),
    pointToLayer: (feature, latlng) => L.circleMarker(latlng, {
      pane: name, color: "#f8fbff", weight: 1, radius: 4,
      fillColor: feature.properties.predicted_arc_id < 0 ? "#bb362b" : "#324e91",
      fillOpacity: 0.92,
    }),
    onEachFeature(feature, layer) {
      const p = feature.properties;
      if (name === "network") return;
      const label = document.createElement("span");
      if (name === "observations") {
        observationMarkers.set(p.observation_id, layer);
        label.textContent = `Observation ${p.observation_id} · ${p.predicted_arc_id < 0 ? "Unmatched" : `Arc ${p.predicted_arc_id}`}`;
      } else {
        label.textContent = `${name === "matched" ? "Matched" : "Reference"} arc ${p.arc_id}`;
      }
      layer.bindPopup(label, { maxWidth: 240 });
    },
  });
  const checkbox = document.querySelector(`#layer-${name}`);
  if (checkbox.checked) layers[name].addTo(map);
  checkbox.addEventListener("change", (event) => {
    if (event.target.checked) layers[name].addTo(map);
    else layers[name].remove();
  });
}

export function fitTrack() {
  const bounds = layers.observations.getBounds();
  if (bounds.isValid()) map.fitBounds(bounds.pad(0.12), { maxZoom: 18, animate: false });
}

export function clearMap() {
  map.closePopup();
  basemap.remove();
  basemapControl.checked = false;
  basemapControl.disabled = true;
  setBasemapNote();
  observationMarkers.clear();
  for (const name of names) {
    layers[name].clearLayers();
    document.getElementById(`layer-${name}`).disabled = true;
  }
}

export function setMap(data, demoRoads) {
  clearMap();
  const features = Object.fromEntries(names.map((name) => [name, []]));
  for (const feature of data.features) features[feature.properties.layer].push(feature);
  if (demoRoads?.coordinates.length) {
    features.network = [{ type: "Feature", geometry: demoRoads, properties: { layer: "network" } }];
    document.getElementById("layer-network").checked = true;
    layers.network.addTo(map);
  }
  for (const name of names) {
    layers[name].addData(features[name]);
    document.getElementById(`layer-${name}`).disabled = !features[name].length;
  }
  map.invalidateSize({ pan: false });
  fitTrack();
  basemapControl.disabled = false;
}

export function focusObservation(id) {
  const marker = observationMarkers.get(id);
  if (!marker) return;
  document.querySelector("#layer-observations").checked = true;
  layers.observations.addTo(map);
  map.setView(marker.getLatLng(), Math.max(16, map.getZoom()), { animate: false });
  marker.openPopup();
}

clearMap();
