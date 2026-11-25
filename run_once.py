"""One-shot runner used by GitHub Actions and cron jobs.

Running with no arguments is the same as `python run_once.py run`.
"""

from __future__ import annotations

import sys

from backend.cli import main

if __name__ == "__main__":
    arguments = sys.argv[1:] or ["run"]
    raise SystemExit(main(arguments))
