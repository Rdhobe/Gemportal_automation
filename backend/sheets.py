"""Google Sheets export using gspread (optional, configured via env)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import config
from .models import RunRecord, Settings
from .utils import format_inr

TENDER_HEADERS = [
    "Score",
    "Bid Number",
    "Title",
    "Category",
    "Group",
    "Buyer",
    "Ministry",
    "State",
    "Quantity",
    "Start Date",
    "End Date",
    "Days Left",
    "Estimated Value",
    "EMD",
    "Offer Validity",
    "Bid Type",
    "Summary",
    "Eligibility Checks",
    "Matched Keywords",
    "Link",
    "PDF",
    "PDF Parsed",
]


class SheetsError(RuntimeError):
    """Raised when the Google Sheets export cannot be completed."""


def _load_client() -> Any:
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise SheetsError(
            "gspread/google-auth are not installed. Run: pip install gspread google-auth"
        ) from exc

    raw = config.GOOGLE_SERVICE_ACCOUNT_JSON
    if not raw:
        raise SheetsError("GOOGLE_SERVICE_ACCOUNT_JSON is not configured")

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    candidate: Path | None = None
    if not raw.lstrip().startswith("{"):
        try:
            possible = Path(raw)
            if possible.exists():
                candidate = possible
        except OSError:
            candidate = None
    if candidate is not None:
        credentials = Credentials.from_service_account_file(str(candidate), scopes=scopes)
    else:
        try:
            info = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SheetsError(
                "GOOGLE_SERVICE_ACCOUNT_JSON must be a JSON string or a file path"
            ) from exc
        credentials = Credentials.from_service_account_info(info, scopes=scopes)
    return gspread.authorize(credentials)


def _open_spreadsheet(client: Any, sheet_id: str) -> Any:
    try:
        return client.open_by_key(sheet_id)
    except Exception:
        if sheet_id.startswith("http"):
            return client.open_by_url(sheet_id)
        raise


def _get_or_create(workbook: Any, title: str, rows: int, cols: int) -> Any:
    try:
        return workbook.worksheet(title)
    except Exception:  # noqa: BLE001 - gspread raises WorksheetNotFound
        return workbook.add_worksheet(title=title, rows=rows, cols=cols)


def _settings_rows(settings: Settings) -> list[list[str]]:
    return [
        ["Setting", "Value"],
        ["Region", settings.region],
        ["Preferred states", ", ".join(settings.preferred_states)],
        ["Max IT tender value (INR)", f"{settings.max_value_it:,}"],
        ["Max other tender value (INR)", f"{settings.max_value_other:,}"],
        ["Max EMD (INR)", f"{settings.max_emd:,}"],
        ["Minimum days remaining", str(settings.min_days_remaining)],
        ["Minimum score", str(settings.min_score)],
        ["IT categories", ", ".join(settings.categories_it)],
        ["Other categories", ", ".join(settings.categories_other)],
        ["IT keywords", ", ".join(settings.keywords_it)],
        ["Other keywords", ", ".join(settings.keywords_other)],
        ["Excluded keywords", ", ".join(settings.exclude_keywords)],
        ["Bid types", ", ".join(settings.bid_types) or "All"],
        ["Pages fetched", str(settings.max_pages)],
        ["PDF parsing top N", str(settings.parse_pdf_top_n)],
        ["AI summary top N", str(settings.summarize_top_n)],
        ["AI summaries enabled", "Yes" if settings.enable_ai_summary else "No"],
        ["PDF parsing enabled", "Yes" if settings.enable_pdf else "No"],
    ]


def _tender_rows(run: RunRecord) -> list[list[Any]]:
    rows: list[list[Any]] = [TENDER_HEADERS]
    for tender in run.tenders:
        rows.append(
            [
                tender.score,
                tender.bid_number,
                tender.title,
                tender.category,
                tender.category_group,
                tender.department,
                tender.ministry,
                tender.state,
                tender.quantity,
                tender.start_date,
                tender.end_date,
                tender.days_remaining if tender.days_remaining is not None else "",
                format_inr(tender.estimated_value),
                format_inr(tender.emd) if tender.emd is not None else "Not listed",
                tender.offer_validity,
                tender.bid_type,
                tender.summary,
                " | ".join(tender.eligibility_flags),
                ", ".join(tender.matched_keywords),
                tender.link,
                tender.pdf_url,
                "Yes" if tender.pdf_parsed else "No",
            ]
        )
    return rows


def export_run(run: RunRecord, settings: Settings) -> dict[str, Any]:
    """Write Settings and Tenders tabs. Returns a status dict for the API/UI."""
    sheet_id = (settings.sheet_id or config.GOOGLE_SHEET_ID).strip()
    if not sheet_id:
        return {
            "status": "skipped",
            "reason": "No Google Sheet ID configured (Settings tab or GOOGLE_SHEET_ID).",
        }
    if not config.GOOGLE_SERVICE_ACCOUNT_JSON:
        return {
            "status": "skipped",
            "reason": "GOOGLE_SERVICE_ACCOUNT_JSON is not configured.",
        }

    try:
        client = _load_client()
        workbook = _open_spreadsheet(client, sheet_id)

        settings_sheet = _get_or_create(workbook, "Settings", rows=40, cols=4)
        settings_sheet.clear()
        settings_sheet.update(values=_settings_rows(settings), range_name="A1")
        settings_sheet.format(
            "A1:B1",
            {"textFormat": {"bold": True}, "backgroundColor": {"red": 0.9, "green": 0.93, "blue": 0.97}},
        )
        settings_sheet.format("A1:A20", {"textFormat": {"bold": True}})

        tab_name = settings.sheet_tab.strip() or "Tenders"
        tender_sheet = _get_or_create(workbook, tab_name, rows=len(run.tenders) + 20, cols=len(TENDER_HEADERS))
        tender_sheet.clear()
        rows = _tender_rows(run)
        tender_sheet.update(values=rows, range_name="A1")
        tender_sheet.freeze(rows=1)
        tender_sheet.format(
            "A1:V1",
            {
                "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                "backgroundColor": {"red": 0.13, "green": 0.31, "blue": 0.55},
            },
        )

        return {
            "status": "ok",
            "spreadsheet_url": f"https://docs.google.com/spreadsheets/d/{workbook.id}",
            "rows_written": max(len(rows) - 1, 0),
            "settings_written": True,
            "tab": tab_name,
        }
    except Exception as exc:  # noqa: BLE001 - report, don't crash the run
        return {"status": "error", "reason": str(exc)}
