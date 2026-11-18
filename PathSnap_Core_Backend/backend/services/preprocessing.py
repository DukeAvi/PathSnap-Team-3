"""Label-free inference preprocessing ported from pathsnap_shared6.py."""
from dataclasses import dataclass

import numpy as np
import pandas as pd
from pyproj import Geod, Transformer
import shapely
from shapely import STRtree

from backend.services.input_loader import InputError
from backend.vendor.pathsnap_features18 import SIX

VERSION = "shared-six-v1/eighteen-v1-lattice-v1"
RADIUS_M = 75.0
MAX_CANDIDATES = 8
EPSILON_M = 1e-6


@dataclass
class Network:
    nodes_xy: np.ndarray
    arcs: np.ndarray
    lines: np.ndarray
    lengths: np.ndarray
    headings: np.ndarray
    active_ids: np.ndarray
    epsg: int
    projection_error: float


def project(observations, nodes, arcs):
    lon, lat = observations[["longitude", "latitude"]].median().to_numpy()
    zone = min(60, max(1, int((lon + 180) // 6) + 1))
    epsg = (32600 if lat >= 0 else 32700) + zone
    transform = Transformer.from_crs(4326, epsg, always_xy=True)
    xy = np.column_stack(transform.transform(nodes[:, 0], nodes[:, 1]))
    gps = np.column_stack(transform.transform(observations.longitude.to_numpy(),
                                              observations.latitude.to_numpy()))
    if not np.isfinite(xy).all() or not np.isfinite(gps).all():
        raise InputError("Projection failed. Supply a local WGS84 track and matching nodes.")
    endpoints = xy[arcs]
    delta = endpoints[:, 1] - endpoints[:, 0]
    lengths = np.linalg.norm(delta, axis=1)
    active = np.flatnonzero(lengths > EPSILON_M)
    if not len(active):
        raise InputError("arcs: network has no nondegenerate road segments")
    sample = active[np.linspace(0, len(active) - 1, min(200, len(active)), dtype=int)]
    a, b = nodes[arcs[sample, 0]], nodes[arcs[sample, 1]]
    _, _, geodesic = Geod(ellps="WGS84").inv(a[:, 0], a[:, 1], b[:, 0], b[:, 1])
    if not np.isfinite(geodesic).all() or np.any(geodesic <= 0):
        raise InputError("nodes: road network does not project to local UTM geometry")
    error = float(np.max(np.abs(lengths[sample] / geodesic - 1)))
    if not np.isfinite(error) or error > 0.01:
        raise InputError("Sampled UTM distance error exceeds 1%. Use a local road network near the GPS track.")
    network = Network(xy, arcs, shapely.linestrings(endpoints), lengths,
                      np.arctan2(delta[:, 1], delta[:, 0]), active, epsg, error)
    return gps, network


def movement_features(track, xy):
    delta = np.diff(xy, axis=0, prepend=xy[:1])
    displacement = np.linalg.norm(delta, axis=1)
    dt = np.diff(track.timestamp, prepend=track.timestamp.iloc[0])
    valid = (displacement >= 3.0) & (dt > 0) & (dt <= 30.0)
    return displacement, np.arctan2(delta[:, 1], delta[:, 0]), valid


def heading_difference(movement, segment):
    return np.rad2deg(np.abs((movement - segment + np.pi) % (2 * np.pi) - np.pi))


def batch_size(feature_count):
    return max(1, min(512, 350000 // feature_count))


def generate_candidates(track, xy, net, max_pairs):
    points = shapely.points(xy)
    tree = STRtree(net.lines[net.active_ids])
    displacement, heading, valid = movement_features(track, xy)
    size = batch_size(len(net.active_ids))
    batches = []
    pair_count = 0
    for start in range(0, len(track), size):
        obs_pos, tree_pos = tree.query(points[start:start + size],
                                      predicate="dwithin", distance=RADIUS_M)
        pair_count += len(obs_pos)
        if pair_count > max_pairs:
            raise InputError("Too many nearby road candidates. Use a smaller network or track.",
                             "spatial_limit")
        obs_pos += start
        arc_id = net.active_ids[tree_pos]
        distances = shapely.distance(points[obs_pos], net.lines[arc_id])
        order = np.lexsort((arc_id, distances, obs_pos))
        obs_pos, arc_id, distances = obs_pos[order], arc_id[order], distances[order]
        starts = (np.r_[0, np.flatnonzero(np.diff(obs_pos)) + 1]
                  if len(obs_pos) else np.empty(0, dtype=int))
        rank = np.arange(len(obs_pos)) - np.repeat(starts, np.diff(np.r_[starts, len(obs_pos)])) + 1
        keep = rank <= MAX_CANDIDATES
        obs_pos, arc_id, distances, rank = obs_pos[keep], arc_id[keep], distances[keep], rank[keep]
        endpoints = net.nodes_xy[net.arcs[arc_id]]
        vector = endpoints[:, 1] - endpoints[:, 0]
        fraction = np.einsum("ij,ij->i", xy[obs_pos] - endpoints[:, 0], vector) / net.lengths[arc_id] ** 2
        hd = heading_difference(heading[obs_pos], net.headings[arc_id])
        hd[~valid[obs_pos]] = 90.0
        values = np.column_stack([distances, rank, hd, np.clip(fraction, 0, 1),
                                  net.lengths[arc_id], displacement[obs_pos]]).astype(np.float32)
        candidates = pd.DataFrame(values, columns=SIX)
        candidates.insert(0, "arc_id", arc_id)
        candidates.insert(0, "observation_id", track.observation_id.to_numpy()[obs_pos])
        candidates.insert(0, "trip_id", track.trip_id.iloc[0])
        batches.append(candidates)
    return pd.concat(batches, ignore_index=True)
