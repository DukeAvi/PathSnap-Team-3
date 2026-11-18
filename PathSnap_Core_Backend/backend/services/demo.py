"""Frozen fixtures and per-trip remapping for the local evaluator."""
from pathlib import Path

import numpy as np
import pandas as pd

from backend.services.inference import OBS_COLUMNS
from backend.vendor.pathsnap_features18 import FEATURES

DEMO_IDS = ("00000000", "00000007", "00000009", "00000040", "00000052",
            "00000056", "00000065", "00000076", "00000077", "00000091")


def read_lattice(path):
    with np.load(path, allow_pickle=False) as archive:
        return {key: archive[key] for key in archive.files}


def frozen_inputs(demo: Path):
    frozen = demo / "frozen"
    observations = pd.read_csv(frozen / "student_test_observations.csv.gz", dtype={"trip_id": str})
    with np.load(frozen / "test_candidates.npz", allow_pickle=False) as archive:
        if archive["features"].tolist() != FEATURES:
            raise ValueError("Frozen candidate feature order mismatch")
        candidates = pd.DataFrame(archive["X"], columns=FEATURES)
        for key in ("trip_id", "observation_id", "arc_id"):
            candidates.insert(len(candidates.columns), key, archive[key])
    return observations, candidates


def frozen_trip(demo, trip):
    observations, candidates = frozen_inputs(demo)
    obs = observations.loc[observations.trip_id == trip].reset_index(drop=True)
    if not len(obs):
        raise ValueError(f"Unknown frozen trip {trip}")
    positions = np.flatnonzero(candidates.trip_id.to_numpy() == trip)
    lattice = read_lattice(demo / "frozen" / "geometry_cache" / f"student_test_{trip}.npz")
    old_indices = lattice["indices"]
    has_candidate = old_indices >= 0
    lookup = np.full(len(candidates), -1)
    lookup[positions] = np.arange(len(positions))
    used = old_indices[has_candidate]
    if np.any(used >= len(lookup)) or np.any(lookup[used] < 0):
        raise ValueError(f"Frozen lattice references a different trip: {trip}")
    lattice["indices"][has_candidate] = lookup[used]
    return obs[OBS_COLUMNS], candidates.iloc[positions].reset_index(drop=True), lattice


def validate_frozen_files(demo, provenance_manifest):
    import hashlib

    paths = {
        **{name: f"test_inputs/{name}" for name in ("student_test_observations.csv.gz",
                                                    "test_candidates.npz")},
        **{f"geometry_cache/student_test_{trip}.npz":
           f"test_inputs/geometry_cache/student_test_{trip}.npz" for trip in DEMO_IDS},
        "hmm_student_observation_predictions.csv.gz":
            "results/hmm_student_observation_predictions.csv.gz",
        "selected_student_candidate_probabilities.npy":
            "results/selected_student_candidate_probabilities.npy",
    }
    for relative, original in paths.items():
        with (demo / "frozen" / relative).open("rb") as source:
            if hashlib.file_digest(source, "sha256").hexdigest() != provenance_manifest.get(original):
                raise ValueError(f"Frozen demo checksum mismatch: {relative}")
