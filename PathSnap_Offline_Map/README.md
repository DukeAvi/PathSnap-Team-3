# PathSnap Trip Evaluator

Run the frozen Selected18 XGBoost emissions and directed-network Viterbi pipeline on ten held-out demos or a new GPS trip. The FastAPI app serves a Leaflet map, a per-observation ledger, optional weak-reference evaluation, and CSV, GeoJSON, and JSON downloads.

The frozen model reproduced all **19,160 exported arc IDs and decoder events**. Of these observations, **16,830 of 19,160 (87.8392484%)** agree with the geometric weak-reference labels. The benchmark describes the bundled test set.

## Start on Windows

Extract the complete ZIP and double-click `Start-PathSnap.cmd` inside the `PathSnap_Offline_Map` folder. The launcher uses Python 3.12 and installs dependencies the first time it runs. Keep the terminal open and visit [http://127.0.0.1:8010](http://127.0.0.1:8010).

Every demo automatically displays its built-in road network beneath the matched route. The map draws directly from the bundled road geometry and works offline after setup. The **Online street map** checkbox can add OpenStreetMap tiles when internet access is available.

## Open the Streamlit UI on another laptop

The Streamlit entry point is `streamlit_ui/app.py`. See the [Streamlit setup guide](docs/STREAMLIT.md) for a Wi-Fi connection or deployment to Streamlit Community Cloud.

## Run with Docker

Run this command in the extracted `PathSnap_App` directory.

```sh
docker compose up --build
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). The first visit opens the first demo automatically when there is no job history. Select any of the ten held-out trips or switch to **Upload trip** and supply your track, nodes, arcs, and optional reference route. The built-in map and trip overlays use supplied road geometry. Leaflet is bundled.

## Run directly with Python

Use Python 3.12 from the app directory.

```sh
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell uses: .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

## Verify the export and run the tests

```sh
python -m pip install -r requirements-dev.txt
python -m scripts.verify_bundle --per-trip
python -m pytest -q
```

The verifier checks candidate probabilities against the export, compares every chosen arc and decoder event, and checks the local candidate-index remapping for each trip. Tests also rebuild the raw candidate features and graph for all ten demo trips and compare raw and cached predictions.

## Rebuild the prepared inputs

The archive includes the model, frozen test fixtures, and all ten matching networks, GPS tracks, and routes. You can reproduce that layout from the trusted training export and the original dataset.

```sh
python -m scripts.import_bundle "/path/to/PathSnap_HMM_Trained.zip"
python -m scripts.prepare_demo "/path/to/input/Student folder"
python -m scripts.build_demo_maps
python -m scripts.verify_bundle --per-trip
```

The import checks all 45 members listed in the source export's SHA-256 manifest before copying runtime files. Demo preparation compares raw rows, candidate membership and features, transition geometry, and geometric weak labels before binding each network to its frozen cache. Keep the supplied scaler and model together. Import only trusted exports because the fitted scaler is serialized with Joblib.

- [API routes and responses](docs/API.md)
- [Raw input formats and preprocessing](docs/INPUT_FORMAT.md)
- [Deployment, storage, and runtime limits](docs/DEPLOYMENT.md)
