from __future__ import annotations

import re

from extractors.base import ExtractedReport, Passage, PageText, compute_extraction_status
from extractors import generic


def extract(pages: list[PageText]) -> ExtractedReport:
    result = generic.extract(pages)
    result.extractor_used = "abg_sundal"
    result.low_confidence = False
    head = pages[0].text if pages else ""
    lines = [ln.strip() for ln in head.splitlines() if ln.strip()]

    # Company usually early after date line
    for i, line in enumerate(lines[:15]):
        if re.search(r"Equity Research|Fast comment|CEST|CET", line, re.I):
            continue
        if 2 < len(line) < 50 and not re.search(r"@|http|\d{2}:\d{2}", line):
            if i + 1 < len(lines) and not re.match(r"^[•\-\d]", lines[i + 1]):
                result.company = line
                break

    m = re.search(r"Target price\s*\n?\s*([\d,\.]+)", head, re.I)
    if m:
        # currency often SEK nearby via share price
        ccy = "SEK"
        if "NOK" in head[:1500]:
            ccy = "NOK"
        if "DKK" in head[:1500]:
            ccy = "DKK"
        result.target_price = f"{ccy}{m.group(1)}"

    m = re.search(r"\n(HOLD|BUY|SELL)\s*\n", head)
    if m:
        result.rating_change = f"Rating: {m.group(1).title()}"

    # ABG estimate-change table on cover
    if not result.revisions:
        revs = generic.parse_revision_mentions("\n".join(p.text for p in pages[:3]))
        if revs:
            result.revisions = revs

    if not result.key_passages:
        m = re.search(r"(We (?:expect|continue|understand)|One of .{10,200})", re.sub(r"\s+", " ", head), re.I)
        if m:
            result.key_passages = [Passage(page=1, text=m.group(0)[:400], label="why_now")]

    result.extraction_status = compute_extraction_status(result)
    return result
