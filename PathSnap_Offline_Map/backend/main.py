"""Same-origin FastAPI application and evaluator."""
from contextlib import asynccontextmanager
from functools import partial

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from backend.api import health, jobs, model, trips
from backend.schemas import ErrorResponse
from backend.services.demo import validate_frozen_files
from backend.services.input_loader import InputError
from backend.services.job_store import JobStore
from backend.services.model_loader import FrozenModel, read_json
from backend.services.tasks import run_trip
from backend.settings import Settings


def error_response(status, code, message):
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


class LimitUploadBody:
    def __init__(self, app, limit):
        self.app = app
        self.limit = limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST":
            await self.app(scope, receive, send)
            return
        content_length = dict(scope["headers"]).get(b"content-length", b"0")
        try:
            size = int(content_length)
        except ValueError:
            await error_response(400, "invalid_request", "Invalid Content-Length.")(scope, receive, send)
            return
        message = f"Upload request exceeds {self.limit:,} bytes."
        if size > self.limit:
            await error_response(413, "upload_too_large", message)(scope, receive, send)
            return
        received = 0

        async def limited_receive():
            nonlocal received
            event = await receive()
            received += len(event.get("body", b""))
            if received > self.limit:
                raise HTTPException(413, message)
            return event

        await self.app(scope, limited_receive, send)


def create_app(settings=None):
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(application):
        application.state.settings = settings
        application.state.model = FrozenModel.load(settings.artifacts_dir)
        manifest = settings.demo_dir / "manifest.json"
        application.state.demos = read_json(manifest) if manifest.is_file() else {}
        if application.state.demos:
            validate_frozen_files(settings.demo_dir,
                read_json(settings.artifacts_dir / "provenance" / "SHA256SUMS.json"))
        application.state.jobs = JobStore(settings, partial(
            run_trip, model=application.state.model, settings=settings))
        try:
            yield
        finally:
            application.state.jobs.close()

    application = FastAPI(title="PathSnap evaluator", version="1.0.0", lifespan=lifespan)
    application.add_middleware(LimitUploadBody, limit=settings.max_request_bytes)

    @application.exception_handler(InputError)
    async def input_error(_request: Request, exc: InputError):
        return error_response(exc.status, exc.code, str(exc))

    @application.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError):
        issues = [f"{'.'.join(map(str, item['loc']))}: {item['msg']}" for item in exc.errors()]
        return error_response(422, "invalid_request", "; ".join(issues))

    @application.exception_handler(HTTPException)
    async def http_error(_request: Request, exc: HTTPException):
        code = {413: "upload_too_large", 404: "not_found", 405: "method_not_allowed"}
        response = error_response(exc.status_code, code.get(exc.status_code, "http_error"), str(exc.detail))
        response.headers.update(exc.headers or {})
        return response

    errors = {code: {"model": ErrorResponse} for code in (400, 404, 409, 413, 422, 429)}
    for module in (health, model, trips, jobs):
        application.include_router(module.router, prefix="/api/v1", responses=errors)
    application.mount("/assets", StaticFiles(directory=settings.frontend_dir), name="assets")

    @application.get("/", include_in_schema=False)
    def frontend():
        return FileResponse(settings.frontend_dir / "index.html")

    return application


app = create_app()
