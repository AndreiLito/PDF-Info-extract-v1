from __future__ import annotations

import re

from extractors.base import ExtractedReport, PageText, compute_extraction_status, find_passages


def _extract_company(head: str) -> str:
    m = re.search(r"Company\s*\n\s*([^\n]+)", head)
    if m:
        return m.group(1).strip()
    m2 = re.search(r"\n([A-Za-z][^\n]{3,60})\nPage 2", head)
    if m2:
        return m2.group(1).strip()
    return ""


def _parse_target_price(head: str) -> str:
    m = re.search(r"Price Target\s*\(([A-Z]{3})\)\s*\n?([\d,\.]+)", head, re.I)
    if m:
        return f"{m.group(1)}{m.group(2).replace(',', '')}"
    return ""


def _parse_rating(head: str) -> str:
    m = re.search(r"Rating\s*\n\s*(Buy|Sell|Hold|Neutral)", head, re.I)
    return m.group(1) if m else ""


def extract(pages: list[PageText]) -> ExtractedReport:
    head = pages[0].text if pages else ""
    full = "\n".join(p.text for p in pages)

    company = _extract_company(head)
    target_price = _parse_target_price(head)
    rating = _parse_rating(head)

    passages = find_passages(
        pages,
        [
            ("why_now", r"(?:Strong Africa|We provide|In this report).{40,500}"),
            ("drivers", r"(?:We see|Notable highs|extrapolation).{30,400}"),
            ("results", r"(?:Q4|FY26|reported group).{30,400}"),
        ],
    )

    result = ExtractedReport(
        pages=pages,
        revisions=[],
        rating_change=f"Rating: {rating}" if rating else "",
        target_price=target_price,
        key_passages=passages,
        full_text=full,
        company=company,
        extractor_used="deutsche_bank",
        low_confidence=True,
    )
    result.extraction_status = compute_extraction_status(result)
    return result
