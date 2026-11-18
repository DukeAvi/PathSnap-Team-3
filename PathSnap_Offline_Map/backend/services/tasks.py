"""Build and evaluate a single trip job."""
import hashlib
import time

from backend.services.demo import frozen_trip
from backend.services.evaluation import summarize, weak_reference
from backend.services.exports import save_result
from backend.services.features import FEATURES, augment
from backend.services.geometry import make_geojson
from backend.services.graph import build_lattice, lattice_key
from backend.services.inference import decode
from backend.services.input_loader import read_trip_directory
from backend.services.preprocessing import generate_candidates, project


def run_trip(path, task, model, settings):
    start = time.perf_counter()
    trip_id = task["trip_id"]
    mode = task["source"]
    raw_path = settings.demo_dir / "networks" / trip_id if mode == "demo" else path
    if mode == "demo":
        for name, digest in task["demo"]["network_files"].items():
            with (raw_path / name).open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != digest:
                    raise ValueError(f"Demo {trip_id}: file checksum mismatch ({name})")
    raw = read_trip_directory(raw_path, trip_id, settings)
    observations = raw.observations
    gps, network = project(observations, raw.nodes, raw.arcs)
    if mode == "demo":
        observations, candidates, lattice = frozen_trip(settings.demo_dir, trip_id)
    else:
        candidates = augment(generate_candidates(observations, gps, network,
                                                 settings.max_spatial_pairs),
                             observations, raw.nodes, raw.arcs)
        lattice = build_lattice(observations, candidates, gps, network, model.decoder)
    key = lattice_key(observations, candidates, raw.nodes, raw.arcs, model.decoder)
    if mode == "demo" and key != task["demo"]["lattice_key"]:
        raise ValueError(f"Demo {trip_id}: cached lattice inputs changed. Re-run prepare_demo.")
    preparation_seconds = time.perf_counter() - start
    start = time.perf_counter()
    probability = model.probabilities(candidates[FEATURES])
    emission_seconds = time.perf_counter() - start
    start = time.perf_counter()
    predictions = decode(observations, candidates, probability, [lattice], model.decoder)
    decoder_seconds = time.perf_counter() - start
    reference = (weak_reference(observations, gps, network, raw.route, settings.max_spatial_pairs)
                 if raw.route is not None else None)
    result, summary = summarize(predictions, candidates, lattice, reference)
    geojson = make_geojson(result, raw.nodes, raw.arcs, raw.route, candidates,
                           settings.max_display_arcs)
    summary.update(trip_id=trip_id, source=mode, cleaning=task.get("cleaning", raw.cleaning),
                   projection_epsg=network.epsg, zero_length_arcs=len(raw.arcs) - len(network.active_ids),
                   network=geojson["network"], lattice_key=key,
                   timings={"preparation_s": preparation_seconds, "emissions_s": emission_seconds,
                            "decoder_s": decoder_seconds})
    if raw.route is not None:
        summary["route"] = {"entries": len(raw.route), "disconnected_pairs": int(
            (raw.arcs[raw.route[:-1], 1] != raw.arcs[raw.route[1:], 0]).sum())}
    save_result(path, result, summary, geojson)
