"""Readiness endpoint for local deployment."""
from fastapi import APIRouter, Request

from backend.schemas import Health

router = APIRouter(tags=["health"])


@router.get("/health", response_model=Health)
def health(request: Request):
    return {"status": "ok", "demos": len(request.app.state.demos)}
