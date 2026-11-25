"""Relevance classification, hard filters, and explainable scoring."""

from __future__ import annotations

import re

from .constants import RISK_KEYWORDS
from .models import ScoreLine, Settings, Tender
from .utils import extract_turnover, normalize_state, state_matches


def _keyword_pattern(keyword: str) -> re.Pattern[str]:
    escaped = re.escape(keyword.lower())
    if len(keyword) <= 4:
        return re.compile(rf"\b{escaped}\b")
    return re.compile(escaped)


def match_keywords(text: str, keywords: list[str]) -> list[str]:
    """Return the configured keywords present in ``text``."""
    lowered = text.lower()
    hits: list[str] = []
    for keyword in keywords:
        keyword = keyword.strip()
        if not keyword:
            continue
        if _keyword_pattern(keyword).search(lowered):
            hits.append(keyword)
    return hits


def _category_hit(text: str, categories: list[str]) -> str | None:
    lowered = text.lower()
    for category in categories:
        normalized = category.lower().strip()
        if normalized and normalized in lowered:
            return category
        words = [
            word
            for word in re.findall(r"[a-z]+", normalized)
            if len(word) >= 4 and word not in {"services", "service", "management"}
        ]
        for word in words:
            if re.search(rf"\b{re.escape(word)}\b", lowered):
                return category
    return None


def classify(tender: Tender, settings: Settings) -> tuple[str, list[str], str | None]:
    """Classify as ``it``/``other``/``unknown`` with matched keywords and category."""
    text = f"{tender.title} {tender.category} {tender.raw_category}"
    it_keywords = match_keywords(text, settings.keywords_it)
    other_keywords = match_keywords(text, settings.keywords_other)
    it_category = _category_hit(text, settings.categories_it)
    other_category = _category_hit(text, settings.categories_other)

    it_weight = len(it_keywords) * 2 + (3 if it_category else 0)
    other_weight = len(other_keywords) * 2 + (3 if other_category else 0)

    if it_weight == 0 and other_weight == 0:
        return "unknown", [], None
    if it_weight >= other_weight:
        tender.matched_keywords = it_keywords
        return "it", it_keywords, it_category
    tender.matched_keywords = other_keywords
    return "other", other_keywords, other_category


def filter_tender(tender: Tender, settings: Settings) -> tuple[bool, str]:
    """Apply hard filters. Returns ``(eligible, reject_reason)``."""
    text = f"{tender.title} {tender.category} {tender.raw_category}".lower()

    for keyword in settings.exclude_keywords:
        if keyword and keyword.lower() in text:
            return False, f"excluded keyword: {keyword}"

    if tender.days_remaining is not None and tender.days_remaining < settings.min_days_remaining:
        return False, "closing too soon"

    group, _, _ = classify(tender, settings)
    if group == "unknown":
        return False, "not relevant to configured categories"

    limit = settings.max_value_it if group == "it" else settings.max_value_other
    if tender.estimated_value is not None and tender.estimated_value > limit:
        return False, "value above limit"

    if tender.emd is not None and tender.emd > settings.max_emd:
        return False, "EMD above limit"

    if settings.bid_types and tender.bid_type and not any(
        tender.bid_type.lower() == item.lower() for item in settings.bid_types
    ):
        return False, "bid type mismatch"

    if settings.region and settings.region.lower() != "all india":
        allowed = {normalize_state(settings.region).lower()}
        allowed.update(normalize_state(state).lower() for state in settings.preferred_states)
        if tender.state and tender.state.lower() not in allowed:
            return False, "outside selected region"

    return True, ""


