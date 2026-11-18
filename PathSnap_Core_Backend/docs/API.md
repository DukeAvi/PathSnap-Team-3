# PathSnap API

FastAPI serves the OpenAPI schema at `/openapi.json` and interactive documentation at `/docs`.

| Method | Path | Result |
| --- | --- | --- |
| GET | `/api/v1/health` | Ready status and number of installed demos |
| GET | `/api/v1/model` | The exact ordered predictors, frozen decoder settings, provenance metrics, and evaluation definitions |
| GET | `/api/v1/trips/demos` | Demo trip IDs and observation counts |
| POST | `/api/v1/trips/demos/{trip_id}` | Queue an installed demo and return a job with status 202 |
| POST | `/api/v1/trips` | Queue a single multipart trip and return a job and cleaning report with status 202 |
| GET | `/api/v1/jobs` | Retained jobs, newest first |
| GET | `/api/v1/jobs/{job_id}` | Job status and actionable failure details, if present |
| GET | `/api/v1/jobs/{job_id}/summary` | Cleaning, match counts, continuity, events, timings, and optional reference agreement |
| GET | `/api/v1/jobs/{job_id}/result` | Summary and observation ledger |
| GET | `/api/v1/jobs/{job_id}/map` | WGS84 GeoJSON with network, reference, matched arcs, and observations |
| GET | `/api/v1/jobs/{job_id}/exports/{kind}` | Attachment download. `kind` is `csv`, `geojson`, or `json` |

## Submit and retrieve

```sh
curl -fsS http://127.0.0.1:8000/api/v1/trips \
  -F 'trip_id=trip-01' \
  -F 'track=@my-trip.track' \
  -F 'nodes=@my-network.nodes' \
  -F 'arcs=@my-network.arcs' \
  -F 'route=@my-reference.route'
```

Omit the last field for inference without a reference. For a demo, send a POST to `/api/v1/trips/demos/00000052` without a request body. Copy `job_id` from the response and poll the job route until its `state` is `succeeded` or `failed`. Active states are `queued` and `running`. Inference and exports are ready together when the job succeeds.

| Status | Meaning |
| --- | --- |
| 202 | Trip queued |
| 404 | Unknown demo or expired or unknown job |
| 409 | Results unavailable while the job is active or failed |
| 413 | File or upload body exceeds the configured byte limit |
| 422 | Missing or malformed fields or invalid trip data |
| 429 | Active job capacity reached |

Request errors use `{"error":{"code":"invalid_input","message":"arcs: expected integer IDs in the zero-based range 0..1"}}`. Some trip geometry or decoder errors are discovered by the worker. These appear in the status payload in `error`, with `state` set to `failed`.

The ledger includes `observation_id`, `trip_id`, `raw_row`, `timestamp`, `longitude`, `latitude`, `predicted_arc_id`, `candidate_count`, and `decoder_event`. Decoder events are the empty string for ordinary continuation and `start`, `gap_reset`, `no_candidates`, `restart`, or `transition_reset` when applicable. Unmatched observation arc IDs are `-1`. Reference columns appear when evaluation is available.

Continuity counts consecutive pairs with positive gaps up to 30 seconds, two matched arcs, and a feasible directed distance of at most `80 × gap + 150` metres under the frozen geometry rules. The denominator includes every consecutive pair. Weak-reference agreement compares each decoded arc with the weak reference chosen for that GPS observation. Unmatched observations remain in the agreement denominator.

GeoJSON line features represent directed arcs in supplied node order. A line is emitted per distinct arc within a layer. The observation ledger preserves the full sequence. For large networks, the map backdrop contains up to the configured number of candidate arcs, while the matched and reference layers keep their distinct arcs. GeoJSON's `network` metadata reports the backdrop coverage.
