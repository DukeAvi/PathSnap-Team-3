"""Use supplied trip-local WGS84 network geometry for map layers."""
import numpy as np


def feature(kind, coordinates, properties):
    return {"type": "Feature", "geometry": {"type": kind, "coordinates": coordinates},
            "properties": properties}


def arc_coordinates(nodes, arcs, arc_id):
    return nodes[arcs[arc_id]].tolist()


def make_geojson(results, nodes, arcs, route, candidates, display_limit):
    features = []
    fields = ["observation_id", "raw_row", "timestamp", "predicted_arc_id", "decoder_event",
              "candidate_count", "reference_arc_id", "correct"]
    for row in results.to_dict("records"):
        properties = {field: row[field] for field in fields if field in row}
        features.append(feature("Point", [row["longitude"], row["latitude"]],
                                {**properties, "layer": "observations"}))

    def append_arcs(ids, layer):
        for arc_id in ids:
            features.append(feature("LineString", arc_coordinates(nodes, arcs, arc_id),
                                    {"layer": layer, "arc_id": int(arc_id)}))

    nearby = np.unique(candidates.arc_id.to_numpy(dtype=int))
    if len(arcs) <= display_limit:
        backdrop = np.arange(len(arcs))
    else:
        backdrop = nearby[:display_limit]
    append_arcs(backdrop, "network")
    if route is not None:
        append_arcs(dict.fromkeys(route.tolist()), "reference")
    path = results.predicted_arc_id.to_numpy()
    append_arcs(dict.fromkeys(path[path >= 0].tolist()), "matched")
    return {"type": "FeatureCollection", "features": features,
            "network": {"total_arcs": len(arcs), "displayed_arcs": len(backdrop),
                        "partial": len(backdrop) != len(arcs)}}
