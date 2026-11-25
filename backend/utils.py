"""Small parsing and formatting helpers shared by the backend."""

from __future__ import annotations

import math
import re
from datetime import date, datetime
from typing import Any

from .constants import STATE_ALIASES

_DATE_FORMATS = (
    "%d-%m-%Y %I:%M %p",
    "%d-%m-%Y %H:%M",
    "%d/%m/%Y %I:%M %p",
    "%d/%m/%Y %H:%M",
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%d-%b-%Y",
    "%d %b %Y",
    "%d %B %Y",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d",
)

_AMOUNT_WORDS = {
    "crore": 10_000_000,
    "cr": 10_000_000,
    "lakh": 100_000,
    "lakhs": 100_000,
    "lac": 100_000,
    "lacs": 100_000,
}


def clean_text(value: Any) -> str:
    """Return a whitespace-collapsed string for any input."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ", ".join(clean_text(item) for item in value if clean_text(item))
    return re.sub(r"\s+", " ", str(value)).strip()


def parse_amount(value: Any) -> float | None:
    """Parse Indian currency strings such as ``Rs. 2.5 Lakh`` into rupees."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if math.isnan(value) or math.isinf(value) or value < 0:
            return None
        return float(value)

    text = clean_text(value)
    if not text:
        return None
    lowered = text.lower().replace(",", "").replace("₹", "").strip()
    if lowered in {"na", "n/a", "nil", "none", "-", "--", "not applicable"}:
        return None

    match = re.search(r"(\d+(?:\.\d+)?)\s*(crore|cr|lakhs?|lacs?)\b", lowered)
    if match:
        return float(match.group(1)) * _AMOUNT_WORDS[match.group(2)]

    match = re.search(r"\d+(?:\.\d+)?", lowered)
    if not match:
        return None
    return float(match.group(0))


def format_inr(amount: float | None) -> str:
    """Format a number with Indian digit grouping, e.g. ``₹12,34,567``."""
    if amount is None:
        return "—"
    number = round(amount)
    sign = "-" if number < 0 else ""
    digits = str(abs(number))
    if len(digits) <= 3:
        return f"{sign}₹{digits}"
    head, tail = digits[:-3], digits[-3:]
    groups: list[str] = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return f"{sign}₹{','.join(groups + [tail])}"


def format_lakh(amount: float | None) -> str:
    """Format rupees as a short lakh/crore value."""
    if amount is None:
        return "—"
    if amount >= 10_000_000:
        return f"₹{amount / 10_000_000:.2f} Cr"
    return f"₹{amount / 100_000:.2f} L"


def parse_date(value: Any) -> datetime | None:
    """Parse the date formats returned by GeM and PDFs."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    if isinstance(value, (int, float)):
        if value > 10_000_000_000:  # milliseconds
            value = value / 1000
        if value > 1_000_000_000:
            try:
                return datetime.fromtimestamp(value)
            except (OverflowError, OSError, ValueError):
                return None

    text = clean_text(value)
    if not text:
        return None
    text = re.sub(r"\b(IST|GMT|UTC)\b", "", text, flags=re.IGNORECASE).strip()
    text = text.replace("T", " ")

    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo:
            parsed = parsed.replace(tzinfo=None)
        return parsed
    except ValueError:
        pass

    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def human_date(value: Any) -> str:
    """Render a date for the UI."""
    parsed = parse_date(value)
    if not parsed:
        return clean_text(value) or "—"
    if parsed.hour or parsed.minute:
        return parsed.strftime("%d %b %Y, %I:%M %p")
    return parsed.strftime("%d %b %Y")


def days_remaining(end_date: Any) -> int | None:
    """Whole days between today and the closing date."""
    parsed = parse_date(end_date)
    if not parsed:
        return None
    return (parsed.date() - date.today()).days


def normalize_state(value: Any) -> str:
    """Normalize a state name and resolve common aliases."""
    text = clean_text(value)
    if not text:
        return ""
    key = re.sub(r"\s+", " ", text.lower())
    if key in STATE_ALIASES:
        return STATE_ALIASES[key]
    for alias, canonical in STATE_ALIASES.items():
        if key.replace(" and ", " & ") == alias.replace(" and ", " & "):
            return canonical
    return text.title()


def state_matches(candidate: str, target: str) -> bool:
    """Case-insensitive comparison of two state names."""
    if not candidate or not target:
        return False
    return normalize_state(candidate).lower() == normalize_state(target).lower()


def truncate(text: str, limit: int) -> str:
    text = clean_text(text)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rsplit(" ", 1)[0] + "…"


def extract_turnover(text: str) -> float | None:
    """Find an annual-turnover requirement in free text and return rupees."""
    patterns = (
        r"(?:average\s+)?(?:annual\s+)?turnover[^\n]{0,100}?(\d+(?:\.\d+)?)\s*(crore|cr|lakhs?|lacs?)",
        r"(?:turnover)[^\n]{0,40}?rs\.?\s*([\d,]+(?:\.\d+)?)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        if match.lastindex and match.lastindex >= 2 and match.group(2):
            return float(match.group(1).replace(",", "")) * _AMOUNT_WORDS[match.group(2).lower()]
        return float(match.group(1).replace(",", ""))
    return None


def extract_experience_years(text: str) -> int | None:
    """Find an experience requirement such as ``3 years of experience``."""
    match = re.search(
        r"(\d{1,2})\s*(?:\+)?\s*(?:years?|yrs?)[^.\n]{0,40}?(?:experience|past experience)",
        text,
        flags=re.IGNORECASE,
    )
    return int(match.group(1)) if match else None
