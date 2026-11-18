"""Bind the ten frozen demo trips to verified raw networks and routes."""
import argparse
from pathlib import Path
import re
from shutil import copyfile

import numpy as np
import pandas as pd

from backend.services.demo import DEMO_IDS, frozen_inputs, frozen_trip
from backend.services.evaluation import weak_reference
from backend.services.exports import write_json
from backend.services.features import FEATURES, augment
from backend.services.graph import build_lattice, lattice_key
from backend.services.inference import OBS_COLUMNS
from backend.services.input_loader import read_trip_directory
from backend.services.model_loader import FrozenModel
from backend.services.preprocessing import generate_candidates, project
from backend.settings import ROOT, Settings
from scripts.import_bundle import digest

REFERENCE_COLUMNS = ["observation_id", "reference_arc_id", "reference_distance_m",
                     "reference_route_position", "reference_progress_m", "reference_tie"]


def prepare(source, root=ROOT):
    raw_root = next((p for p in (source, source / "student_test",
                               source / "Student folder" / "student_test")
                    if all((p / trip).is_dir() for trip in DEMO_IDS)), None)
    if raw_root is None:
        raise ValueError("Supply Student folder, its parent, or its student_test directory with ten test trips")
    model = FrozenModel.load(root / "artifacts")
    demo = root / "data" / "demo"
    ledger, _ = frozen_inputs(demo)
    settings = Settings()
    manifest = {}
    for trip in DEMO_IDS:
        if not re.fullmatch(r"\d{8}", trip):
            raise ValueError(f"Invalid frozen trip ID {trip}")
        raw_dir = raw_root / trip
        raw = read_trip_directory(raw_dir, trip, settings, stem=trip)
        if raw.route is None:
            raise ValueError(f"Demo {trip} requires a matching .route")
        obs, expected, cached = frozen_trip(demo, trip)
        raw.observations["observation_id"] = obs.observation_id
        pd.testing.assert_frame_equal(raw.observations[OBS_COLUMNS], obs[OBS_COLUMNS])
        gps, network = project(obs, raw.nodes, raw.arcs)
        candidates = augment(generate_candidates(obs, gps, network, settings.max_spatial_pairs),
                             obs, raw.nodes, raw.arcs)
        pd.testing.assert_frame_equal(candidates[["observation_id", "arc_id", "trip_id"]],
                                      expected[["observation_id", "arc_id", "trip_id"]])
        np.testing.assert_allclose(candidates[FEATURES], expected[FEATURES], rtol=1e-6, atol=1e-6)
        rebuilt = build_lattice(obs, expected, gps, network, model.decoder)
        for key in cached:
            np.testing.assert_array_equal(rebuilt[key], cached[key], err_msg=f"{trip}: {key}")
        reference = weak_reference(obs, gps, network, raw.route, settings.max_spatial_pairs)
        pd.testing.assert_frame_equal(reference[REFERENCE_COLUMNS],
            ledger.loc[ledger.trip_id == trip, REFERENCE_COLUMNS].reset_index(drop=True),
            check_dtype=False)
        destination = demo / "networks" / trip
        destination.mkdir(parents=True, exist_ok=True)
        files = {}
        for name in ("track", "nodes", "arcs", "route"):
            path = raw_dir / f"{trip}.{name}"
            copyfile(path, destination / name)
            files[name] = digest(path)
        manifest[trip] = dict(observations=len(obs), network_files=files,
                              lattice_key=lattice_key(obs, expected, raw.nodes, raw.arcs, model.decoder))
        print(f"{trip}: verified raw rows, features, reference, and graph ({len(obs):,} observations).")
    write_json(demo / "manifest.json", manifest)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("student_folder", type=Path)
    args = parser.parse_args()
    prepare(args.student_folder)
