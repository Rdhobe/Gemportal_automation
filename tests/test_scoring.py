from backend.models import Settings, Tender
from backend.scoring import classify, filter_tender, prepare_tenders, score_tender


def make_tender(**overrides) -> Tender:
    defaults = {
        "bid_number": "GEM/2026/B/1",
        "title": "Development of Website and Web Portal",
        "category": "Website Development",
        "bid_type": "Service",
        "department": "Municipal Corporation",
        "state": "Maharashtra",
        "days_remaining": 15,
        "estimated_value": 800_000,
        "emd": 0,
        "end_date": "15-12-2026",
    }
    defaults.update(overrides)
    return Tender(**defaults)


def test_classify_it_tender():
    tender = make_tender()
    group, keywords, category = classify(tender, Settings())
    assert group == "it"
    assert "website" in keywords
    assert category == "Website Development"


def test_filter_rejects_excluded_and_over_limit():
    settings = Settings()

    construction = make_tender(title="Construction of office building", category="Civil Works")
    assert filter_tender(construction, settings)[0] is False

    expensive = make_tender(estimated_value=9_000_000)
    assert filter_tender(expensive, settings) == (False, "value above limit")

    high_emd = make_tender(emd=100_000)
    assert filter_tender(high_emd, settings) == (False, "EMD above limit")

    urgent = make_tender(days_remaining=2)
    assert filter_tender(urgent, settings) == (False, "closing too soon")


def test_other_tender_uses_lower_value_cap():
    settings = Settings()
    marketing = make_tender(
        title="Social Media Management for Tourism",
        category="Social Media Management",
        estimated_value=600_000,
    )
    assert filter_tender(marketing, settings)[0] is False

    marketing.estimated_value = 400_000
    assert filter_tender(marketing, settings)[0] is True


def test_score_rewards_preferred_state_and_reports_breakdown():
    settings = Settings(preferred_states=["Maharashtra"])
    tender = score_tender(make_tender(), settings)
    assert tender.score > 0
    assert any("Preferred state" in line.reason for line in tender.score_breakdown)
    assert abs(sum(line.points for line in tender.score_breakdown) - tender.score) < 0.01


def test_prepare_tenders_sorts_by_score_and_tracks_rejections():
    settings = Settings()
    tenders = [
        make_tender(bid_number="LOW", title="Cloud storage subscription", category="Cloud", estimated_value=100_000),
        make_tender(bid_number="HIGH", title="Software development and website portal", category="Software", estimated_value=200_000),
        make_tender(bid_number="DROP", title="Construction and civil work", category="Civil Works"),
    ]
    matched, rejections = prepare_tenders(tenders, settings)
    assert [item.bid_number for item in matched] == ["HIGH", "LOW"]
    assert any("excluded" in reason for reason in rejections)
