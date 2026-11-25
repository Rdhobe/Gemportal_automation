from backend.gem_client import normalize_bid
from backend.models import Tender
from backend.pdf_parser import eligibility_flags, extract_eligibility
from backend.summarizer import rule_based_summary


def test_normalize_gem_row():
    raw = {
        "b_id": "9000000001",
        "b_bid_number": "GEM/2026/B/4200001",
        "b_category_name": "Laptop & Desktop",
        "b_item_category": "Supply of Laptops",
        "b_total_quantity": "120 Nos",
        "b_start_date": "20-11-2026 10:00 AM",
        "b_end_date": "09-12-2026 11:00 PM",
        "b_opening_date": "10-12-2026 11:00 AM",
        "b_estimated_bid_value": "24,00,000.00",
        "b_emd": "48,000.00",
        "b_bid_type": "Product",
        "ba_official_details_deptName": "Directorate of Higher Education",
        "ba_official_details_minName": "Ministry of Education",
        "ba_official_details_state": "Delhi",
    }
    tender = normalize_bid(raw)
    assert tender is not None
    assert tender.bid_number == "GEM/2026/B/4200001"
    assert tender.estimated_value == 2_400_000
    assert tender.emd == 48_000
    assert tender.state == "Delhi"
    assert tender.days_remaining is not None
    assert tender.link.endswith("9000000001")
    assert "09 Dec 2026" in tender.end_date


def test_normalize_empty_row_returns_none():
    assert normalize_bid({}) is None


def test_eligibility_extraction_and_flags():
    text = (
        "Bidder must have minimum 3 years of experience in software projects. "
        "Average annual turnover of Rs. 2 crore is required. MSE relaxation is applicable. "
        "OEM authorisation certificate required. Offer validity: 90 days. EMD: Rs. 50,000."
    )
    eligibility = extract_eligibility(text)
    assert eligibility["Experience"] == "3+ years mentioned"
    assert "Turnover" in eligibility
    assert "Relaxation appears to apply" in eligibility["MSE relaxation"]
    assert "OEM / authorisation" in eligibility

    flags = eligibility_flags(eligibility, text)
    assert any("High turnover" in flag for flag in flags)
    assert any("OEM" in flag for flag in flags)


def test_rule_based_summary_uses_rupees_for_emd():
    tender = Tender(
        bid_number="GEM/2026/B/2",
        title="Comprehensive AMC for Computers",
        category="AMC",
        category_group="it",
        department="District Office",
        state="Gujarat",
        estimated_value=480_000,
        emd=9_600,
        end_date="05 Dec 2026",
        days_remaining=10,
    )
    summary = rule_based_summary(tender)
    assert "an IT tender" in summary
    assert "₹4.80 L" in summary
    assert "₹9,600" in summary
