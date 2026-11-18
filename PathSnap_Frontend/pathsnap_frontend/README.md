# PathSnap evaluator frontend

A lightweight interface for the two-laptop evaluation. It connects to the team's FastAPI backend, loads the available evaluation trip IDs, requests a prediction and displays the returned GeoJSON layers and metrics. No trip predictions or reference routes are hardcoded.

## Run on Laptop 2

1. Install Python and open a terminal in this folder.
2. Run `python -m http.server 8080` (Windows: `py -m http.server 8080`).
3. Open `http://localhost:8080` on Laptop 2. Click the gear and enter Laptop 1's server address, for example `http://192.168.1.10:8000`.
4. Choose a trip and click **Run reconstruction**. Both laptops need network connectivity, and the server must listen on its LAN interface (e.g. `uvicorn main:app --host 0.0.0.0 --port 8000`). Allow the port through the firewall as required.

The page uses Leaflet, OpenStreetMap tiles and Google Fonts from CDNs, so it needs internet access for the interactive map and fonts. Prediction calls are made directly from the browser to Laptop 1. The API must allow the UI's actual origin in CORS, including `http://localhost:8080` when served as above. Do not load this UI from HTTPS while calling an HTTP LAN API: browsers may block mixed content.

## API contract

The frontend is an integration-ready UI. The backend is not included. Implement or adapt the following contract in your FastAPI application. It is a proposed contract because the team's API implementation was not supplied.

### `GET /trips`

Returns the actual evaluator trip choices from the server:

```json
{"trips": [{"trip_id": "example-id", "label": "Trip 1"}]}
```

An array of IDs or objects is also accepted. Do not use student-test IDs as the evaluator set unless the evaluator explicitly provides them as such.

### `POST /predict`

Request:

```json
{"trip_id": "example-id"}
```

Response:

```json
{
  "metrics": {"top1_accuracy": 0.82, "route_continuity": 0.95, "processing_seconds": 1.4},
  "layers": {
    "gps_observations": {"type": "FeatureCollection", "features": []},
    "road_network": {"type": "FeatureCollection", "features": []},
    "predicted_route": {"type": "FeatureCollection", "features": []}
  }
}
```

Metrics shown above are only an API-format example, not experimental results. Return actual values from the server. Metrics `top1_accuracy` and `route_continuity` are fractions in [0, 1]; omit any unavailable metric. Layer values are GeoJSON geometry, Feature or FeatureCollection, with coordinates in `[longitude, latitude]` order (WGS84). The optional `reference_route` GeoJSON can be returned only if authorized by evaluation rules; supplied guidelines state evaluator ground-truth labels must remain server-side and not be exposed to the UI. In that case omit the layer. Do not include label arrays, route IDs or other reference data in the UI response. Return predicted road geometry and any approved aggregate metrics instead.

The server must generate predictions from the selected trip through the actual model and HMM/Viterbi pipeline, calculate metrics server-side, and log requests as required. The UI does not perform inference or create evaluation results. If your endpoints have different names, change them in `app.js` or add adapter endpoints. Serve a restricted and validated set of trip IDs from the backend.

Example CORS configuration in FastAPI:

```python
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
```

If Laptop 2 opens the frontend at a different origin, add that exact origin. Consult your team before finalizing the API schema and confirm metric definitions (especially route continuity and pointwise accuracy).
