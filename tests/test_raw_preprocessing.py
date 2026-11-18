from io import BytesIO

import numpy as np
import pytest

from backend.services.features import augment
from backend.services.graph import build_lattice, lattice_key
from backend.services.inference import decode
from backend.services.input_loader import InputError, clean_track, read_trip
from backend.services.preprocessing import generate_candidates, project
from backend.settings import Settings
from backend.vendor.pathsnap_features18 import FEATURES

TRACK = b"77.00004 13 11\n77 13 0\n77.003 13 11\nnan 13 9\n77.00006 13 42\n77.01 13 43\n77.00007 13 44"
NODES = b"76.9999 13\n77.0002 13"
ARCS = b"0 1\n0 1\n1 0\n0 0"


def raw_trip(route=None, arcs=ARCS):
    return read_trip(BytesIO(TRACK), BytesIO(NODES), BytesIO(arcs),
                     BytesIO(route) if route is not None else None, "sample", Settings())


def run_raw(raw, model):
    gps, net = project(raw.observations, raw.nodes, raw.arcs)
    candidates = augment(generate_candidates(raw.observations, gps, net, 1000), raw.observations,
                         raw.nodes, raw.arcs)
    lattice = build_lattice(raw.observations, candidates, gps, net, model.decoder)
    p = model.probabilities(candidates[FEATURES])
    return candidates, p, decode(raw.observations, candidates, p, [lattice], model.decoder)


def test_raw_identity_and_decoder_resets_are_label_free(frozen_model):
    raw = raw_trip()
    assert raw.observations.raw_row.tolist() == [1, 0, 4, 5, 6]
    assert raw.cleaning["duplicate_times_dropped"] == 1
    assert raw.cleaning["invalid_gps_dropped"] == 1
    c, p, predictions = run_raw(raw, frozen_model)
    tied = c.loc[(c.observation_id == 0) & c.arc_id.isin([0, 1])]
    assert tied.distance_m.nunique() == 1
    assert tied.arc_id.tolist() == [0, 1]
    assert 3 not in c.arc_id.to_numpy()
    assert predictions.decoder_event.tolist() == ["start", "", "gap_reset", "no_candidates", "restart"]
    assert predictions.predicted_arc_id.iloc[3] == -1
    empty = c.iloc[:0]
    gps, net = project(raw.observations, raw.nodes, raw.arcs)
    lattice = build_lattice(raw.observations, empty, gps, net, frozen_model.decoder)
    result = decode(raw.observations, empty, frozen_model.probabilities(empty[FEATURES]),
                    [lattice], frozen_model.decoder)
    assert (result.predicted_arc_id == -1).all()
    first_key = lattice_key(raw.observations, c, raw.nodes, raw.arcs, frozen_model.decoder)
    changed_key = lattice_key(raw.observations, c.iloc[::-1], raw.nodes, raw.arcs, frozen_model.decoder)
    assert first_key != changed_key
    other_c, other_p, other_pred = run_raw(raw_trip(b"2\n0"), frozen_model)
    assert c.equals(other_c)
    np.testing.assert_array_equal(p, other_p)
    assert predictions.equals(other_pred)


def test_reject_unusable_or_unsupported_data():
    with pytest.raises(InputError, match="zero-based"):
        raw_trip(arcs=b"0 99")
    with pytest.raises(InputError, match="zero-based"):
        raw_trip(b"99")
    with pytest.raises(InputError, match="distinct timestamps"):
        clean_track(np.array([[0, 0, 1], [0, 0, 1]]), "bad")
    with pytest.raises(InputError, match="UTM extent"):
        clean_track(np.array([[0, 89, 1], [0, 89, 2]]), "bad")
