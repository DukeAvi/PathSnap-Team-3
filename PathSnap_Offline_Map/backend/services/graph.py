"""Directed transition geometry ported from the frozen lattice builder."""
import hashlib
import json

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

from backend.services.preprocessing import MAX_CANDIDATES, VERSION
from backend.vendor.pathsnap_features18 import FEATURES


def lattice_key(observations, candidates, nodes, arcs, decoder):
    """Include order and identity as well as the exact geometry and config."""
    digest = hashlib.sha256()
    digest.update(json.dumps([VERSION, decoder], sort_keys=True).encode())
    arrays = (
        observations.trip_id.to_numpy(dtype=str), observations.observation_id.to_numpy(dtype="<i8"),
        observations.raw_row.to_numpy(dtype="<i8"),
        observations[["longitude", "latitude", "timestamp"]].to_numpy(dtype="<f8"),
        candidates.trip_id.to_numpy(dtype=str),
        candidates[["observation_id", "arc_id"]].to_numpy(dtype="<i8"),
        candidates[FEATURES].to_numpy(dtype="<f4"),
        np.asarray(nodes, dtype="<f8"), np.asarray(arcs, dtype="<i8"),
    )
    for array in arrays:
        digest.update(json.dumps([array.shape, array.dtype.str]).encode())
        digest.update(array.tobytes())
    return digest.hexdigest()


def build_lattice(observations, candidates, gps, net, decoder):
    # The loader gives observations chronological order and assigns stable IDs.
    # A candidate's index here is its position in the emission vector.
    candidates = candidates.reset_index(drop=True)
    candidates = candidates.sort_values(["observation_id", "distance_rank", "arc_id"],
                                        kind="stable")
    active = net.active_ids
    arcs = net.arcs
    length = net.lengths
    order = active[np.lexsort((length[active], arcs[active, 1], arcs[active, 0]))]
    edges = order[np.r_[True, np.any(arcs[order[1:]] != arcs[order[:-1]], axis=1)]]
    graph = csr_matrix((length[edges], (arcs[edges, 0], arcs[edges, 1])),
                       shape=(len(net.nodes_xy), len(net.nodes_xy)))
    obs_ids = observations.observation_id.to_numpy()
    indices = np.full((len(obs_ids), MAX_CANDIDATES), -1, dtype=np.int64)
    arc_ids = np.full_like(indices, -1)
    fractions = np.zeros_like(indices, dtype=float)
    slots = candidates.groupby("observation_id", sort=False).cumcount().to_numpy()
    rows = observations.set_index("observation_id").index.get_indexer(candidates.observation_id)
    if np.any(rows < 0) or np.any(slots >= MAX_CANDIDATES):
        raise ValueError("Invalid candidate rows for this observation ledger")
    indices[rows, slots] = candidates.index
    arc_ids[rows, slots] = candidates.arc_id
    fractions[rows, slots] = candidates.projection_fraction
    dt = np.r_[0., np.diff(observations.timestamp.to_numpy())]
    displacement = np.r_[0., np.linalg.norm(np.diff(gps, axis=0), axis=1)]

    routes = np.full((*indices.shape, MAX_CANDIDATES), np.inf, dtype=np.float32)
    counts = np.count_nonzero(indices >= 0, axis=1)
    steps = np.flatnonzero((dt[1:] > 0) & (dt[1:] <= decoder["max_gap_s"])
                           & (counts[:-1] > 0) & (counts[1:] > 0)) + 1
    requests = {}
    for step in steps:
        previous = arc_ids[step - 1, :counts[step - 1]]
        current = arc_ids[step, :counts[step]]
        targets = set(arcs[current, 0].tolist())
        for source in set(arcs[previous, 1].tolist()):
            requests.setdefault(source, set()).update(targets)
    distances = {}
    for source, targets in requests.items():
        distances_from_source = dijkstra(graph, directed=True, indices=source,
                                         limit=decoder["search_limit_m"])
        distances[source] = {target: distances_from_source[target] for target in targets}
    for step in steps:
        previous = arc_ids[step - 1, :counts[step - 1]]
        current = arc_ids[step, :counts[step]]
        before = fractions[step - 1, :len(previous)]
        after = fractions[step, :len(current)]
        bridge = np.array([[distances[source][target] for target in arcs[current, 0]]
                           for source in arcs[previous, 1]])
        distance = ((1 - before) * length[previous])[:, None] + bridge + (after * length[current])[None, :]
        delta = (after[None, :] - before[:, None]) * length[previous, None]
        same_arc = (previous[:, None] == current[None, :]) & (delta >= -decoder["jitter_m"])
        distance[same_arc] = np.minimum(distance[same_arc], np.maximum(0, delta[same_arc]))
        routes[step, :len(previous), :len(current)] = distance
    return dict(indices=indices, arcs=arc_ids, obs_ids=obs_ids, dt=dt, displacement=displacement,
                routes=routes, trip=np.array(str(observations.trip_id.iloc[0])))
