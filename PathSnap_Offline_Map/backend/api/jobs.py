"""Read persisted job state, summaries and export files."""
from typing import Literal

from fastapi import APIRouter, Request, Response

from backend.schemas import JobResult, JobStatus, Summary
from backend.services.exports import DOWNLOADS

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=list[JobStatus])
def jobs(request: Request):
    return request.app.state.jobs.list()


@router.get("/{job_id}", response_model=JobStatus)
def status(job_id: str, request: Request):
    return request.app.state.jobs.get(job_id)


@router.get("/{job_id}/summary", response_model=Summary)
def summary(job_id: str, request: Request):
    return Summary.model_validate_json(request.app.state.jobs.result(job_id, "summary"))


@router.get("/{job_id}/result", response_model=JobResult, response_model_exclude_unset=True)
def result(job_id: str, request: Request):
    return JobResult.model_validate_json(request.app.state.jobs.result(job_id, "json"))


@router.get("/{job_id}/map")
def map_data(job_id: str, request: Request):
    return Response(request.app.state.jobs.result(job_id, "geojson"),
                    media_type="application/geo+json")


@router.get("/{job_id}/exports/{kind}")
def download(job_id: str, kind: Literal["csv", "geojson", "json"], request: Request):
    filename, mime = DOWNLOADS[kind]
    return Response(request.app.state.jobs.result(job_id, kind), media_type=mime,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
