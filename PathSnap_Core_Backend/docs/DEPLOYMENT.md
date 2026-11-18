# Local deployment

From `PathSnap_Core_Backend`, run `docker compose up --build` and visit [http://127.0.0.1:8000](http://127.0.0.1:8000). The host port publishes on loopback. `docker compose down` stops the app and preserves its named jobs volume. The first image build needs access to package repositories. The trip evaluator itself works offline after setup.

The container uses Python 3.12, installs the CPU XGBoost wheel, and runs the app as a non-root user. To change Compose limits or the host port, copy `.env.example` to `.env` and edit the values before starting. For a native Python run, set the equivalent variables in your shell. Pass the native port to Uvicorn using `--port`.

| Variable | Default |
| --- | --- |
| `PATHSNAP_PORT` (Compose) | `8000` |
| `PATHSNAP_MAX_FILE_BYTES` | `8388608` (8 MiB per file) |
| `PATHSNAP_MAX_TRACK_ROWS` | `25000` |
| `PATHSNAP_MAX_NODES` | `180000` |
| `PATHSNAP_MAX_ARCS` | `350000` |
| `PATHSNAP_MAX_ROUTE_ROWS` | `50000` |
| `PATHSNAP_MAX_SPATIAL_PAIRS` | `5000000` hits per candidate or reference search |
| `PATHSNAP_MAX_ACTIVE_JOBS` | `4` including the running job |
| `PATHSNAP_MAX_SAVED_JOBS` | `25` |
| `PATHSNAP_MAX_DISPLAY_ARCS` | `10000` backdrop arcs |
| `PATHSNAP_JOBS_DIR` | `data/jobs` natively and the mounted volume in Compose |

Use one Uvicorn process per jobs directory. One worker processes jobs serially and the fitted model is loaded once in that process. Status, raw uploaded inputs, and generated results persist under internal job IDs. When the saved job limit is reached, a new submission expires the oldest completed or failed job. Export results you want to keep. A restart marks interrupted jobs failed so that you can resubmit them.

Inference, GeoJSON exports, and the API operate with local artifacts and data. The optional FastAPI Swagger page uses its standard CDN assets. The OpenAPI JSON and the supplied API documentation remain available offline.
