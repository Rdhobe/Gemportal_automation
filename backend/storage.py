"""JSON file storage for settings and tender runs."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from .config import RUNS_DIR, SETTINGS_FILE
from .models import RunRecord, Settings


class Storage:
    """Simple, dependency-free persistence rooted at the project data folder."""

    def __init__(self, settings_file: Path | None = None, runs_dir: Path | None = None) -> None:
        self.settings_file = Path(settings_file or SETTINGS_FILE)
        self.runs_dir = Path(runs_dir or RUNS_DIR)
        self.settings_file.parent.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ settings
    def load_settings(self) -> Settings:
        if not self.settings_file.exists():
            settings = Settings()
            self.save_settings(settings)
            return settings
        try:
            payload = json.loads(self.settings_file.read_text(encoding="utf-8"))
            return Settings.model_validate(payload)
        except (json.JSONDecodeError, OSError, ValueError):
            return Settings()

    def save_settings(self, settings: Settings) -> Settings:
        with self._lock:
            self._atomic_write(self.settings_file, settings.model_dump(mode="json"))
        return settings

    # ---------------------------------------------------------------------- runs
    def save_run(self, record: RunRecord) -> Path:
        filename = f"{record.started_at.replace(':', '').replace('-', '')}__{record.run_id}.json"
        path = self.runs_dir / filename
        with self._lock:
            self._atomic_write(path, record.model_dump(mode="json"))
        return path

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        for path in sorted(self.runs_dir.glob("*.json"), reverse=True):
            if run_id in path.stem:
                try:
                    return json.loads(path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    continue
        return None

    def latest_run(self) -> dict[str, Any] | None:
        files = sorted(self.runs_dir.glob("*.json"), reverse=True)
        for path in files:
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
        return None

    def list_runs(self, limit: int = 25) -> list[dict[str, Any]]:
        summaries: list[dict[str, Any]] = []
        for path in sorted(self.runs_dir.glob("*.json"), reverse=True)[:limit]:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            summaries.append(
                {
                    "run_id": payload.get("run_id"),
                    "started_at": payload.get("started_at"),
                    "finished_at": payload.get("finished_at"),
                    "status": payload.get("status"),
                    "source": payload.get("source"),
                    "total_fetched": payload.get("total_fetched", 0),
                    "total_matched": payload.get("total_matched", 0),
                    "duration_seconds": payload.get("duration_seconds"),
                }
            )
        return summaries

    # ------------------------------------------------------------------- helpers
    @staticmethod
    def _atomic_write(path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temp_name = tempfile.mkstemp(
            prefix=path.stem, suffix=".tmp", dir=str(path.parent)
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
