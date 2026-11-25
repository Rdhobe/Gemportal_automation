from backend.models import Settings
from backend.pipeline import Pipeline
from backend.storage import Storage


def test_sample_pipeline_end_to_end(tmp_path):
    storage = Storage(tmp_path / "settings.json", tmp_path / "runs")
    settings = Settings(
        use_sample_data=True,
        enable_pdf=False,
        enable_ai_summary=False,
        enable_google_sheets=False,
        min_days_remaining=7,
    )
    record = Pipeline(storage).run(settings, persist=True)

    assert record.status == "done"
    assert record.source == "sample"
    assert record.total_fetched >= 20
    assert record.total_matched >= 10
    assert len(record.tenders) == record.total_matched

    scores = [tender.score for tender in record.tenders]
    assert scores == sorted(scores, reverse=True)

    titles = " ".join(tender.title.lower() for tender in record.tenders)
    assert "construction" not in titles
    assert "security guards" not in titles
    assert "furniture" not in titles

    for tender in record.tenders:
        assert tender.category_group in {"it", "other"}
        assert tender.summary
        if tender.days_remaining is not None:
            assert tender.days_remaining >= 7
        limit = settings.max_value_it if tender.category_group == "it" else settings.max_value_other
        if tender.estimated_value is not None:
            assert tender.estimated_value <= limit
        if tender.emd is not None:
            assert tender.emd <= settings.max_emd

    latest = storage.latest_run()
    assert latest is not None
    assert latest["run_id"] == record.run_id
    assert len(latest["tenders"]) == record.total_matched
