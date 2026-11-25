"""Tender summaries via Groq with a deterministic offline fallback."""

from __future__ import annotations

import re

import requests

from . import config
from .models import Tender
from .utils import format_inr, format_lakh, truncate

SYSTEM_PROMPT = (
    "You are a bid analyst for a small Indian IT services company. "
    "Write factual, compact tender summaries. Never invent facts that are not "
    "in the provided data. Do not use markdown or bullet points."
)


def rule_based_summary(tender: Tender) -> str:
    """Build a 2-3 line summary without any AI dependency."""
    group = {
        "it": "IT",
        "other": "non-IT",
        "unknown": "general",
    }.get(tender.category_group, "general")
    buyer = tender.department or tender.ministry or "a government buyer"
    location = f", {tender.state}" if tender.state else ""
    value = format_lakh(tender.estimated_value)
    if tender.emd is None:
        emd = "EMD not listed"
    elif tender.emd == 0:
        emd = "no EMD"
    else:
        emd = format_inr(tender.emd)
    closing = tender.end_date or "closing date not listed"
    days = (
        f" ({tender.days_remaining} days left)"
        if tender.days_remaining is not None
        else ""
    )
    article = "an" if group == "IT" else "a"
    summary = (
        f"{tender.title} is {article} {group} tender from {buyer}{location}. "
        f"Estimated value {value} with {emd}; closes {closing}{days}."
    )
    if tender.eligibility_flags:
        summary += f" Main eligibility check: {tender.eligibility_flags[0]}."
    return summary


def _prompt(tender: Tender, pdf_text: str) -> str:
    lines = [
        f"Bid number: {tender.bid_number}",
        f"Item/title: {tender.title}",
        f"Category: {tender.category or 'not listed'}",
        f"Buyer: {tender.department or 'not listed'}"
        + (f" ({tender.ministry})" if tender.ministry else ""),
        f"State: {tender.state or 'not listed'}",
        f"Quantity: {tender.quantity or 'not listed'}",
        f"Estimated value: {format_lakh(tender.estimated_value)}",
        f"EMD: {format_lakh(tender.emd) if tender.emd is not None else 'not listed'}",
        f"Bid end: {tender.end_date or 'not listed'}"
        + (
            f" ({tender.days_remaining} days remaining)"
            if tender.days_remaining is not None
            else ""
        ),
        f"Offer validity: {tender.offer_validity or 'not listed'}",
        f"Eligibility notes: {'; '.join(tender.eligibility_flags) or 'none extracted'}",
    ]
    if pdf_text:
        lines.append("Tender document excerpt:")
        lines.append(truncate(pdf_text, 5_500))
    lines.append(
        "Write a 2-3 sentence summary (max 70 words) covering what is being bought, "
        "who is buying and where, the key commercial terms, and the main eligibility "
        "risk the bidder must verify. Plain text only."
    )
    return "\n".join(lines)


def summarize_tender(tender: Tender, pdf_text: str = "") -> tuple[str, str]:
    """Return ``(summary, source)`` using Groq when configured."""
    if not config.GROQ_API_KEY:
        return rule_based_summary(tender), "rules"

    payload = {
        "model": config.GROQ_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _prompt(tender, pdf_text)},
        ],
        "temperature": 0.2,
        "max_tokens": config.GROQ_MAX_TOKENS,
    }
    # Reasoning models (for example gpt-oss) spend completion tokens on hidden
    # reasoning before writing the answer. Keep that budget low so the visible
    # summary is not truncated. Non-reasoning models reject this parameter.
    if (
        "gpt-oss" in config.GROQ_MODEL.lower()
        and config.GROQ_REASONING_EFFORT in {"low", "medium", "high"}
    ):
        payload["reasoning_effort"] = config.GROQ_REASONING_EFFORT
    try:
        response = requests.post(
            config.GROQ_ENDPOINT,
            json=payload,
            headers={
                "Authorization": f"Bearer {config.GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=45,
        )
        if response.status_code != 200:
            snippet = re.sub(r"\s+", " ", response.text[:180])
            raise RuntimeError(f"Groq HTTP {response.status_code}: {snippet}")
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        summary = re.sub(r"\s+", " ", str(content)).strip().strip('"')
        if not summary:
            raise RuntimeError("Groq returned an empty summary")
        return summary, "groq"
    except Exception:  # noqa: BLE001 - fall back rather than fail the run
        return rule_based_summary(tender), "rules"
