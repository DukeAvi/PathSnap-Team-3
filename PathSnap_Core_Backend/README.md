# PathSnap Core Backend

The FastAPI service runs the frozen Selected18 XGBoost model and directed-network Viterbi decoder on uploaded GPS trips and ten bundled demos. API endpoints accept jobs and return matching results, evaluation metrics, and CSV, GeoJSON, and JSON exports.

## Run in VS Code on Windows

Extract the ZIP, open the `PathSnap_Core_Backend` folder, and run these commands in PowerShell with Python 3.12 installed.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Open [the API docs](http://127.0.0.1:8000/docs) or check [server health](http://127.0.0.1:8000/api/v1/health). The OpenAPI schema is available at `/openapi.json`.

## Run a demo from PowerShell

With the server running, open a second terminal and submit a bundled trip.

```powershell
$job = Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/trips/demos/00000052
$status = "http://127.0.0.1:8000/api/v1/jobs/$($job.job_id)"
Invoke-RestMethod $status
```

Once the job state is `succeeded`, retrieve its result with `Invoke-RestMethod "$status/result"`.

## Use Docker

Run `docker compose up --build` from this folder and open [the API docs](http://127.0.0.1:8000/docs).

## Verify the frozen model

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m scripts.verify_bundle --per-trip
```

- [API endpoints and response formats](docs/API.md)
- [Raw input format](docs/INPUT_FORMAT.md)
- [Deployment and limits](docs/DEPLOYMENT.md)
