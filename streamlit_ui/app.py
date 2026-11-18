"""Streamlit evaluator for the same frozen PathSnap inference pipeline."""
import json
from pathlib import Path
import re
from shutil import copyfileobj
import sys
from tempfile import TemporaryDirectory
from threading import Lock

import pandas as pd
import streamlit as st

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.schemas import TRIP_ID
from backend.services.demo import validate_frozen_files
from backend.services.exports import DOWNLOADS
from backend.services.input_loader import InputError
from backend.services.model_loader import FrozenModel, read_json
from backend.services.tasks import run_trip
from backend.settings import Settings


@st.cache_resource(show_spinner="Loading the frozen PathSnap model…")
def resources():
    settings = Settings()
    model = FrozenModel.load(settings.artifacts_dir)
    manifest = settings.demo_dir / "manifest.json"
    demos = read_json(manifest) if manifest.is_file() else {}
    if demos:
        validate_frozen_files(settings.demo_dir,
                              read_json(settings.artifacts_dir / "provenance" / "SHA256SUMS.json"))
    vendor = settings.frontend_dir / "vendor"
    leaflet_css = (vendor / "leaflet.css").read_text(encoding="utf-8")
    leaflet_js = (vendor / "leaflet.js").read_text(encoding="utf-8")
    map_js = (HERE / "map.js").read_text(encoding="utf-8")
    return settings, model, demos, Lock(), (leaflet_css, leaflet_js, map_js)


def evaluate(task, uploads=None):
    settings, model, _, lock, _ = resources()
    if not lock.acquire(blocking=False):
        raise InputError("A trip is already running. Submit again when it finishes.", "queue_full", 429)
    try:
        with TemporaryDirectory(prefix="pathsnap-") as temp:
            directory = Path(temp)
            for name, source in (uploads or {}).items():
                if source is None:
                    continue
                if source.size > settings.max_file_bytes:
                    raise InputError(f"{name}: file exceeds {settings.max_file_bytes:,} bytes")
                source.seek(0)
                with (directory / name).open("wb") as target:
                    copyfileobj(source, target)
            run_trip(directory, task, model, settings)
            return {kind: (directory / filename).read_bytes()
                    for kind, (filename, _) in DOWNLOADS.items()}
    finally:
        lock.release()


def map_html(geojson, assets):
    leaflet_css, leaflet_js, map_js = assets
    # JSON is encoded as data. Escaping "<" keeps it inside the script element.
    data = json.dumps(geojson, separators=(",", ":")).replace("<", r"\u003c")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Trip map</title>
