import numpy as np
import pandas as pd
import pytest

from backend.services.demo import DEMO_IDS, frozen_trip
from backend.services.features import FEATURES, augment
from backend.services.graph import build_lattice, lattice_key
from backend.services.inference import decode
from backend.services.input_loader import read_trip_directory
from backend.services.model_loader import read_json
from backend.services.preprocessing import generate_candidates, project
from backend.settings import ROOT, Settings
from scripts.verify_bundle import verify

DEMO = ROOT / "data" / "demo"


def test_frozen_all_and_per_trip():
    assert verify(per_trip=True) == (16830, 19160)


@pytest.mark.parametrize("trip", DEMO_IDS)
def test_raw_rebuild_matches_frozen_features_and_transitions(trip, frozen_model):
    settings = Settings()
    obs, frozen, lattice = frozen_trip(DEMO, trip)
    raw = read_trip_directory(DEMO / "networks" / trip, trip, settings)
    # Raw uploads allocate job-local IDs. Use the original IDs for table equality here.
    raw.observations["observation_id"] = obs.observation_id
    gps, net = project(raw.observations, raw.nodes, raw.arcs)
    candidates = augment(generate_candidates(raw.observations, gps, net,
                                              settings.max_spatial_pairs), obs, raw.nodes, raw.arcs)
    for key in ["observation_id", "arc_id", "trip_id"]:
        pd.testing.assert_series_equal(candidates[key], frozen[key])
    np.testing.assert_allclose(candidates[FEATURES], frozen[FEATURES], rtol=1e-6, atol=1e-6)
    rebuilt = build_lattice(obs, candidates, gps, net, frozen_model.decoder)
    for key in lattice:
        if key == "trip":
            np.testing.assert_equal(rebuilt[key], lattice[key])
        else:
            np.testing.assert_allclose(rebuilt[key], lattice[key], rtol=1e-6, atol=1e-6)
    actual = decode(obs, candidates, frozen_model.probabilities(candidates[FEATURES]), [rebuilt],
                    frozen_model.decoder)
    cached = decode(obs, frozen, frozen_model.probabilities(frozen[FEATURES]), [lattice],
                    frozen_model.decoder)
    pd.testing.assert_frame_equal(actual, cached)
    manifest = read_json(DEMO / "manifest.json")
    key = lattice_key(obs, frozen, raw.nodes, raw.arcs, frozen_model.decoder)
    assert key == manifest[trip]["lattice_key"]


def test_wrong_subset_index_is_rejected(frozen_model):
    obs, candidates, lattice = frozen_trip(DEMO, "00000052")
    p = frozen_model.probabilities(candidates[FEATURES])
    lattice["indices"][0, 0] = len(p)
    with pytest.raises(ValueError, match="probability vector"):
        decode(obs, candidates, p, [lattice], frozen_model.decoder)
