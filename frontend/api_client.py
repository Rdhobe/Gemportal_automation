"""Thin HTTP client used by the Streamlit frontend."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import requests

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
except ImportError:  # pragma: no cover - dotenv is in requirements
    pass


class ApiError(RuntimeError):
    """Raised for backend connection or API errors."""


class BrainApi:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or os.getenv("BRAIN_API_URL", "http://127.0.0.1:8000")).rstrip("/")
        self.session = requests.Session()

    def _request(
        self,
        method: str,
        path: str,
        *,
        timeout: float = 30,
        **kwargs: Any,
    ) -> Any:
        url = f"{self.base_url}{path}"
        try:
            response = self.session.request(method, url, timeout=timeout, **kwargs)
        except requests.RequestException as exc:
            raise ApiError(
                f"Backend is not reachable at {self.base_url}. "
                "Start it with `python run_backend.py`."
            ) from exc

        if response.status_code >= 400:
            detail = response.text
            try:
                payload = response.json()
                detail = payload.get("detail", detail)
            except ValueError:
                pass
            raise ApiError(f"{response.status_code}: {detail}")
        if not response.content:
            return None
        return response.json()

    def ping(self) -> bool:
        try:
            self._request("GET", "/api/health", timeout=3)
            return True
        except ApiError:
            return False

    def health(self) -> dict:
        return self._request("GET", "/api/health", timeout=5)

    def meta(self) -> dict:
        return self._request("GET", "/api/meta", timeout=10)

    def get_settings(self) -> dict:
        return self._request("GET", "/api/settings", timeout=10)

    def save_settings(self, settings: dict) -> dict:
        return self._request("PUT", "/api/settings", json=settings, timeout=20)

    def start_run(self, settings: dict, use_sample: bool = False) -> dict:
        return self._request(
            "POST",
            "/api/run",
            json={"settings": settings, "use_sample": use_sample},
            timeout=30,
        )

    def run_status(self) -> dict:
        return self._request("GET", "/api/run/status", timeout=10)

    def latest_run(self) -> dict | None:
        try:
            return self._request("GET", "/api/runs/latest", timeout=15)
        except ApiError as exc:
            if "404" in str(exc):
                return None
            raise

    def get_run(self, run_id: str) -> dict:
        return self._request("GET", f"/api/runs/{run_id}", timeout=30)

    def list_runs(self, limit: int = 25) -> list[dict]:
        return self._request("GET", "/api/runs", params={"limit": limit}, timeout=15)

    def export(self, run_id: str | None = None) -> dict:
        payload = {"run_id": run_id} if run_id else {}
        return self._request("POST", "/api/export", json=payload, timeout=180)
