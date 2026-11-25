"""FastAPI backend for the GeM tender brain."""

from __future__ import annotations

from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .constants import BID_TYPES, INDIAN_STATES, IT_CATEGORIES, OTHER_CATEGORIES
from .models import (
    ApiMeta,
    ExportRequest,
    HealthResponse,
    RunRequest,
    RunStatus,
    Settings,
)
from .pipeline import RunInProgressError, RunManager, export_existing_run
from .storage import Storage

VERSION = "1.0.0"

storage = Storage()
manager = RunManager(storage)

app = FastAPI(
    title="GeM Tender Brain",
    description="Filters and scores GeM tenders, reads tender PDFs, and writes results to Google Sheets.",
    version=VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {
        "app": "GeM Tender Brain",
        "version": VERSION,
        "docs": "/docs",
        "frontend": "Run `python run_frontend.py` and open http://localhost:8501",
    }


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        version=VERSION,
        time=datetime.now(),
        data_dir=str(config.DATA_DIR),
    )


@app.get("/api/meta", response_model=ApiMeta)
def meta() -> ApiMeta:
    return ApiMeta(
        it_categories=IT_CATEGORIES,
        other_categories=OTHER_CATEGORIES,
        states=INDIAN_STATES,
        bid_types=BID_TYPES,
        groq_available=config.groq_available(),
        google_available=config.google_available(),
        sample_mode_default=config.GEM_SAMPLE_MODE,
    )


@app.get("/api/settings", response_model=Settings)
def get_settings() -> Settings:
    return storage.load_settings()


@app.put("/api/settings", response_model=Settings)
def put_settings(settings: Settings) -> Settings:
    return storage.save_settings(settings)


@app.post("/api/run", response_model=RunStatus)
def start_run(request: RunRequest | None = None) -> RunStatus:
    body = request or RunRequest()
    settings = body.settings or storage.load_settings()
    try:
        return manager.start(settings, use_sample=body.use_sample)
    except RunInProgressError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/run/status", response_model=RunStatus)
def run_status() -> RunStatus:
    return manager.status()


@app.get("/api/runs/latest")
def latest_run() -> dict:
    payload = storage.latest_run()
    if not payload:
        raise HTTPException(status_code=404, detail="No runs saved yet")
    return payload


@app.get("/api/runs")
def list_runs(limit: int = 25) -> list[dict]:
    return storage.list_runs(limit=max(1, min(limit, 100)))


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict:
    payload = storage.get_run(run_id)
    if not payload:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return payload


@app.post("/api/export")
def export_to_sheets(request: ExportRequest | None = None) -> dict:
    body = request or ExportRequest()
    settings = body.settings or storage.load_settings()
    result = export_existing_run(storage, body.run_id, settings)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("reason", "Export failed"))
    return result
