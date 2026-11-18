"""Independent Shared6 route-derived weak labels and frozen evaluation metrics."""
import numpy as np
import pandas as pd
import shapely
from shapely import STRtree

from backend.services.input_loader import InputError
from backend.services.preprocessing import EPSILON_M, batch_size, heading_difference, movement_features


def weak_reference(observations, xy, net, route, max_pairs):
    positions = np.flatnonzero(net.lengths[route] > EPSILON_M)
    if not len(positions):
        raise InputError("route: no nondegenerate reference segment")
    points = shapely.points(xy)
    tree = STRtree(net.lines[route[positions]])
    displacement, heading, valid = movement_features(observations, xy)
    prefix = np.r_[0., np.cumsum(net.lengths[route])]
    observed_progress = np.cumsum(displacement)
    expected = observed_progress / max(observed_progress[-1], EPSILON_M) * prefix[-1]
    batches = []
    pair_count = 0
    size = batch_size(len(positions))
    for start in range(0, len(points), size):
        pairs, distance = tree.query_nearest(points[start:start + size],
                                             all_matches=True, return_distance=True)
        pair_count += len(distance)
        if pair_count > max_pairs:
            raise InputError("Too many equally near reference segments. Use a shorter route.",
                             "spatial_limit")
        obs_pos, route_pos = pairs[0] + start, positions[pairs[1]]
        arc_id = route[route_pos]
        projected = shapely.line_locate_point(net.lines[arc_id], points[obs_pos])
        progress = prefix[route_pos] + projected
        hd = heading_difference(heading[obs_pos], net.headings[arc_id])
        hd[~valid[obs_pos]] = 0
        order = np.lexsort((route_pos, np.abs(progress - expected[obs_pos]), hd, obs_pos))
        selected = order[np.r_[True, np.diff(obs_pos[order]) != 0]]
        matches = pd.DataFrame({"obs": obs_pos, "arc": arc_id}).drop_duplicates()
        ties = np.bincount(matches.obs.to_numpy() - start, minlength=len(selected)) > 1
        batches.append(pd.DataFrame(dict(
            observation_id=observations.observation_id.to_numpy()[obs_pos[selected]],
            reference_arc_id=arc_id[selected], reference_distance_m=distance[selected],
            reference_route_position=route_pos[selected], reference_progress_m=progress[selected],
            reference_tie=ties,
        )))
    return pd.concat(batches, ignore_index=True)


def summarize(predictions, candidates, lattice, reference):
    result = predictions.copy()
    counts = candidates.groupby("observation_id").size()
    result["candidate_count"] = result.observation_id.map(counts).fillna(0).astype(int)
    matched = result.predicted_arc_id >= 0
    selected = result.set_index("observation_id").loc[lattice["obs_ids"], "predicted_arc_id"].to_numpy()
    dt = lattice["dt"][1:]
    eligible = (selected[:-1] >= 0) & (selected[1:] >= 0) & (dt > 0) & (dt <= 30)
    steps = np.flatnonzero(eligible) + 1
    slots = np.argmax(lattice["arcs"] == selected[:, None], axis=1)
    distances = lattice["routes"][steps, slots[steps - 1], slots[steps]]
    feasible = int(np.sum(np.isfinite(distances) & (distances <= 80.0 * dt[eligible] + 150.0)))
    summary = dict(observations=len(result), candidate_rows=len(candidates),
                   matched=int(matched.sum()), unmatched=int((~matched).sum()),
                   reference_agreement=None, continuity_pair_count=len(dt),
                   continuity_eligible_pairs=len(steps), continuous_pairs=feasible,
                   route_continuity=feasible / len(dt) if len(dt) else 0.0,
                   decoder_events={str(key): int(value) for key, value in
                                   result.decoder_event.replace("", "continue").value_counts().items()})
    if reference is not None:
        result = result.merge(reference, on="observation_id", validate="one_to_one")
        seen = candidates[["observation_id", "arc_id"]].rename(columns={"arc_id": "reference_arc_id"})
        have = pd.MultiIndex.from_frame(seen)
        result["reference_present"] = pd.MultiIndex.from_frame(
            result[["observation_id", "reference_arc_id"]]).isin(have)
        result["correct"] = result.predicted_arc_id == result.reference_arc_id
        correct = int(result.correct.sum())
        summary["reference_agreement"] = dict(
            correct=correct, total=len(result), fraction=correct / len(result),
            candidate_coverage=float(result.reference_present.mean()),
            exact_observation_sequence=bool(result.correct.all()))
    return result, summary
