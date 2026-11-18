"""Filesystem locations and local runtime limits."""
from dataclasses import dataclass, field
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def env_limit(name, default):
    value = int(os.environ.get(f"PATHSNAP_{name}", default))
    if value <= 0:
        raise ValueError(f"PATHSNAP_{name} must be positive")
    return value


@dataclass(frozen=True)
class Settings:
    artifacts_dir: Path = ROOT / "artifacts"
    frontend_dir: Path = ROOT / "frontend"
    demo_dir: Path = ROOT / "data" / "demo"
    jobs_dir: Path = field(default_factory=lambda: Path(os.environ.get(
        "PATHSNAP_JOBS_DIR", ROOT / "data" / "jobs")).resolve())
    max_file_bytes: int = field(default_factory=lambda: env_limit("MAX_FILE_BYTES", 8 * 1024**2))
    max_track_rows: int = field(default_factory=lambda: env_limit("MAX_TRACK_ROWS", 25000))
    max_nodes: int = field(default_factory=lambda: env_limit("MAX_NODES", 180000))
    max_arcs: int = field(default_factory=lambda: env_limit("MAX_ARCS", 350000))
    max_route_rows: int = field(default_factory=lambda: env_limit("MAX_ROUTE_ROWS", 50000))
    max_spatial_pairs: int = field(default_factory=lambda: env_limit("MAX_SPATIAL_PAIRS", 5000000))
    max_active_jobs: int = field(default_factory=lambda: env_limit("MAX_ACTIVE_JOBS", 4))
    max_saved_jobs: int = field(default_factory=lambda: env_limit("MAX_SAVED_JOBS", 25))
    max_display_arcs: int = field(default_factory=lambda: env_limit("MAX_DISPLAY_ARCS", 10000))

    def __post_init__(self):
        if self.max_saved_jobs < self.max_active_jobs:
            raise ValueError("Saved job limit must be at least the active job limit")

    @property
    def max_request_bytes(self):
        return self.max_file_bytes * 4 + 65536
