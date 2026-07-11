from __future__ import annotations

import re

from extractors.base import ExtractedReport, Passage, PageText, compute_extraction_status
from extractors import generic


def extract(pages: list[PageText]) -> ExtractedReport:
    result = generic.extract(pages)
    result.extractor_used = "bofa"
    result.low_confidence = False
    head = pages[0].text if pages else ""
    lines = [ln.strip() for ln in head.splitlines() if ln.strip()]

    # Company often after disclaimer block — look for standalone name before sector
    for i, line in enumerate(lines):
        if re.search(r"Price Objective|BofA Securities|129\d{5}", line, re.I):
            for nxt in lines[i + 1 : i + 8]:
                if 2 < len(nxt) < 60 and not re.search(r"Refer to|Employed|FINRA|conflict|page \d", nxt, re.I):
                    result.company = nxt
                    break
            break

    m = re.search(r"Price objective[:\s]*([A-Z]{3})?\s*([\d,\.]+)", head, re.I)
    if m:
        result.target_price = f"{(m.group(1) or '')}{m.group(2)}"

    m = re.search(r"\b(Buy|Neutral|Underperform)\b", head)
    if m:
        result.rating_change = f"Rating: {m.group(1)}"

    if not result.revisions:
        revs = generic.parse_revision_mentions("\n".join(p.text for p in pages[:3]))
        if revs:
            result.revisions = revs

    if not result.key_passages:
        m = re.search(r"(We expect|In our view|Key takeaway).{40,400}", re.sub(r"\s+", " ", head), re.I)
        if m:
            result.key_passages = [Passage(page=1, text=m.group(0)[:400], label="why_now")]

    result.extraction_status = compute_extraction_status(result)
    return result
