import numpy as np
import pandas as pd

from backend.services.geometry import make_geojson


def test_geojson_is_wgs84_and_uses_directed_trip_local_arcs():
    nodes = np.array([[77.1, 13.2], [77.3, 13.4]])
    arcs = np.array([[0, 1], [1, 0]])
    results = pd.DataFrame([
        dict(observation_id=9, raw_row=0, timestamp=0, longitude=77.2, latitude=13.3,
             predicted_arc_id=1, decoder_event="start", candidate_count=1),
        dict(observation_id=10, raw_row=1, timestamp=1, longitude=77.4, latitude=13.5,
             predicted_arc_id=-1, decoder_event="no_candidates", candidate_count=0),
    ])
    candidates = pd.DataFrame({"arc_id": [1]})
    output = make_geojson(results, nodes, arcs, np.array([0, 0]), candidates, display_limit=1)
    layers = {item["properties"]["layer"]: item["geometry"] for item in output["features"][1:]}
    assert output["features"][0]["geometry"]["coordinates"] == [77.2, 13.3]
    assert layers["matched"]["coordinates"] == [[77.3, 13.4], [77.1, 13.2]]
    assert layers["reference"]["coordinates"] == [[77.1, 13.2], [77.3, 13.4]]
    assert output["network"] == {"total_arcs": 2, "displayed_arcs": 1, "partial": True}
