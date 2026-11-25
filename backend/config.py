"""Environment-driven configuration for the GeM tender brain."""

from __future__ import annotations

import os
from pathlib import Path

try:  # python-dotenv is optional at runtime
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - fallback for minimal installs
    load_dotenv = None  # type: ignore[assignment]

PROJECT_DIR = Path(__file__).resolve().parent.parent

if load_dotenv is not None:
    load_dotenv(PROJECT_DIR / ".env", override=False)


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


DATA_DIR = Path(
    os.getenv(
        "GEM_DATA_DIR",
        os.getenv("BRAIN_DATA_DIR", str(PROJECT_DIR / "data")),
    )
)
RUNS_DIR = DATA_DIR / "runs"
SETTINGS_FILE = DATA_DIR / "settings.json"

HOST = os.getenv("BRAIN_HOST", "127.0.0.1")
PORT = _int_env("BRAIN_PORT", 8000)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
GROQ_MAX_TOKENS = _int_env("GROQ_MAX_TOKENS", 800)
GROQ_REASONING_EFFORT = os.getenv("GROQ_REASONING_EFFORT", "low").strip().lower()
GROQ_ENDPOINT = os.getenv(
    "GROQ_ENDPOINT", "https://api.groq.com/openai/v1/chat/completions"
).strip()

GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "").strip()

GEM_TIMEOUT = _int_env("GEM_TIMEOUT", 30)
GEM_MAX_PAGES = _int_env("GEM_MAX_PAGES", 5)
ALLOW_PLAYWRIGHT_FALLBACK = _bool_env("ALLOW_PLAYWRIGHT_FALLBACK", False)
GEM_SAMPLE_MODE = _bool_env("GEM_SAMPLE_MODE", False)
GEM_SAMPLE_FALLBACK = _bool_env("GEM_SAMPLE_FALLBACK", True)
PDF_MAX_BYTES = _int_env("PDF_MAX_BYTES", 8_000_000)
PDF_MAX_CHARS = _int_env("PDF_MAX_CHARS", 18_000)

for directory in (DATA_DIR, RUNS_DIR):
    directory.mkdir(parents=True, exist_ok=True)


def groq_available() -> bool:
    return bool(GROQ_API_KEY)


def google_available() -> bool:
    return bool(GOOGLE_SERVICE_ACCOUNT_JSON)
