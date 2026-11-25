"""Run orchestration: fetch, filter, enrich, summarize, persist, export."""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from datetime import datetime

from .gem_client import GemClient, normalize_bid
from .models import RunRecord, RunStatus, Settings, Tender
from .pdf_parser import apply_pdf_result, parse_tender_pdf
from .scoring import filter_tender, prepare_tenders, score_tender
from .sheets import export_run
from .storage import Storage
from .summarizer import rule_based_summary, summarize_tender

ProgressCallback = Callable[[int, str, str], None]


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def new_run_id() -> str:
    return f"{datetime.now().strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:6]}"


class Pipeline:
    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    def run(
        self,
        settings: Settings,
        progress: ProgressCallback | None = None,
        persist: bool = True,
        run_id: str | None = None,
    ) -> RunRecord:
        run_id = run_id or new_run_id()
        started = time.perf_counter()
        record = RunRecord(
            run_id=run_id,
            started_at=_now_iso(),
            status="running",
            settings=settings,
        )

        def emit(percent: int, stage: str, message: str) -> None:
            if progress:
                progress(max(0, min(100, percent)), stage, message)

        try:
            emit(3, "fetch", "Connecting to GeM")
            client = GemClient()
            raw_bids, source, fetch_errors = client.fetch_bids(settings, progress=progress)
            record.source = source
            record.errors.extend(fetch_errors)

            emit(20, "normalize", f"Normalizing {len(raw_bids)} bids")
            seen: set[str] = set()
            tenders: list[Tender] = []
            for raw in raw_bids:
                tender = normalize_bid(raw)
                if tender is None:
                    continue
                key = tender.bid_number.lower()
                if key in seen:
                    continue
                seen.add(key)
                tender.source = source
                tenders.append(tender)
            record.total_fetched = len(tenders)

            emit(32, "score", "Filtering and scoring tenders")
            matched, rejections = prepare_tenders(tenders, settings)
            record.rejections = rejections

            # ----------------------------------------------------- PDF enrichment
            pdf_texts: dict[str, str] = {}
            if settings.enable_pdf and matched and source != "sample":
                top = matched[: settings.parse_pdf_top_n]
                for index, tender in enumerate(top, start=1):
                    emit(
                        38 + int(index / max(len(top), 1) * 24),
                        "pdf",
                        f"Reading tender document {index}/{len(top)}",
                    )
                    result = parse_tender_pdf(tender)
                    apply_pdf_result(tender, result)
                    if result.text:
                        pdf_texts[tender.bid_number] = result.text
                    elif result.error and len(record.errors) < 8:
                        record.errors.append(
                            f"PDF {tender.bid_number}: {result.error}"
                        )

                # Parsed EMD/value can change both eligibility and score.
                rescored: list[Tender] = []
                for tender in matched:
                    eligible, reason = filter_tender(tender, settings)
                    if not eligible:
                        rejections[reason] = rejections.get(reason, 0) + 1
                        continue
                    scored = score_tender(tender, settings)
                    if scored.score < settings.min_score:
                        rejections["score below threshold"] = (
                            rejections.get("score below threshold", 0) + 1
                        )
                        continue
                    rescored.append(scored)
                matched = rescored
                matched.sort(key=lambda item: (-item.score, item.days_remaining or 9999))
            elif settings.enable_pdf and source == "sample":
                emit(40, "pdf", "Sample mode — skipping PDF downloads")

            # --------------------------------------------------------- summaries
            emit(66, "summarize", "Writing tender summaries")
            for index, tender in enumerate(matched, start=1):
                if settings.enable_ai_summary and index <= settings.summarize_top_n:
                    text = pdf_texts.get(tender.bid_number, "")
                    summary, summary_source = summarize_tender(tender, text)
                else:
                    summary, summary_source = rule_based_summary(tender), "rules"
                tender.summary = summary
                tender.summary_source = summary_source
                if index % 5 == 0:
                    emit(
                        66 + int(index / max(len(matched), 1) * 20),
                        "summarize",
                        f"Summarized {index}/{len(matched)} tenders",
                    )

            record.tenders = matched
            record.total_matched = len(matched)
            record.finished_at = _now_iso()
            record.duration_seconds = round(time.perf_counter() - started, 2)
            record.status = "done"

            if settings.enable_google_sheets:
                emit(90, "sheets", "Exporting to Google Sheets")
                record.sheet = export_run(record, settings)
                if record.sheet.get("status") == "error":
                    record.errors.append(
                        f"Google Sheets export failed: {record.sheet.get('reason')}"
                    )

            if persist:
                emit(97, "save", "Saving results")
                self.storage.save_run(record)

            emit(100, "done", f"Found {len(matched)} matching tenders")
            return record
        except Exception as exc:  # record the failure for the UI
            record.status = "error"
            record.finished_at = _now_iso()
            record.duration_seconds = round(time.perf_counter() - started, 2)
            record.errors.append(str(exc))
            if persist:
                try:
                    self.storage.save_run(record)
                except Exception:  # noqa: BLE001, S110 - best effort on failure
                    pass
            raise


class RunInProgressError(RuntimeError):
    """Raised when a second run is requested while one is active."""


class RunManager:
    """Run the pipeline in a background thread and expose pollable status."""

    def __init__(self, storage: Storage) -> None:
        self.storage = storage
        self.pipeline = Pipeline(storage)
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._state = RunStatus()

    def start(self, settings: Settings, use_sample: bool = False) -> RunStatus:
        with self._lock:
            if self._state.status == "running" and self._thread and self._thread.is_alive():
                raise RunInProgressError("A tender run is already in progress")

            if use_sample:
                settings = settings.model_copy(update={"use_sample_data": True})

            self.storage.save_settings(settings)
            run_id = new_run_id()
            self._state = RunStatus(
                run_id=run_id,
                status="running",
                progress=1,
                stage="queued",
                message="Starting run",
                started_at=_now_iso(),
                matched=0,
                fetched=0,
            )
            self._thread = threading.Thread(
                target=self._execute,
                args=(run_id, settings),
                name=f"gem-run-{run_id}",
                daemon=True,
            )
            self._thread.start()
            return self._state

    def _execute(self, run_id: str, settings: Settings) -> None:
        def progress(percent: int, stage: str, message: str) -> None:
            with self._lock:
                self._state.progress = percent
                self._state.stage = stage
                self._state.message = message

        try:
            record = self.pipeline.run(
                settings, progress=progress, persist=True, run_id=run_id
            )
            with self._lock:
                self._state.status = "done"
                self._state.progress = 100
                self._state.stage = "done"
                self._state.message = f"Found {record.total_matched} matching tenders"
                self._state.finished_at = record.finished_at
                self._state.matched = record.total_matched
                self._state.fetched = record.total_fetched
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self._state.status = "error"
                self._state.stage = "error"
                self._state.error = str(exc)
                self._state.message = "Run failed"
                self._state.finished_at = _now_iso()

    def status(self) -> RunStatus:
        with self._lock:
            return self._state.model_copy(deep=True)


def export_existing_run(
    storage: Storage, run_id: str | None, settings: Settings | None = None
) -> dict:
    """Export a stored run to Google Sheets."""
    payload = storage.get_run(run_id) if run_id else storage.latest_run()
    if not payload:
        return {"status": "error", "reason": "No run found to export"}
    record = RunRecord.model_validate(payload)
    active_settings = settings or record.settings
    return export_run(record, active_settings)
