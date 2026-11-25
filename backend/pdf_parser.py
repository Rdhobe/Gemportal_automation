"""Tender PDF retrieval and eligibility extraction."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

import requests

from . import config
from .models import Tender
from .utils import (
    clean_text,
    extract_experience_years,
    extract_turnover,
    format_inr,
    parse_amount,
    truncate,
)

PDF_LINK_RE = re.compile(r"""(?:href|src)=["']([^"']+?\.pdf[^"']*)["']""", re.IGNORECASE)
PDF_URL_RE = re.compile(r"""https?://[^"'\s<>]+\.pdf""", re.IGNORECASE)


@dataclass
class PdfResult:
    text: str = ""
    eligibility: dict[str, str] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)
    emd: float | None = None
    estimated_value: float | None = None
    offer_validity: str = ""
    pdf_url: str = ""
    parsed: bool = False
    error: str = ""


def _session(session: requests.Session | None) -> requests.Session:
    if session is not None:
        return session
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            ),
            "Accept": "application/pdf,text/html;q=0.9,*/*;q=0.8",
            "Referer": "https://bidplus.gem.gov.in/all-bids",
        }
    )
    return session


def resolve_pdf_url(tender: Tender, session: requests.Session | None = None) -> str:
    """Return a direct PDF URL, inspecting the bid detail page when needed."""
    if tender.pdf_url and ".pdf" in tender.pdf_url.lower():
        return tender.pdf_url

    http = _session(session)
    try:
        response = http.get(tender.link, timeout=config.GEM_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"Could not open bid page: {exc}") from exc

    html = response.text
    for pattern in (PDF_LINK_RE, PDF_URL_RE):
        match = pattern.search(html)
        if match:
            url = match.group(1) if match.lastindex else match.group(0)
            if url.startswith("//"):
                url = "https:" + url
            elif url.startswith("/"):
                url = "https://bidplus.gem.gov.in" + url
            return url.replace("&amp;", "&")
    raise RuntimeError("No PDF link found on the bid page")


def download_pdf(url: str, session: requests.Session | None = None) -> bytes:
    """Download a tender PDF with a hard size cap."""
    http = _session(session)
    with http.get(url, timeout=config.GEM_TIMEOUT, stream=True) as response:
        response.raise_for_status()
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_content(chunk_size=65_536):
            if not chunk:
                continue
            total += len(chunk)
            if total > config.PDF_MAX_BYTES:
                raise RuntimeError("PDF is larger than the configured size limit")
            chunks.append(chunk)
    data = b"".join(chunks)
    if not data.startswith(b"%PDF"):
        raise RuntimeError("Downloaded document is not a PDF")
    return data


def extract_text(pdf_bytes: bytes) -> str:
    """Extract text with pdfplumber, capped for downstream prompts."""
    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("pdfplumber is not installed") from exc

    parts: list[str] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages[:25]:
            page_text = page.extract_text() or ""
            if page_text:
                parts.append(page_text)
    return truncate("\n".join(parts), config.PDF_MAX_CHARS)


def _find_amount(text: str, labels: str) -> float | None:
    pattern = rf"(?:{labels})[^\n]{{0,80}}?(?:rs\.?|₹|inr)?\s*([\d][\d,]*(?:\.\d+)?(?:\s*(?:lakh|lac|crore|cr))?)"
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return parse_amount(match.group(1)) if match else None


