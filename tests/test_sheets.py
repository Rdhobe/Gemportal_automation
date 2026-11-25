"""Google Sheets export logic, exercised without live Google APIs."""

from __future__ import annotations

from backend import config, sheets
from backend.models import RunRecord, Settings, Tender


class FakeSheet:
    def __init__(self, title: str) -> None:
        self.title = title
        self.values: list[list] = []
        self.cleared = False
        self.formatted = False
        self.frozen = False

    def clear(self) -> None:
        self.cleared = True

    def update(self, values, range_name="A1") -> None:
        self.values = values

    def format(self, *args, **kwargs) -> None:
        self.formatted = True

    def freeze(self, rows: int = 1) -> None:
        self.frozen = True


class FakeWorkbook:
    id = "fake-sheet-id"

    def __init__(self) -> None:
        self.tabs: dict[str, FakeSheet] = {}

    def worksheet(self, title: str) -> FakeSheet:
        if title not in self.tabs:
            raise KeyError(title)
        return self.tabs[title]

    def add_worksheet(self, title: str, rows: int, cols: int) -> FakeSheet:
        self.tabs[title] = FakeSheet(title)
        return self.tabs[title]


def make_run(settings: Settings) -> RunRecord:
    tender = Tender(
        bid_number="GEM/2026/B/77",
        title="Supply of Network Switches",
        category="Networking",
        category_group="it",
        department="Public Works Department",
        state="Assam",
        estimated_value=650_000,
        emd=13_000,
        end_date="09 Dec 2026",
        days_remaining=8,
        score=84,
        summary="A networking tender for switches and routers.",
        eligibility_flags=["OEM or authorisation certificate"],
    )
    return RunRecord(
        run_id="test-run",
        started_at="2026-11-25T10:00:00",
        finished_at="2026-11-25T10:00:02",
        status="done",
        source="sample",
        settings=settings,
        total_fetched=1,
        total_matched=1,
        tenders=[tender],
    )


def test_export_writes_settings_and_tender_tabs(monkeypatch):
    workbook = FakeWorkbook()
    monkeypatch.setattr(config, "GOOGLE_SERVICE_ACCOUNT_JSON", "configured")
    monkeypatch.setattr(sheets, "_load_client", lambda: object())
    monkeypatch.setattr(sheets, "_open_spreadsheet", lambda client, sheet_id: workbook)

    settings = Settings(sheet_id="fake-sheet-id", sheet_tab="Tenders")
    result = sheets.export_run(make_run(settings), settings)

    assert result["status"] == "ok"
    assert result["rows_written"] == 1
    assert result["settings_written"] is True
    assert set(workbook.tabs) == {"Settings", "Tenders"}
    assert workbook.tabs["Settings"].values[0] == ["Setting", "Value"]
    assert workbook.tabs["Tenders"].values[0] == sheets.TENDER_HEADERS
    assert workbook.tabs["Tenders"].values[1][1] == "GEM/2026/B/77"
    assert workbook.tabs["Tenders"].frozen is True


def test_export_skips_without_sheet_id(monkeypatch):
    monkeypatch.setattr(config, "GOOGLE_SHEET_ID", "")
    monkeypatch.setattr(config, "GOOGLE_SERVICE_ACCOUNT_JSON", "configured")

    result = sheets.export_run(make_run(Settings()), Settings(sheet_id=""))

    assert result["status"] == "skipped"
    assert "No Google Sheet ID" in result["reason"]
