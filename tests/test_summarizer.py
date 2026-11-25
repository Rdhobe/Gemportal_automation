"""Groq payload and fallback behaviour for tender summaries."""

from __future__ import annotations

from backend import config
from backend.models import Tender
from backend.summarizer import summarize_tender


class FakeResponse:
    def __init__(self, content: str, status_code: int = 200) -> None:
        self._content = content
        self.status_code = status_code
        self.text = content

    def json(self) -> dict:
        return {"choices": [{"message": {"content": self._content}}]}


def make_tender() -> Tender:
    return Tender(
        bid_number="GEM/2026/B/9",
        title="Annual Maintenance of Server Room",
        category="AMC",
        category_group="it",
        department="Indian Institute of Technology",
        state="Tamil Nadu",
        estimated_value=600_000,
        emd=12_000,
        end_date="09 Dec 2026",
        days_remaining=14,
    )


def test_reasoning_model_gets_large_budget_and_low_effort(monkeypatch):
    captured: dict = {}

    def fake_post(url, json, headers, timeout):
        captured.update(json)
        return FakeResponse("A factual summary.")

    monkeypatch.setattr("backend.summarizer.requests.post", fake_post)
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-key")
    monkeypatch.setattr(config, "GROQ_MODEL", "openai/gpt-oss-20b")
    monkeypatch.setattr(config, "GROQ_MAX_TOKENS", 800)
    monkeypatch.setattr(config, "GROQ_REASONING_EFFORT", "low")

    summary, source = summarize_tender(make_tender())

    assert source == "groq"
    assert summary == "A factual summary."
    assert captured["max_tokens"] == 800
    assert captured["reasoning_effort"] == "low"


def test_standard_model_omits_reasoning_effort(monkeypatch):
    captured: dict = {}

    def fake_post(url, json, headers, timeout):
        captured.update(json)
        return FakeResponse("A factual summary.")

    monkeypatch.setattr("backend.summarizer.requests.post", fake_post)
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-key")
    monkeypatch.setattr(config, "GROQ_MODEL", "llama-3.3-70b-versatile")

    summarize_tender(make_tender())

    assert captured["max_tokens"] == 800
    assert "reasoning_effort" not in captured


def test_empty_groq_content_falls_back_to_rules(monkeypatch):
    monkeypatch.setattr(
        "backend.summarizer.requests.post",
        lambda *args, **kwargs: FakeResponse(""),
    )
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-key")

    summary, source = summarize_tender(make_tender())

    assert source == "rules"
    assert "Annual Maintenance of Server Room" in summary
