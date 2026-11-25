"""Command-line entry point, also used by the GitHub Actions workflow."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from .models import Settings
from .pipeline import Pipeline, export_existing_run
from .storage import Storage
from .utils import format_inr

CSV_COLUMNS = [
    "score",
    "bid_number",
    "title",
    "category",
    "group",
    "buyer",
    "state",
    "end_date",
    "days_remaining",
    "estimated_value",
    "emd",
    "summary",
    "eligibility",
    "link",
]


def _print_table(record) -> None:
    print(f"\nRun {record.run_id} — {record.status} — source: {record.source or 'n/a'}")
    print(
        f"Fetched {record.total_fetched} | matched {record.total_matched} | "
        f"{record.duration_seconds}s"
    )
    if record.rejections:
        print("Rejections:", ", ".join(f"{k}={v}" for k, v in record.rejections.items()))
    print("-" * 110)
    print(f"{'Score':>5}  {'Days':>4}  {'Value':>12}  {'State':<14}  Bid / title")
    print("-" * 110)
    for tender in record.tenders[:25]:
        days = "-" if tender.days_remaining is None else str(tender.days_remaining)
        print(
            f"{tender.score:>5}  {days:>4}  {format_inr(tender.estimated_value):>12}  "
            f"{(tender.state or '-')[:14]:<14}  {tender.bid_number} | {tender.title[:52]}"
        )
    if len(record.tenders) > 25:
        print(f"... and {len(record.tenders) - 25} more")
    if record.errors:
        print("\nNotes:")
        for error in record.errors:
            print(f"  - {error}")
    if record.sheet:
        print(f"\nGoogle Sheets: {record.sheet}")


def _write_csv(record, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_COLUMNS)
        for tender in record.tenders:
            writer.writerow(
                [
                    tender.score,
                    tender.bid_number,
                    tender.title,
                    tender.category,
                    tender.category_group,
                    tender.department,
                    tender.state,
                    tender.end_date,
                    tender.days_remaining,
                    tender.estimated_value,
                    tender.emd,
                    tender.summary,
                    " | ".join(tender.eligibility_flags),
                    tender.link,
                ]
            )
    print(f"CSV written to {path}")


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, OSError):
            pass

    parser = argparse.ArgumentParser(description="GeM tender brain CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Fetch and score tenders")
    run_parser.add_argument("--sample", action="store_true", help="Use offline sample data")
    run_parser.add_argument("--no-pdf", action="store_true", help="Skip tender PDF parsing")
    run_parser.add_argument("--no-ai", action="store_true", help="Use rule-based summaries")
    run_parser.add_argument("--sheet", action="store_true", help="Export to Google Sheets")
    run_parser.add_argument("--pages", type=int, help="Override number of GeM pages")
    run_parser.add_argument("--csv", type=Path, help="Write results to a CSV file")
    run_parser.add_argument("--json", action="store_true", help="Print full run JSON")

    export_parser = subparsers.add_parser("export", help="Re-export a stored run")
    export_parser.add_argument("--run-id", help="Run ID (defaults to latest)")

    args = parser.parse_args(argv)
    storage = Storage()

    if args.command == "export":
        result = export_existing_run(storage, args.run_id)
        print(json.dumps(result, indent=2))
        return 0 if result.get("status") in {"ok", "skipped"} else 1

    settings = storage.load_settings()
    updates: dict = {}
    if args.sample:
        updates["use_sample_data"] = True
    if args.no_pdf:
        updates["enable_pdf"] = False
    if args.no_ai:
        updates["enable_ai_summary"] = False
    if args.sheet:
        updates["enable_google_sheets"] = True
    if args.pages:
        updates["max_pages"] = max(1, min(args.pages, 50))
    if updates:
        settings = Settings.model_validate({**settings.model_dump(), **updates})

    pipeline = Pipeline(storage)
    try:
        record = pipeline.run(settings)
    except Exception as exc:  # noqa: BLE001
        print(f"Run failed: {exc}", file=sys.stderr)
        return 1

    _print_table(record)
    if args.csv:
        _write_csv(record, args.csv)
    if args.json:
        print(json.dumps(record.model_dump(mode="json"), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
