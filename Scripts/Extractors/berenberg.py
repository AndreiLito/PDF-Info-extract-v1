from __future__ import annotations

import re

from extractors.base import ExtractedReport, Passage, PageText, compute_extraction_status
from extractors import generic


def extract(pages: list[PageText]) -> ExtractedReport:
    result = generic.extract(pages)
    result.extractor_used = "berenberg"
    result.low_confidence = False
    head = pages[0].text if pages else ""

    m = re.match(r"^([A-Za-z][A-Za-z0-9&\.\-'\s]+?)\s*\(([A-Z0-9]+(?:\s+[A-Z]{2})?)", head.strip())
    if m:
        result.company = m.group(1).strip()

    m = re.search(r"Price target:\s*([A-Z]{3})\s*([\d,\.]+)\s*\(([\d,\.]+)\)", head, re.I)
    if not m:
        m = re.search(r"Price target\s*\n\s*([A-Z]{3})\s*([\d,\.]+)", head, re.I)
    if m:
        if m.lastindex >= 3 and m.group(3):
            result.target_price = f"{m.group(1)}{m.group(2)} (was {m.group(1)}{m.group(3)})"
        else:
            # Changes made block
            m2 = re.search(r"Price target:\s*([A-Z]{3})\s*([\d,\.]+)\s*\(([\d,\.]+)\)", head, re.I)
            if m2:
                result.target_price = f"{m2.group(1)}{m2.group(2)} (was {m2.group(1)}{m2.group(3)})"
            else:
                result.target_price = f"{m.group(1)}{m.group(2)}"

    m = re.search(r"Price target:\s*([A-Z]{3})\s*([\d,\.]+)\s*\(([\d,\.]+)\)", head, re.I)
    if m:
        result.target_price = f"{m.group(1)}{m.group(2)} (was {m.group(1)}{m.group(3)})"

    m = re.search(r"\n(HOLD|BUY|SELL)\s*\n", head)
    if m:
        result.rating_change = f"Reiterate {m.group(1).title()}" if "reiterate" in head.lower() else f"Rating: {m.group(1).title()}"

    # estimate change table with old / ∆ %
    norm = re.sub(r"\s+", " ", head)
    if not result.revisions:
        revs = generic.parse_revision_mentions(head)
        if revs:
            result.revisions = revs
    if ("Estimates changes" in head or "Changes made in this note" in head) and not result.revisions:
        for mm in re.finditer(r"(20\d{2})E[^%]{0,40}?([+\-]?\d+\.?\d*)\s*%", norm):
            result.revisions.append(
                {"metric": "Estimate", "fy1": mm.group(1)[-2:], "change_fy1": f"{mm.group(2)}%", "fy2": "", "change_fy2": ""}
            )
            if len(result.revisions) >= 6:
                break

    result.extraction_status = compute_extraction_status(result)
    return result
