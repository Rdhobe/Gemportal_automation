"""GeM bid fetching, normalization, and browser fallback."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

import requests

from . import config
from .constants import GEM_BASE_URL, GEM_BIDS_ENDPOINT, GEM_DETAIL_URL
from .models import Settings, Tender
from .sample_data import sample_bids
from .utils import (
    clean_text,
    days_remaining,
    human_date,
    normalize_state,
    parse_amount,
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

ProgressCallback = Callable[[int, str, str], None]


class GemFetchError(RuntimeError):
    """Raised when GeM cannot be reached or returns an unexpected payload."""


def _first(raw: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in raw:
            value = raw[key]
            if value is not None and value != "" and value != [] and value != {}:
                return value
    return None


def _bid_payload(page: int) -> dict[str, Any]:
    """Request body used by the bidplus.gem.gov.in listing page."""
    return {
        "payload": {
            "page": page,
            "param": {"searchBid": "", "searchType": "fullText"},
            "filter": {
                "bidEndFrom": "",
                "bidEndTo": "",
                "bidOpeningFrom": "",
                "bidOpeningTo": "",
                "state": [],
                "ministry": [],
                "department": [],
                "bidType": "",
                "bidValueFrom": "",
                "bidValueTo": "",
                "category": "",
            },
        },
        "type": "all",
    }


def normalize_bid(raw: dict[str, Any]) -> Tender | None:
    """Map one raw GeM listing row to our Tender model."""
    bid_id = clean_text(_first(raw, "b_id", "bid_id", "id"))
    bid_number = clean_text(
        _first(raw, "b_bid_number", "bid_number", "b_bid_no", "b_id", "id")
    )
    title = clean_text(
        _first(raw, "b_item_category", "b_items", "b_category_name", "title", "item")
    )
    category = clean_text(
        _first(raw, "b_category_name", "b_item_category", "category", "category_name")
    )

    if not bid_number and not title:
        return None

    bid_id = bid_id or bid_number
    detail_url = clean_text(_first(raw, "detail_url", "b_detail_url")) or GEM_DETAIL_URL.format(
        bid_id=bid_id
    )
    pdf_url = clean_text(_first(raw, "b_pdf_url", "pdf_url", "b_document_url", "document_url"))

    end_date = _first(raw, "b_end_date", "b_bid_end_date", "end_date", "bidEndDate")
    start_date = _first(raw, "b_start_date", "b_bid_start_date", "start_date", "bidStartDate")
    opening_date = _first(
        raw, "b_opening_date", "b_bid_opening_date", "opening_date", "bidOpeningDate"
    )

    value = parse_amount(
        _first(
            raw,
            "b_estimated_bid_value",
            "b_bid_value",
            "bid_value",
            "estimated_bid_value",
            "b_value",
        )
    )
    emd = parse_amount(_first(raw, "b_emd", "b_emd_amount", "emd", "emd_amount"))

    return Tender(
        bid_number=bid_number or title,
        title=title or category or "Untitled tender",
        category=category,
        raw_category=category,
        bid_type=clean_text(_first(raw, "b_bid_type", "bid_type", "type")),
        department=clean_text(
            _first(
                raw,
                "ba_official_details_deptName",
                "b_department",
                "department",
                "dept_name",
            )
        ),
        ministry=clean_text(
            _first(raw, "ba_official_details_minName", "b_ministry", "ministry")
        ),
        state=normalize_state(
            _first(raw, "ba_official_details_state", "b_consignee_state", "state")
        ),
        city=clean_text(_first(raw, "ba_official_details_city", "b_consignee_city", "city")),
        quantity=clean_text(_first(raw, "b_total_quantity", "b_quantity", "quantity")),
        start_date=human_date(start_date) if start_date else "",
        end_date=human_date(end_date) if end_date else "",
        opening_date=human_date(opening_date) if opening_date else "",
        days_remaining=days_remaining(end_date),
        estimated_value=value,
        emd=emd,
        offer_validity=clean_text(_first(raw, "b_offer_validity", "offer_validity")),
        link=detail_url,
        pdf_url=pdf_url,
        source="gem",
    )


class GemClient:
    """Fetch live GeM bids with a Playwright fallback for blocked requests."""

    def __init__(self, timeout: int | None = None) -> None:
        self.timeout = timeout or config.GEM_TIMEOUT
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-IN,en;q=0.9",
                "Content-Type": "application/json",
                "Origin": GEM_BASE_URL,
                "Referer": f"{GEM_BASE_URL}/all-bids",
                "X-Requested-With": "XMLHttpRequest",
            }
        )

    # ------------------------------------------------------------------ public
    def fetch_bids(
        self,
        settings: Settings,
        progress: ProgressCallback | None = None,
    ) -> tuple[list[dict[str, Any]], str, list[str]]:
        """Return ``(raw_bids, source, errors)`` for the configured pages."""
        errors: list[str] = []
        if settings.use_sample_data or config.GEM_SAMPLE_MODE:
            if progress:
                progress(10, "sample", "Loading offline sample tenders")
            return sample_bids(), "sample", errors

        try:
            bids = self._fetch_live(settings, progress)
            if not bids:
                raise GemFetchError("GeM returned no bids for the requested pages")
            return bids, "gem", errors
        except Exception as exc:  # noqa: BLE001 - surface any fetch failure to the UI
            errors.append(f"Live GeM fetch failed: {exc}")

        if config.ALLOW_PLAYWRIGHT_FALLBACK:
            try:
                if progress:
                    progress(8, "playwright", "Live API blocked, trying headless browser")
                bids = self._fetch_playwright(settings)
                if bids:
                    return bids, "playwright", errors
                errors.append("Playwright fallback returned no bids")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Playwright fallback failed: {exc}")

        if config.GEM_SAMPLE_FALLBACK:
            errors.append("Showing offline sample tenders instead of live GeM data")
            if progress:
                progress(10, "sample", "Live fetch unavailable — using sample tenders")
            return sample_bids(), "sample", errors

        raise GemFetchError("; ".join(errors) or "Unable to fetch GeM bids")

    # ------------------------------------------------------------------- live
    def _fetch_live(
        self,
        settings: Settings,
        progress: ProgressCallback | None = None,
    ) -> list[dict[str, Any]]:
        bids: list[dict[str, Any]] = []
        for page in range(1, settings.max_pages + 1):
            if progress:
                progress(
                    8 + int(page / settings.max_pages * 10),
                    "fetch",
                    f"Fetching GeM page {page} of {settings.max_pages}",
                )
            try:
                response = self.session.post(
                    GEM_BIDS_ENDPOINT,
                    data=json.dumps(_bid_payload(page)),
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                raise GemFetchError(f"Network error: {exc}") from exc

            if response.status_code in {403, 429}:
                raise GemFetchError(
                    f"GeM blocked the request (HTTP {response.status_code}). "
                    "Enable the Playwright fallback or use sample data."
                )
            if response.status_code >= 400:
                raise GemFetchError(f"GeM returned HTTP {response.status_code}")

            try:
                payload = response.json()
            except ValueError as exc:
                snippet = re.sub(r"\s+", " ", response.text[:160])
                raise GemFetchError(f"GeM returned non-JSON content: {snippet}") from exc

            rows = self._extract_rows(payload)
            if not rows:
                break
            bids.extend(rows)
            if len(rows) < 10:
                break
        return bids

    @staticmethod
    def _extract_rows(payload: Any) -> list[dict[str, Any]]:
        data: Any = payload
        if isinstance(payload, dict):
            data = payload.get("data", payload.get("response", payload.get("result", [])))
            if isinstance(data, dict):
                data = data.get("data", data.get("bids", data.get("docs", [])))
        if isinstance(data, list):
            return [row for row in data if isinstance(row, dict)]
        return []

    # -------------------------------------------------------------- playwright
    def _fetch_playwright(self, settings: Settings) -> list[dict[str, Any]]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise GemFetchError(
                "Playwright is not installed. Run: pip install playwright && playwright install chromium"
            ) from exc

        bids: list[dict[str, Any]] = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(user_agent=USER_AGENT)
            page = context.new_page()
            page.goto(f"{GEM_BASE_URL}/all-bids", wait_until="domcontentloaded", timeout=60_000)
            for index in range(1, settings.max_pages + 1):
                script = """
                    async (payload) => {
                        const response = await fetch(
                            'https://bidplus.gem.gov.in/all-bids-data',
                            {
                                method: 'POST',
                                headers: {
                                    'Content-Type': 'application/json',
                                    'X-Requested-With': 'XMLHttpRequest'
                                },
                                body: JSON.stringify(payload)
                            }
                        );
                        return await response.text();
                    }
                """
                text = page.evaluate(script, _bid_payload(index))
                payload = json.loads(text)
                rows = self._extract_rows(payload)
                if not rows:
                    break
                bids.extend(rows)
                if len(rows) < 10:
                    break
            browser.close()
        return bids
