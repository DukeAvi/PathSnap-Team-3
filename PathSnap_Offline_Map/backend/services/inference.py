"""Run the frozen compiled decoder with candidate-index alignment checks."""
import numpy as np
import pandas as pd

from backend.vendor.fast_decoder import decode_fast

OBS_COLUMNS = ["observation_id", "trip_id", "timestamp", "longitude", "latitude", "raw_row"]


def decode(observations, candidates, probabilities, lattices, config):
    if (len(probabilities) != len(candidates) or not np.isfinite(probabilities).all()
            or not observations.observation_id.is_unique):
        raise ValueError("Invalid inference ledger or candidate probabilities")
    observation_ids = candidates.observation_id.to_numpy()
    candidate_arcs = candidates.arc_id.to_numpy()
    candidate_trips = candidates.trip_id.to_numpy()
    frames = []
    for lattice in lattices:
        ids = lattice["obs_ids"]
        indices = lattice["indices"]
        rows, cols = np.where(indices >= 0)
        selected = indices[rows, cols]
        if (indices.shape != (len(ids), 8) or np.any(indices < -1)
                or np.any(selected >= len(probabilities))
                or not np.array_equal(observation_ids[selected], ids[rows])
                or not np.array_equal(candidate_arcs[selected], lattice["arcs"][rows, cols])
                or not np.all(candidate_trips[selected] == str(lattice["trip"]))):
            raise ValueError("Lattice candidate indices do not match the probability vector")
        arcs, events = decode_fast(lattice, probabilities, config)
        frames.append(pd.DataFrame(dict(observation_id=ids, predicted_arc_id=arcs,
                                        decoder_event=events)))
    decoded = pd.concat(frames, ignore_index=True)
    result = observations[OBS_COLUMNS].merge(decoded, on="observation_id", how="left",
                                             validate="one_to_one")
    if len(decoded) != len(result) or result.predicted_arc_id.isna().any():
        raise ValueError("Lattice observations do not match the observation ledger")
    return result
