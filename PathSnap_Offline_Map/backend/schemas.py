"""Public request, response and error schemas."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

TRIP_ID = r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$"


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class CleaningReport(BaseModel):
    raw_observations: int
    invalid_gps_dropped: int
    duplicate_times_dropped: int
    reordered_rows: int
    observations: int
    gaps_over_30s: int
    nodes: int
    arcs: int


class JobStatus(BaseModel):
    job_id: str
    trip_id: str
    source: Literal["demo", "upload"]
    state: Literal["queued", "running", "succeeded", "failed"]
    created_at: datetime
    updated_at: datetime
    cleaning: CleaningReport | None = None
    error: ErrorDetail | None = None


class DemoTrip(BaseModel):
    trip_id: str
    observations: int


class Health(BaseModel):
    status: Literal["ok"]
    demos: int


class ModelInfo(BaseModel):
    algorithm: str
    features: list[str]
    schema_version: str
    decoder: dict[str, float | str]
    benchmark: dict[str, float | int | str]
    evaluation_definitions: dict[str, str]


class Agreement(BaseModel):
    correct: int
    total: int
    fraction: float
    candidate_coverage: float
    exact_observation_sequence: bool


class NetworkDisplay(BaseModel):
    total_arcs: int
    displayed_arcs: int
    partial: bool


class Timing(BaseModel):
    preparation_s: float
    emissions_s: float
    decoder_s: float


class Summary(BaseModel):
    trip_id: str
    source: Literal["demo", "upload"]
    cleaning: CleaningReport
    projection_epsg: int
    zero_length_arcs: int
    lattice_key: str
    timings: Timing
    network: NetworkDisplay
    route: dict[str, int] | None = None
    observations: int
    candidate_rows: int
    matched: int
    unmatched: int
    continuity_pair_count: int
    continuity_eligible_pairs: int
    continuous_pairs: int
    route_continuity: float
    decoder_events: dict[str, int]
    reference_agreement: Agreement | None


class ObservationResult(BaseModel):
    observation_id: int
    trip_id: str
    timestamp: float
    longitude: float
    latitude: float
    raw_row: int
    predicted_arc_id: int
    decoder_event: Literal["", "no_candidates", "start", "gap_reset", "restart", "transition_reset"]
    candidate_count: int
    reference_arc_id: int | None = None
    reference_distance_m: float | None = None
    reference_route_position: int | None = None
    reference_progress_m: float | None = None
    reference_tie: bool | None = None
    reference_present: bool | None = None
    correct: bool | None = None


class JobResult(BaseModel):
    summary: Summary
    observations: list[ObservationResult]