def score_tender(tender: Tender, settings: Settings) -> Tender:
    """Score an eligible tender and attach an explainable breakdown."""
    group, keywords, category_hit = classify(tender, settings)
    text = f"{tender.title} {tender.category} {tender.raw_category}"
    lines: list[ScoreLine] = []

    def add(reason: str, points: float) -> None:
        if points:
            lines.append(ScoreLine(reason=reason, points=round(points, 1)))

    tender.category_group = group  # type: ignore[assignment]
    tender.matched_keywords = keywords

    add("Relevant category match", 10)
    if group == "it":
        add("IT focus (company priority)", 5)
    if category_hit:
        add(f"Category: {category_hit}", 22)
    if keywords:
        keyword_points = min(len(keywords) * 11, 33)
        shown = ", ".join(keywords[:4])
        add(f"Keyword matches: {shown}", keyword_points)

    limit = settings.max_value_it if group == "it" else settings.max_value_other
    if tender.estimated_value is not None:
        ratio = tender.estimated_value / limit if limit else 1
        if ratio <= 0.35:
            add("Well below value limit", 8)
        elif ratio <= 0.7:
            add("Comfortably below value limit", 5)
        elif ratio <= 0.9:
            add("Within value limit", 2)

    if tender.emd is not None:
        if tender.emd == 0:
            add("No EMD required", 8)
        elif tender.emd <= settings.max_emd * 0.5:
            add("Low EMD", 5)
        elif tender.emd <= settings.max_emd:
            add("EMD within limit", 2)
    else:
        add("EMD not listed yet", 1)

    if tender.state:
        if settings.preferred_states and any(
            state_matches(tender.state, state) for state in settings.preferred_states
        ):
            add(f"Preferred state: {tender.state}", 14)
        elif settings.region and settings.region.lower() != "all india":
            if state_matches(tender.state, settings.region):
                add(f"Inside selected region: {tender.state}", 8)
        else:
            add("All-India location", 2)

    if tender.days_remaining is not None:
        if tender.days_remaining >= settings.min_days_remaining + 7:
            add("Good time to prepare", 4)
        elif tender.days_remaining <= settings.min_days_remaining + 2:
            add("Tight submission window", -3)

    if tender.department:
        add("Buyer department identified", 2)

    # ------------------------------------------------------------- penalties
    for keyword, penalty in RISK_KEYWORDS.items():
        if re.search(rf"\b{re.escape(keyword)}\b", text.lower()):
            add(f"Requires work outside our scope: {keyword}", -penalty)

    turnover = extract_turnover(text)
    if turnover:
        if turnover >= 50_000_000:
            add("Very high turnover requirement", -25)
        elif turnover >= 10_000_000:
            add("High turnover requirement", -14)
        elif turnover >= 5_000_000:
            add("Moderate turnover requirement", -7)

    if re.search(r"\b[5-9]\+?\s*years?\b[^.\n]{0,25}experience", text, re.IGNORECASE):
        add("Long experience requirement", -8)

    if re.search(r"\boem\b|authori[sz]ation certificate|authorised dealer", text, re.IGNORECASE):
        add("OEM / authorisation may be required", -4)
        label = "OEM or authorisation certificate"
        if label not in tender.eligibility_flags:
            tender.eligibility_flags.append(label)

    total = sum(line.points for line in lines)
    tender.score = round(max(total, 0), 1)
    tender.score_breakdown = lines

    if not tender.summary:
        tender.summary = ""
    return tender


def prepare_tenders(
    tenders: list[Tender], settings: Settings
) -> tuple[list[Tender], dict[str, int]]:
    """Filter, score, and sort a batch. Also returns rejection counts by reason."""
    rejections: dict[str, int] = {}
    matched: list[Tender] = []
    for tender in tenders:
        eligible, reason = filter_tender(tender, settings)
        if not eligible:
            rejections[reason] = rejections.get(reason, 0) + 1
            continue
        scored = score_tender(tender, settings)
        if scored.score < settings.min_score:
            rejections["score below threshold"] = (
                rejections.get("score below threshold", 0) + 1
            )
            continue
        matched.append(scored)
    matched.sort(key=lambda item: (-item.score, item.days_remaining or 9999))
    return matched, rejections
