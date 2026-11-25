"""Start the Streamlit frontend.

Usage:
    python run_frontend.py
    python run_frontend.py --port 8502
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the GeM tender brain frontend")
    parser.add_argument("--port", default=os.getenv("BRAIN_UI_PORT", "8501"))
    parser.add_argument("--address", default="127.0.0.1")
    args, extra = parser.parse_known_args()

    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(ROOT / "frontend" / "app.py"),
        "--server.port",
        str(args.port),
        "--server.address",
        args.address,
        "--browser.gatherUsageStats",
        "false",
        *extra,
    ]
    try:
        return subprocess.call(command, cwd=str(ROOT))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
