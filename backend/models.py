"""Pydantic models for settings, tenders, and run records."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .constants import (
    DEFAULT_EXCLUDE_KEYWORDS,
    DEFAULT_IT_KEYWORDS,
    DEFAULT_OTHER_KEYWORDS,
    IT_CATEGORIES,
    OTHER_CATEGORIES,
)


def _clean_list(values: list[str] | None) -> list[str]:
    if not values:
        return []
    seen: set[str] = set()
    cleaned: list[str] = []
    for value in values:
        item = str(value).strip()
        key = item.lower()
        if item and key not in seen:
            seen.add(key)
            cleaned.append(item)
    return cleaned


class Settings(BaseModel):
    """User-editable search configuration (mirrors the Google Sheets Settings tab)."""

    model_config = ConfigDict(extra="ignore")

    region: str = "All India"
    preferred_states: list[str] = Field(default_factory=list)

    max_value_it: int = 2_500_000
    max_value_other: int = 500_000
    max_emd: int = 50_000
    min_days_remaining: int = 7

    keywords_it: list[str] = Field(default_factory=lambda: list(DEFAULT_IT_KEYWORDS))
    keywords_other: list[str] = Field(default_factory=lambda: list(DEFAULT_OTHER_KEYWORDS))
    categories_it: list[str] = Field(default_factory=lambda: list(IT_CATEGORIES))
    categories_other: list[str] = Field(default_factory=lambda: list(OTHER_CATEGORIES))
    exclude_keywords: list[str] = Field(default_factory=lambda: list(DEFAULT_EXCLUDE_KEYWORDS))

    bid_types: list[str] = Field(default_factory=list)
    min_score: int = 25
    max_pages: int = 5
    parse_pdf_top_n: int = 10
    summarize_top_n: int = 10

    use_sample_data: bool = False
    enable_pdf: bool = True
    enable_ai_summary: bool = True
    enable_google_sheets: bool = False

    sheet_id: str = ""
    sheet_tab: str = "Tenders"

    @field_validator("preferred_states", "bid_types")
    @classmethod
    def _validate_optional_lists(cls, value: list[str]) -> list[str]:
        return _clean_list(value)

    @field_validator("keywords_it", "keywords_other", "categories_it", "categories_other", "exclude_keywords")
    @classmethod
    def _validate_lists(cls, value: list[str]) -> list[str]:
        return _clean_list(value)

    @field_validator("max_value_it", "max_value_other", "max_emd")
    @classmethod
    def _positive_amount(cls, value: int) -> int:
        if value < 0:
            raise ValueError("Amount limits cannot be negative")
        return value

    @field_validator("max_pages")
    @classmethod
    def _page_limit(cls, value: int) -> int:
        if value < 1 or value > 50:
            raise ValueError("max_pages must be between 1 and 50")
        return value

    @field_validator("parse_pdf_top_n", "summarize_top_n")
    @classmethod
    def _top_n_limit(cls, value: int) -> int:
        if value < 0 or value > 100:
            raise ValueError("Top-N limits must be between 0 and 100")
        return value

    @field_validator("min_days_remaining", "min_score")
    @classmethod
    def _non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("Value cannot be negative")
        return value


class ScoreLine(BaseModel):
    reason: str
    points: float


class Tender(BaseModel):
    bid_number: str
    title: str
    category: str = ""
    category_group: Literal["it", "other", "unknown"] = "unknown"
    bid_type: str = ""
    department: str = ""
    ministry: str = ""
    state: str = ""
    city: str = ""
    quantity: str = ""
    start_date: str = ""
    end_date: str = ""
    opening_date: str = ""
    days_remaining: int | None = None
    estimated_value: float | None = None
    emd: float | None = None
    offer_validity: str = ""
    link: str = ""
    pdf_url: str = ""
    score: float = 0
    score_breakdown: list[ScoreLine] = Field(default_factory=list)
    matched_keywords: list[str] = Field(default_factory=list)
    summary: str = ""
    summary_source: str = ""
    eligibility: dict[str, str] = Field(default_factory=dict)
    eligibility_flags: list[str] = Field(default_factory=list)
    pdf_parsed: bool = False
    raw_category: str = ""
    source: str = "gem"


class RunRecord(BaseModel):
    run_id: str
    started_at: str
    finished_at: str | None = None
    status: Literal["running", "done", "error"] = "running"
    source: str = ""
    settings: Settings
    total_fetched: int = 0
    total_matched: int = 0
    tenders: list[Tender] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    rejections: dict[str, int] = Field(default_factory=dict)
    sheet: dict = Field(default_factory=dict)
    duration_seconds: float | None = None


class RunRequest(BaseModel):
    settings: Settings | None = None
    use_sample: bool = False


class ExportRequest(BaseModel):
    run_id: str | None = None
    settings: Settings | None = None


class RunStatus(BaseModel):
    run_id: str | None = None
    status: Literal["idle", "running", "done", "error"] = "idle"
    progress: int = 0
    stage: str = ""
    message: str = ""
    error: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    matched: int = 0
    fetched: int = 0


class ApiMeta(BaseModel):
    it_categories: list[str]
    other_categories: list[str]
    states: list[str]
    bid_types: list[str]
    groq_available: bool
    google_available: bool
    sample_mode_default: bool


class HealthResponse(BaseModel):
    status: str
    version: str
    time: datetime
    data_dir: str
