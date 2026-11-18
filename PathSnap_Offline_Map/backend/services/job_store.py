"""Bounded local queue with one worker and restart-safe status persistence."""
from datetime import datetime, timezone
import logging
from queue import Queue
from shutil import copyfileobj, rmtree
from threading import Lock, Thread
from uuid import uuid4

from backend.services.exports import DOWNLOADS, write_json
from backend.services.input_loader import InputError
from backend.services.model_loader import read_json

LOG = logging.getLogger(__name__)
ACTIVE = ("queued", "running")


def now():
    return datetime.now(timezone.utc).isoformat()


class JobStore:
    def __init__(self, settings, runner):
        self.settings = settings
        self.root = settings.jobs_dir
        self.runner = runner
        self.lock = Lock()
        self.queue = Queue(maxsize=settings.max_active_jobs)
        self.root.mkdir(parents=True, exist_ok=True)
        self.jobs = {}
        self.closed = False
        for path in self.root.glob("*/status.json"):
            status = read_json(path)
            if status["state"] in ACTIVE:
                status.update(state="failed", updated_at=now(), error={
                    "code": "worker_restarted", "message": "The worker stopped. Submit this trip again."})
                write_json(path, status)
            self.jobs[status["job_id"]] = status
        self.worker = Thread(target=self._work, name="pathsnap-worker")
        self.worker.start()

    def _update(self, job_id, **changes):
        status = {**self.jobs[job_id], **changes, "updated_at": now()}
        write_json(self.root / job_id / "status.json", status)
        self.jobs[job_id] = status

    def _work(self):
        while True:
            item = self.queue.get()
            if item is None:
                return
            job_id, task = item
            path = self.root / job_id
            try:
                with self.lock:
                    self._update(job_id, state="running")
                self.runner(path, task)
                with self.lock:
                    self._update(job_id, state="succeeded")
            except Exception as error:
                LOG.exception("PathSnap job %s for trip %s failed", job_id, task["trip_id"])
                detail = {"code": "job_failed", "message": "Inference failed. Check the server log."}
                if isinstance(error, (InputError, ValueError)):
                    detail = {"code": getattr(error, "code", "inference_input"),
                              "message": str(error)}
                elif isinstance(error, PermissionError):
                    detail = {"code": "file_access_denied", "message":
                              "PathSnap could not access a required file. On Windows, close any open job files and retry."}
                elif isinstance(error, FileNotFoundError):
                    detail = {"code": "job_file_missing", "message":
                              "A required job or demo file is missing. Check the server terminal for its path."}
                elif isinstance(error, OSError):
                    detail = {"code": "job_io_error", "message":
                              "PathSnap could not read or save a file. Check the server terminal for details."}
                with self.lock:
                    try:
                        self._update(job_id, state="failed", error=detail)
                    except OSError:
                        LOG.exception("Could not persist status for job %s", job_id)
                        self.jobs[job_id].update(state="failed", updated_at=now(), error=detail)

    def submit(self, task, uploads=None):
        with self.lock:
            if self.closed or sum(j["state"] in ACTIVE for j in self.jobs.values()) >= self.settings.max_active_jobs:
                raise InputError("Inference queue is full. Wait for an active job to finish.",
                                 "queue_full", 429)
            while len(self.jobs) >= self.settings.max_saved_jobs:
                old = min((job for job in self.jobs.values() if job["state"] not in ACTIVE),
                          key=lambda job: job["updated_at"])
                rmtree(self.root / old["job_id"])
                del self.jobs[old["job_id"]]
            job_id = uuid4().hex
            path = self.root / job_id
            path.mkdir()
            created_at = now()
            status = dict(job_id=job_id, trip_id=task["trip_id"], source=task["source"],
                          state="queued", cleaning=task.get("cleaning"),
                          created_at=created_at, updated_at=created_at, error=None)
            try:
                for name, source in (uploads or {}).items():
                    if source is not None:
                        source.seek(0)
                        with (path / name).open("wb") as output:
                            copyfileobj(source, output)
                write_json(path / "status.json", status)
            except OSError:
                rmtree(path, ignore_errors=True)
                raise
            self.jobs[job_id] = status
            self.queue.put_nowait((job_id, task))
            return status.copy()

    def _find(self, job_id):
        if job_id not in self.jobs:
            raise InputError("This job does not exist or has expired.", "job_not_found", 404)
        return self.jobs[job_id]

    def get(self, job_id):
        with self.lock:
            return self._find(job_id).copy()

    def list(self):
        with self.lock:
            return sorted(self.jobs.values(), key=lambda status: status["created_at"], reverse=True)

    def result(self, job_id, kind):
        with self.lock:
            if self._find(job_id)["state"] != "succeeded":
                raise InputError("Results become available after a successful job.", "result_unavailable", 409)
            filename = "summary.json" if kind == "summary" else DOWNLOADS[kind][0]
            return (self.root / job_id / filename).read_bytes()

    def close(self):
        with self.lock:
            self.closed = True
        self.queue.put(None)
        self.worker.join()
