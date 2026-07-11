from __future__ import annotations

import re

from extractors.base import ExtractedReport, Passage, PageText, compute_extraction_status
from extractors import generic


def extract(pages: list[PageText]) -> ExtractedReport:
    result = generic.extract(pages)
    result.extractor_used = "redburn"
    result.low_confidence = False
    # Estimate tables often sit mid-note (pp. 4–8); keep cover + body
    head = "\n".join(p.text for p in pages[:8])

    m = re.search(r"Target price:\s*([A-Z]{3})\s*([\d,\.]+)", head, re.I)
    if m:
        result.target_price = f"{m.group(1)}{m.group(2)}"

    m = re.search(r"remain\s+(Neutral|Overweight|Underweight|Buy|Hold)|We remain\s+(Neutral|Buy|Hold)", head, re.I)
    if m:
        result.rating_change = f"Rating: {m.group(1) or m.group(2)}"
    elif re.search(r"\bNeutral\b", head):
        result.rating_change = "Rating: Neutral"

    m = re.search(r"Ticker:\s*([A-Z0-9]+\s*[A-Z]{0,2})", head)
    # company often before ticker block — Danone style in body
    m = re.search(r"ROTHSCHILD & CO REDBURN\s*\n([A-Za-z][^\n/]{2,40})\s*/", head)
    if m:
        result.company = m.group(1).strip()

    m = re.search(
        rf"Adjusted,? diluted EPS[^\d(]{{0,30}}({generic._EPS_NUM})\s+({generic._EPS_NUM})",
        re.sub(r"\s+", " ", head),
        re.I,
    )
    if m:
        result.broker_eps = [generic._eps_float(m.group(1)), generic._eps_float(m.group(2))]
    elif not result.broker_eps:
        be, ce = generic.parse_eps_numbers(head)
        if be:
            result.broker_eps = be
        if ce and not result.consensus_eps:
            result.consensus_eps = ce

    if not result.key_passages:
        m = re.search(r"(We remain|Our EPS forecasts|operating margin).{40,400}", re.sub(r"\s+", " ", head), re.I)
        if m:
            result.key_passages = [Passage(page=1, text=m.group(0)[:400], label="why_now")]

    result.extraction_status = compute_extraction_status(result)
    return result
