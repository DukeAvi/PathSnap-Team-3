const geojson = JSON.parse(document.getElementById("trip-data").textContent);
const map = L.map("map", { preferCanvas: true, minZoom: 1, maxZoom: 20, scrollWheelZoom: false });
map.setView([0, 0], 2);
L.control.scale({ imperial: false }).addTo(map);

const styles = {
  network: { color: "#9ca49d", opacity: 0.9, weight: 1.25, interactive: false },
  reference: { color: "#ad5e07", opacity: 0.92, weight: 6, dashArray: "5 6" },
  matched: { color: "#007d76", opacity: 0.94, weight: 3 },
};
const labels = {
  network: "Road network",
  reference: "Reference route",
  matched: "Matched arcs",
  observations: "GPS points",
};
const data = Object.fromEntries(Object.keys(labels).map((name) => [name, []]));
for (const feature of geojson.features) data[feature.properties.layer].push(feature);
const overlays = {};
for (const [index, name] of Object.keys(labels).entries()) {
  if (!data[name].length) continue;
  const pane = map.createPane(name);
  pane.style.zIndex = 400 + index;
  const layer = L.geoJSON(data[name], {
    pane: name,
    style: () => ({ ...styles[name], pane: name }),
    pointToLayer: (feature, latlng) => L.circleMarker(latlng, {
      pane: name, color: "#f8fbff", weight: 1, radius: 4, fillOpacity: 0.92,
      fillColor: feature.properties.predicted_arc_id < 0 ? "#bb362b" : "#324e91",
    }),
    onEachFeature(feature, element) {
      if (name === "network") return;
      const props = feature.properties;
      const label = document.createElement("span");
      if (name === "observations") {
        const matched = props.predicted_arc_id < 0 ? "Unmatched" : `Arc ${props.predicted_arc_id}`;
        label.textContent = `Observation ${props.observation_id} · ${matched}`;
      } else {
        label.textContent = `${name === "matched" ? "Matched" : "Reference"} arc ${props.arc_id}`;
      }
      element.bindPopup(label);
    },
  });
  overlays[labels[name]] = layer;
  if (name !== "observations") layer.addTo(map);
}
L.control.layers({}, overlays, { collapsed: false }).addTo(map);
const bounds = overlays["GPS points"].getBounds();
map.fitBounds(bounds.pad(0.1), { maxZoom: 18 });
