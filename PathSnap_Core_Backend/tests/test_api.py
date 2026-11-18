import csv
from io import StringIO
import json
from threading import Event
import time

from fastapi.testclient import TestClient

from backend.main import create_app
from backend.services.input_loader import InputError
from backend.services.job_store import JobStore
from backend.settings import Settings

ROOT = "/api/v1"
FILES = dict(track=("anything", b"77.0001 13 2\n77.00002 13 1\n77.00003 13 1"),
             nodes=("anything", b"77 13\n77.0002 13"),
             arcs=("anything", b"0 1\n1 0"))


def wait(client, job, expected="succeeded"):
    path = f"{ROOT}/jobs/{job['job_id']}"
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        status = client.get(path).json()
        if status["state"] not in ("queued", "running"):
            assert status["state"] == expected, status
            return path
        time.sleep(0.05)
    raise AssertionError(f"Job failed to terminate: {status}")


def test_upload_demo_artifacts_and_persistence(tmp_path):
    settings = Settings(jobs_dir=tmp_path)
    with TestClient(create_app(settings)) as client:
        assert client.get("/").json()["service"] == "PathSnap API"
        assert client.get("/openapi.json").json()["info"]["title"] == "PathSnap API"
        assert client.get("/assets/vendor/leaflet.js").status_code == 404
        assert client.get(f"{ROOT}/health").json() == {"status": "ok", "demos": 10}
        model = client.get(f"{ROOT}/model").json()
        assert model["benchmark"]["correct_observations"] == 16830
        assert len(model["features"]) == 18
        assert len(client.get(f"{ROOT}/trips/demos").json()) == 10
        initial = client.post(f"{ROOT}/trips", files=FILES, data={"trip_id": "upload-1"})
        assert initial.status_code == 202
        assert initial.json()["cleaning"]["duplicate_times_dropped"] == 1
        first = wait(client, initial.json())
        without = client.get(f"{first}/result").json()
        assert without["summary"].get("reference_agreement") is None
        assert "reference_arc_id" not in without["observations"][0]
        submitted = client.post(f"{ROOT}/trips", files={**FILES, "route": ("route", b"0")},
                                data={"trip_id": "upload-1"})
        second = wait(client, submitted.json())
        with_reference = client.get(f"{second}/result").json()
        assert with_reference["summary"]["reference_agreement"]["total"] == 2
        for left, right in zip(without["observations"], with_reference["observations"], strict=True):
            assert left == {key: right[key] for key in left}
        assert without["summary"]["lattice_key"] == with_reference["summary"]["lattice_key"]
        assert len(list(csv.DictReader(StringIO(client.get(f"{second}/exports/csv").text)))) == 2
        assert client.get(f"{second}/exports/json").json() == with_reference
        assert client.get(f"{second}/exports/geojson").json() == client.get(f"{second}/map").json()
        assert client.get(f"{second}/map").headers["content-type"] == "application/geo+json"
        demo = client.post(f"{ROOT}/trips/demos/00000052")
        assert demo.status_code == 202
        demo_path = wait(client, demo.json())
        assert client.get(f"{demo_path}/summary").json()["reference_agreement"]["correct"] == 259
    with TestClient(create_app(settings)) as client:
        assert client.get(f"{second}/summary").status_code == 200
        assert len(client.get(f"{ROOT}/jobs").json()) == 3


def test_malformed_upload_and_limits(tmp_path):
    settings = Settings(jobs_dir=tmp_path, max_file_bytes=100)
    with TestClient(create_app(settings)) as client:
        uri = f"{ROOT}/trips"
        malformed = client.post(uri, files={**FILES, "arcs": ("bad", b"0 999")}, data={"trip_id": "test"})
        assert malformed.status_code == 422
        assert "zero-based" in malformed.json()["error"]["message"]
        assert client.post(uri, files=FILES, data={"trip_id": "../bad"}).status_code == 422
        assert client.post(uri, files={}, data={"trip_id": "no-files"}).status_code == 422
        long_track = {"track": ("large", b"0" * 101)}
        assert client.post(uri, files={**FILES, **long_track}, data={"trip_id": "test"}).status_code == 413
        limit_exceeded = client.post(uri, content=b"x" * (settings.max_request_bytes + 1))
        assert limit_exceeded.status_code == 413
        assert client.get(f"{ROOT}/jobs/absent").status_code == 404
        assert client.get(f"{ROOT}/jobs").json() == []
        invalid_network = client.post(uri, files={**FILES, "arcs": ("bad", b"0 0")},
                                      data={"trip_id": "test"})
        path = wait(client, invalid_network.json(), expected="failed")
        assert "nondegenerate" in client.get(path).json()["error"]["message"]
        assert client.get(f"{path}/result").status_code == 409


def test_queue_bound_and_interrupted_status(tmp_path):
    settings = Settings(jobs_dir=tmp_path, max_active_jobs=1, max_saved_jobs=1)
    released = Event()
    store = JobStore(settings, lambda *_: released.wait(timeout=3))
    try:
        job = store.submit({"trip_id": "one", "source": "demo"})
        try:
            store.submit({"trip_id": "two", "source": "demo"})
        except InputError as exc:
            assert exc.status == 429
        else:
            raise AssertionError("The bounded queue accepted a second active job")
    finally:
        released.set()
        store.close()
    status_file = tmp_path / job["job_id"] / "status.json"
    payload = json.loads(status_file.read_text())
    status_file.write_text(json.dumps({**payload, "state": "running"}))
    restarted = JobStore(settings, lambda *_: None)
    try:
        assert restarted.get(job["job_id"])["error"]["code"] == "worker_restarted"
        restarted.submit({"trip_id": "new", "source": "demo"})
        assert not status_file.exists()
    finally:
        restarted.close()
