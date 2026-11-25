"""Start the FastAPI backend.

Usage:
    python run_backend.py
    python run_backend.py --reload --port 8001
"""

from __future__ import annotations

import argparse

import uvicorn

from backend.config import HOST, PORT


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the GeM tender brain backend")
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--reload", action="store_true", help="Auto-reload on code changes")
    args = parser.parse_args()

    uvicorn.run(
        "backend.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