<style>{leaflet_css}
html, body {{ margin: 0; padding: 0; }}
#map {{
  width: 100%; height: 460px; background-color: #f3f4ee;
}}
</style></head><body>
<div id="map" aria-label="Trip map"></div>
<script id="trip-data" type="application/json">{data}</script>
<script>{leaflet_js}</script>
<script>{map_js}</script>
</body></html>"""


def run_and_display(task, uploads=None):
    try:
        with st.spinner("Matching GPS observations to the road network…"):
            st.session_state["run"] = evaluate(task, uploads)
    except ValueError as error:
        st.error(str(error))


def trip_form(demos, model):
    benchmark = model.metrics
    with st.sidebar:
        st.header("Run a trip")
        source = st.radio("Trip source", ["Bundled demo", "Upload trip"] if demos else ["Upload trip"])
        if source == "Bundled demo":
            with st.form("demo"):
                trip = st.selectbox("Held-out trip", demos,
                                    format_func=lambda key: f"{key} · {demos[key]['observations']:,} points")
                if st.form_submit_button("Run demo", type="primary"):
                    run_and_display({"trip_id": trip, "source": "demo", "demo": demos[trip]})
        else:
            with st.form("upload"):
                trip = st.text_input("Trip ID", max_chars=64, placeholder="trip-01")
                track = st.file_uploader("GPS track")
                nodes = st.file_uploader("Network nodes")
                arcs = st.file_uploader("Directed arcs")
                route = st.file_uploader("Reference route (optional)")
                if st.form_submit_button("Run map matching", type="primary"):
                    if not re.fullmatch(TRIP_ID, trip):
                        st.error("Enter a trip ID beginning with a letter or digit. Use letters, digits, dots, hyphens, or underscores.")
                    elif any(item is None for item in (track, nodes, arcs)):
                        st.error("Choose a track, nodes, and arcs file.")
                    else:
                        run_and_display({"trip_id": trip, "source": "upload"},
                                        dict(track=track, nodes=nodes, arcs=arcs, route=route))
        st.divider()
        st.metric("Frozen benchmark", f"{benchmark['test_top1_accuracy']:.2%}")
        st.caption(f"{benchmark['correct_observations']:,} of {benchmark['total_observations']:,} "
                   "held-out observations agree with weak reference labels.")


def results(assets):
    files = st.session_state.get("run")
    if not files:
        st.info("Select a bundled demo and run it, or upload a GPS track and its road network.")
        return
    result = json.loads(files["json"])
    summary = result["summary"]
    agreement = summary["reference_agreement"]
    st.header(f"Trip {summary['trip_id']}")
    observations, matched, weak_reference, continuity = st.columns(4)
    observations.metric("GPS observations", f"{summary['observations']:,}")
    matched.metric("Matched", f"{summary['matched']:,}")
    matched.caption(f"{summary['unmatched']:,} unmatched")
    weak_reference.metric("Weak-reference agreement", f"{agreement['fraction']:.2%}" if agreement else "—")
    if agreement:
        weak_reference.caption(f"{agreement['correct']:,} of {agreement['total']:,} observations")
    else:
        weak_reference.caption("No reference route supplied")
    continuity.metric("Route continuity", f"{summary['route_continuity']:.2%}")
    continuity.caption(f"{summary['continuous_pairs']:,} of {summary['continuity_pair_count']:,} consecutive pairs")

    st.subheader("Trip map")
    geojson = json.loads(files["geojson"])
    if summary["source"] == "demo":
        basemap_path = ROOT / "frontend" / "demo-maps" / f"{summary['trip_id']}.geojson"
        if basemap_path.is_file():
            basemap = read_json(basemap_path)
            geojson["features"] = [feature for feature in geojson["features"]
                                   if feature["properties"]["layer"] != "network"]
            geojson["features"].append({"type": "Feature", "geometry": basemap,
                                       "properties": {"layer": "network"}})
            st.caption(f"{len(basemap['coordinates']):,} road segments in the built-in map.")
    elif summary["network"]["partial"]:
        st.caption(f"Displaying {summary['network']['displayed_arcs']:,} nearby road arcs.")
    st.iframe(map_html(geojson, assets), height=462)

    st.subheader("Observations")
    frame = pd.DataFrame(result["observations"])
    filters = {"All observations": frame, "Unmatched": frame.loc[frame.predicted_arc_id < 0],
               "Decoder events": frame.loc[frame.decoder_event != ""]}
    if agreement:
        filters["Reference disagreements"] = frame.loc[~frame.correct]
    selection = st.selectbox("Show observations", list(filters))
    st.dataframe(filters[selection], hide_index=True, width="stretch")
    with st.expander("Cleaning, network, and decoder details"):
        st.json({key: summary[key] for key in ("cleaning", "projection_epsg", "zero_length_arcs",
                                                "network", "decoder_events", "timings")})

    st.subheader("Download results")
    for column, (kind, (filename, mime)) in zip(st.columns(3), DOWNLOADS.items(), strict=True):
        column.download_button("GeoJSON" if kind == "geojson" else kind.upper(), files[kind],
                               file_name=filename, mime=mime, on_click="ignore")


def main():
    st.set_page_config(page_title="PathSnap Trip Evaluator", layout="wide")
    st.title("PathSnap Trip Evaluator")
    _, model, demos, _, assets = resources()
    trip_form(demos, model)
    results(assets)


if __name__ == "__main__":
    main()
