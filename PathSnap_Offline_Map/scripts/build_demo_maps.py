"""Build Leaflet road basemaps from the verified, bundled demo networks."""
import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def main():
    demo = ROOT / "data" / "demo"
    manifest = json.loads((demo / "manifest.json").read_text(encoding="utf-8"))
    output = ROOT / "frontend" / "demo-maps"
    output.mkdir(exist_ok=True)
    for trip_id, metadata in sorted(manifest.items()):
        network = demo / "networks" / trip_id
        for name in ("nodes", "arcs"):
            with (network / name).open("rb") as source:
                digest = hashlib.file_digest(source, "sha256").hexdigest()
            if digest != metadata["network_files"][name]:
                raise ValueError(f"{trip_id}: the {name} file has changed")
        nodes = np.loadtxt(network / "nodes", ndmin=2)
        directed = np.loadtxt(network / "arcs", dtype=np.int64, ndmin=2)
        undirected = np.unique(np.sort(directed, axis=1), axis=0)
        segments = nodes[undirected]
        segments = segments[np.any(segments[:, 0] != segments[:, 1], axis=1)]
        if not len(segments) or not np.isfinite(segments).all():
            raise ValueError(f"{trip_id}: invalid road map geometry")
        basemap = {"type": "MultiLineString", "coordinates": segments.tolist()}
        (output / f"{trip_id}.geojson").write_text(
            json.dumps(basemap, separators=(",", ":"), allow_nan=False),
            encoding="utf-8",
        )
        print(f"{trip_id}: {len(segments):,} road segments")


if __name__ == "__main__":
    main()
