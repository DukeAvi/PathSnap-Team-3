"""Persist job results atomically before the job becomes downloadable."""
import json
from pathlib import Path
from time import sleep
import warnings

DOWNLOADS = {
    "csv": ("predictions.csv", "text/csv"),
    "geojson": ("map.geojson", "application/geo+json"),
    "json": ("result.json", "application/json"),
}


def write_json(path: Path, payload):
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, separators=(",", ":"), allow_nan=False)
    delays = (0.05, 0.15, 0.35)
    for delay in delays:
        try:
            temporary.replace(path)
            return
        except PermissionError as error:
            if getattr(error, "winerror", None) not in (32, 33):
                raise
            sleep(delay)
    temporary.replace(path)


def save_result(path, observations, summary, geojson):
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="invalid value encountered in cast",
                                category=RuntimeWarning)
        observations.to_csv(path / "predictions.csv", index=False)
    write_json(path / "map.geojson", geojson)
    write_json(path / "result.json", {"summary": summary,
                                      "observations": observations.to_dict("records")})
    write_json(path / "summary.json", summary)
