"""Reproduce every frozen held-out arc and decoder event without retraining."""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from backend.services.demo import DEMO_IDS, frozen_inputs, frozen_trip, read_lattice
from backend.services.inference import decode
from backend.services.model_loader import FrozenModel
from backend.vendor.pathsnap_features18 import FEATURES

ROOT = Path(__file__).resolve().parents[1]


def verify(root=ROOT, per_trip=False):
    model = FrozenModel.load(root / "artifacts")
    demo = root / "data" / "demo"
    obs, candidates = frozen_inputs(demo)
    frozen = demo / "frozen"
    expected = pd.read_csv(frozen / "hmm_student_observation_predictions.csv.gz",
                           keep_default_na=False, dtype={"trip_id": str})
    p = model.probabilities(candidates[FEATURES])
    saved_p = np.load(frozen / "selected_student_candidate_probabilities.npy", allow_pickle=False)
    np.testing.assert_allclose(p, saved_p, rtol=2e-5, atol=2e-6)
    lattices = [read_lattice(frozen / "geometry_cache" / f"student_test_{trip}.npz")
                for trip in DEMO_IDS]
    predictions = decode(obs, candidates, p, lattices, model.decoder)
    columns = ["observation_id", "trip_id", "predicted_arc_id", "decoder_event"]
    pd.testing.assert_frame_equal(predictions[columns], expected[columns], check_dtype=False)
    correct = int((predictions.predicted_arc_id == obs.reference_arc_id).sum())
    assert (correct, len(predictions)) == (16830, 19160)
    if per_trip:
        for trip in DEMO_IDS:
            local_obs, local_candidates, lattice = frozen_trip(demo, trip)
            local_p = model.probabilities(local_candidates[FEATURES])
            local = decode(local_obs, local_candidates, local_p, [lattice], model.decoder)
            pd.testing.assert_frame_equal(local[columns],
                expected.loc[expected.trip_id == trip, columns].reset_index(drop=True),
                check_dtype=False)
    print(f"Exact arc/event parity for {len(predictions):,} observations across {len(DEMO_IDS)} trips.")
    print(f"Weak-reference agreement: {correct:,} / {len(predictions):,} ({correct / len(predictions):.7%}).")
    return correct, len(predictions)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--per-trip", action="store_true", help="Also verify local trip index remapping")
    args = parser.parse_args()
    verify(per_trip=args.per_trip)
