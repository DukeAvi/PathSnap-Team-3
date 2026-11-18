# Raw trip format

Upload separate whitespace-delimited text files without headers. Nonblank lines are data rows. Whitespace varies freely between fields. File extensions describe their roles and may vary in the upload.

| Multipart field | Columns per nonblank row | Meaning |
| --- | --- | --- |
| `track` | `longitude latitude timestamp_seconds` | WGS84 GPS points with numeric seconds |
| `nodes` | `longitude latitude` | WGS84 road network points in index order |
| `arcs` | `from_node_id to_node_id` | Directed arc endpoints, both zero-based node IDs |
| `route` | `arc_id` | Optional ordered reference route, as zero-based arc IDs |
| `trip_id` | String form field | 1–64 characters, beginning with an ASCII letter or digit. Later characters may also include `_`, `-`, and `.` |

Here is a two-point `track`.

```text
77.00002 13.00000 1
77.00010 13.00000 2
```

The road network has two `nodes`.

```text
77.00000 13.00000
77.00020 13.00000
```

These two `arcs` run in opposite directions.

```text
0 1
1 0
```

An optional `route` containing a single line `0` supplies a reference for both observations in this example.

## Cleaning and geometry

- Sort valid GPS observations stably by timestamp. For duplicate timestamps, retain the earliest input row. Invalid numeric GPS coordinates or nonfinite GPS coordinates and times are discarded and counted. Malformed rows and nonnumeric tokens are rejected.
- A usable track needs at least two retained observations with distinct timestamps. `raw_row` is the zero-based data-row identity before cleaning. Upload observation IDs start at zero and are unique within that job. Demos keep the globally unique IDs from the frozen evaluation ledger.
- Retained GPS latitudes and node latitudes must be within the supported UTM extent of −80° through 84°. The track median chooses its UTM zone and hemisphere. Projection must be finite, and sampled road segment lengths are checked against geodesic lengths using the original Shared6 1% threshold. Supply a local road network in the same area as the trip.
- Endpoints and reference IDs must be finite, integer-valued, and in range. Node and arc IDs preserve input order. The network needs at least one nondegenerate arc. Degenerate segments keep their original row IDs and are excluded from candidates and graph edges.
- Shared6 generates up to eight arcs per retained observation, within 75 metres in projected coordinates. Rank is by exact distance with arc ID as the tie-breaker. Movement uses the preceding retained point, with heading available for movement of at least 3 metres within a positive gap of up to 30 seconds. The exported augmentation supplies the remaining twelve predictors.
- The optional route is evaluated after decoding. Each GPS observation receives a geometric weak label from its nearest nondegenerate segment on the route, with ties resolved by heading, rough route progress, and then route position. Reference values never enter candidate or inference data. A route can contain repeated arcs and disconnected steps. It needs at least one nondegenerate segment.

The cleaning report records raw and retained counts, invalid GPS and duplicate drops, how many valid rows moved in the stable sort, gaps over 30 seconds, and the network size. Projection, zero-length arcs, and route discontinuities appear in the results summary.
