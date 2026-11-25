from datetime import datetime, timedelta

from backend.utils import (
    days_remaining,
    extract_experience_years,
    extract_turnover,
    format_inr,
    normalize_state,
    parse_amount,
    parse_date,
)


def test_parse_amount_indian_formats():
    assert parse_amount("1,00,000.00") == 100_000
    assert parse_amount("₹ 2.5 Lakh") == 250_000
    assert parse_amount("Rs. 1.2 crore") == 12_000_000
    assert parse_amount(50_000) == 50_000
    assert parse_amount("N/A") is None
    assert parse_amount("") is None


def test_format_inr_uses_indian_grouping():
    assert format_inr(1_234_567) == "₹12,34,567"
    assert format_inr(500) == "₹500"
    assert format_inr(None) == "—"


def test_parse_date_and_days_remaining():
    parsed = parse_date("28-01-2026 05:00 PM")
    assert parsed is not None
    assert parsed.year == 2026 and parsed.month == 1 and parsed.day == 28
    assert parsed.hour == 17

    future = datetime.now() + timedelta(days=10)
    assert days_remaining(future.strftime("%d-%m-%Y")) == 10


def test_normalize_state_aliases():
    assert normalize_state("orissa") == "Odisha"
    assert normalize_state("new delhi") == "Delhi"
    assert normalize_state("maharashtra") == "Maharashtra"


def test_extract_requirements_from_text():
    text = "Bidder must have average annual turnover of Rs. 2.5 crore and 3 years of experience."
    assert extract_turnover(text) == 25_000_000
    assert extract_experience_years(text) == 3
