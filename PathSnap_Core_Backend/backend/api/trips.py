"""Accept a raw trip or select an installed benchmark demo."""
from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile

from backend.schemas import DemoTrip, JobStatus, TRIP_ID
from backend.services.input_loader import InputError, read_trip

router = APIRouter(prefix="/trips", tags=["trips"])


@router.get("/demos", response_model=list[DemoTrip])
def list_demos(request: Request):
    return [{"trip_id": trip, "observations": demo["observations"]}
            for trip, demo in sorted(request.app.state.demos.items())]


@router.post("/demos/{trip_id}", response_model=JobStatus, status_code=202)
def submit_demo(trip_id: str, request: Request):
    demo = request.app.state.demos.get(trip_id)
    if demo is None:
        raise InputError("This bundled trip is unavailable.", "demo_not_found", 404)
    return request.app.state.jobs.submit(dict(trip_id=trip_id, source="demo", demo=demo))


@router.post("", response_model=JobStatus, status_code=202)
def submit_trip(request: Request, trip_id: Annotated[str, Form(pattern=TRIP_ID)],
                track: Annotated[UploadFile, File()], nodes: Annotated[UploadFile, File()],
                arcs: Annotated[UploadFile, File()], route: Annotated[UploadFile | None, File()] = None):
    settings = request.app.state.settings
    uploads = dict(track=track, nodes=nodes, arcs=arcs, route=route)
    for name, upload in uploads.items():
        if upload is not None and upload.size is not None and upload.size > settings.max_file_bytes:
            raise InputError(f"{name}: file exceeds {settings.max_file_bytes:,} bytes",
                             "upload_too_large", 413)
    streams = {name: upload.file if upload is not None else None for name, upload in uploads.items()}
    raw = read_trip(**streams, trip_id=trip_id, settings=settings)
    return request.app.state.jobs.submit(dict(trip_id=trip_id, source="upload",
                                              cleaning=raw.cleaning), streams)
