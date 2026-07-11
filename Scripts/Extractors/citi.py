from __future__ import annotations

import re

from extractors.base import ExtractedReport, Passage, PageText, compute_extraction_status
from extractors import generic


def extract(pages: list[PageText]) -> ExtractedReport:
    result = generic.extract(pages)
    result.extractor_used = "citi"
    result.low_confidence = False
    head = pages[0].text if pages else ""
    norm = re.sub(r"\s+", " ", head)

    m = re.search(r"([A-Za-z][A-Za-z0-9&\.\-'\s]{2,40})\s*\(([A-Z0-9]+\.[A-Z])\)", head)
    if m:
        result.company = m.group(1).strip()
    # Allow mixed-case tickers: NOVOb.CO
    if not result.company:
        m = re.search(r"([A-Za-z][A-Za-z0-9&\.\-/'+\s]{2,50})\s*\(([A-Za-z0-9]{2,8}\.[A-Z]{1,3})\)", head)
        if m and not re.search(r"appendix|disclosure|certification", m.group(1), re.I):
            result.company = m.group(1).strip()

    m = re.search(r"\b(Buy|Sell|Neutral|High Risk)\b", head)
    if m:
        result.rating_change = f"Rating: {m.group(1)}"

    # Citi often uses Flash notes without classic TP on page 1
    m = re.search(r"Target\s*[Pp]rice[:\s]*([\d,\.]+)", head)
    if m:
        result.target_price = m.group(1)

    if not result.revisions:
        revs = generic.parse_revision_mentions("\n".join(p.text for p in pages[:3]))
        if revs:
            result.revisions = revs

    if not result.key_passages:
        m = re.search(r"(CITI.?S TAKE|Post close|We expect).{40,500}", norm, re.I)
        if m:
            result.key_passages = [Passage(page=1, text=m.group(0)[:400], label="why_now")]

    result.extraction_status = compute_extraction_status(result)
    return result
