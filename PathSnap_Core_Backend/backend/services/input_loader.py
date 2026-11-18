"""Parse only supported whitespace-separated trip formats."""
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import numpy as np
import pandas as pd


class InputError(ValueError):
    def __init__(self, message, code="invalid_input", status=422):
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class RawTrip:
    observations: pd.DataFrame
    nodes: np.ndarray
    arcs: np.ndarray
    route: np.ndarray | None
    cleaning: dict


def numeric(source: BinaryIO, name, columns, max_rows, max_bytes):
    rows = []
    byte_count = 0
    source.seek(0)
    for line_number, line in enumerate(source, 1):
        byte_count += len(line)
        if byte_count > max_bytes:
            raise InputError(f"{name}: file exceeds {max_bytes:,} bytes", "upload_too_large", 413)
        fields = line.split()
        if not fields:
            continue
        if len(rows) >= max_rows:
            raise InputError(f"{name}: exceeds the {max_rows:,}-row limit")
        if len(fields) != columns:
            raise InputError(f"{name}, line {line_number}: expected {columns} numeric columns")
        try:
            rows.append([float(value) for value in fields])
        except ValueError:
            raise InputError(f"{name}, line {line_number}: expected numeric values without a header") from None
    if not rows:
        raise InputError(f"{name}: no data rows")
    return np.asarray(rows, dtype=np.float64)


def coordinates_valid(a):
    return np.isfinite(a[:, :2]).all(axis=1) & (np.abs(a[:, 0]) <= 180) & (np.abs(a[:, 1]) <= 90)


def clean_track(raw, trip_id):
    good = coordinates_valid(raw) & np.isfinite(raw[:, 2])
    frame = pd.DataFrame(raw[good], columns=["longitude", "latitude", "timestamp"])
    frame["raw_row"] = np.flatnonzero(good)
    original_order = frame.raw_row.to_numpy().copy()
    frame = frame.sort_values("timestamp", kind="stable")
    reordered = int(np.sum(original_order != frame.raw_row.to_numpy()))
    duplicates = int(frame.timestamp.duplicated().sum())
    frame = frame.drop_duplicates("timestamp", keep="first").reset_index(drop=True)
    if len(frame) < 2:
        raise InputError("track: need at least two valid observations with distinct timestamps")
    if not frame.latitude.between(-80, 84).all():
        raise InputError("track: retained latitudes must be in the UTM extent [-80, 84]")
    with np.errstate(over="ignore", invalid="ignore"):
        gaps = np.diff(frame.timestamp.to_numpy())
    if not np.isfinite(gaps).all():
        raise InputError("track: timestamp differences exceed the supported numeric range")
    frame["observation_id"] = np.arange(len(frame), dtype=np.int64)
    frame["trip_id"] = trip_id
    return frame, dict(raw_observations=len(raw), invalid_gps_dropped=int((~good).sum()),
                       duplicate_times_dropped=duplicates, reordered_rows=reordered,
                       observations=len(frame), gaps_over_30s=int((gaps > 30).sum()))


def indices(values, upper, name):
    if (not np.isfinite(values).all() or not np.equal(values, np.floor(values)).all()
            or np.any(values < 0) or np.any(values >= upper)):
        raise InputError(f"{name}: expected integer IDs in the zero-based range 0..{upper - 1}")
    return values.astype(np.int64)


def read_trip(track, nodes, arcs, route, trip_id, settings):
    observations, report = clean_track(numeric(track, "track", 3, settings.max_track_rows,
                                               settings.max_file_bytes), trip_id)
    node_coords = numeric(nodes, "nodes", 2, settings.max_nodes, settings.max_file_bytes)
    if not coordinates_valid(node_coords).all():
        raise InputError("nodes: expected finite WGS84 longitude and latitude")
    if not ((node_coords[:, 1] >= -80) & (node_coords[:, 1] <= 84)).all():
        raise InputError("nodes: latitude is outside the UTM extent [-80, 84]")
    endpoints = indices(numeric(arcs, "arcs", 2, settings.max_arcs, settings.max_file_bytes),
                        len(node_coords), "arcs")
    route_ids = None
    if route is not None:
        route_ids = indices(numeric(route, "route", 1, settings.max_route_rows,
                                    settings.max_file_bytes).ravel(), len(endpoints), "route")
    report.update(nodes=len(node_coords), arcs=len(endpoints))
    return RawTrip(observations, node_coords, endpoints, route_ids, report)


def read_trip_directory(path: Path, trip_id, settings, stem=""):
    def file(extension):
        return path / (f"{stem}.{extension}" if stem else extension)

    with file("track").open("rb") as track, file("nodes").open("rb") as nodes, file("arcs").open("rb") as arcs:
        if file("route").is_file():
            with file("route").open("rb") as route:
                return read_trip(track, nodes, arcs, route, trip_id, settings)
        return read_trip(track, nodes, arcs, None, trip_id, settings)