def extract_eligibility(text: str) -> dict[str, str]:
    """Heuristically pull the eligibility points listed in the project brief."""
    eligibility: dict[str, str] = {}

    experience = extract_experience_years(text)
    if experience:
        eligibility["Experience"] = f"{experience}+ years mentioned"

    turnover = extract_turnover(text)
    if turnover:
        eligibility["Turnover"] = f"{format_inr(turnover)} annual turnover mentioned"

    if re.search(r"\bMSE\b|micro\s+and\s+small|udyam", text, re.IGNORECASE):
        relaxed = re.search(
            r"(?:MSE|micro\s+and\s+small|udyam)[^.\n]{0,120}?(?:relax|exempt|exemption)",
            text,
            re.IGNORECASE,
        )
        eligibility["MSE relaxation"] = (
            "Relaxation appears to apply" if relaxed else "MSE mentioned — verify relaxation"
        )

    if re.search(r"\bstartup\b", text, re.IGNORECASE):
        relaxed = re.search(
            r"startup[^.\n]{0,120}?(?:relax|exempt|exemption)", text, re.IGNORECASE
        )
        eligibility["Startup relaxation"] = (
            "Relaxation appears to apply" if relaxed else "Startup mentioned — verify relaxation"
        )

    if re.search(r"\bOEM\b|authori[sz]ation certificate|authorised dealer", text, re.IGNORECASE):
        eligibility["OEM / authorisation"] = "Certificate or OEM authorisation mentioned"

    validity = re.search(
        r"offer\s+validity[^.\n]{0,80}", text, flags=re.IGNORECASE
    )
    if validity:
        eligibility["Offer validity"] = clean_text(validity.group(0))

    return eligibility


def eligibility_flags(eligibility: dict[str, str], text: str = "") -> list[str]:
    """Turn extracted eligibility into short action-oriented checkpoints."""
    flags: list[str] = []
    turnover = extract_turnover(text) if text else None
    experience = extract_experience_years(text) if text else None
    for key, value in eligibility.items():
        if key == "Turnover":
            if turnover and turnover >= 10_000_000:
                flags.append(f"High turnover requirement ({value})")
            else:
                flags.append(f"Check turnover: {value}")
        elif key == "Experience":
            if experience and experience >= 5:
                flags.append(f"Long experience requirement ({experience}+ years)")
            else:
                flags.append(f"Check experience: {value}")
        elif key == "OEM / authorisation":
            flags.append("OEM or authorisation certificate may be required")
        elif key == "MSE relaxation" and "appears" not in value:
            flags.append("Confirm MSE relaxation")
        elif key == "Startup relaxation" and "appears" not in value:
            flags.append("Confirm startup relaxation")
    return list(dict.fromkeys(flags))


def parse_tender_pdf(
    tender: Tender,
    session: requests.Session | None = None,
    max_chars: int | None = None,
) -> PdfResult:
    """Resolve, download, and parse a tender PDF. Never raises."""
    result = PdfResult()
    http = _session(session)
    try:
        result.pdf_url = resolve_pdf_url(tender, http)
        pdf_bytes = download_pdf(result.pdf_url, http)
        text = extract_text(pdf_bytes)
        if max_chars:
            text = truncate(text, max_chars)
        result.text = text
        result.eligibility = extract_eligibility(text)
        result.flags = eligibility_flags(result.eligibility, text)
        result.emd = _find_amount(text, r"EMD|earnest money")
        result.estimated_value = _find_amount(
            text, r"estimated\s+(?:bid\s+)?value|bid\s+value"
        )
        validity = re.search(r"offer\s+validity[^.\n]{0,80}", text, re.IGNORECASE)
        if validity:
            result.offer_validity = clean_text(validity.group(0))
        result.parsed = bool(text)
        if not text:
            result.error = "PDF had no extractable text (possibly scanned)"
    except Exception as exc:  # noqa: BLE001 - enrichment must never break a run
        result.error = str(exc)
    return result


def apply_pdf_result(tender: Tender, result: PdfResult) -> Tender:
    """Merge parsed PDF data back into a tender."""
    tender.pdf_url = result.pdf_url or tender.pdf_url
    tender.pdf_parsed = result.parsed
    tender.eligibility.update(result.eligibility)
    for flag in result.flags:
        if flag not in tender.eligibility_flags:
            tender.eligibility_flags.append(flag)
    if result.offer_validity and not tender.offer_validity:
        tender.offer_validity = result.offer_validity
    if result.emd is not None and tender.emd is None:
        tender.emd = result.emd
    if result.estimated_value is not None and tender.estimated_value is None:
        tender.estimated_value = result.estimated_value
    return tender
