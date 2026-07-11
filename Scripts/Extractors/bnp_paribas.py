from __future__ import annotations

import re

from extractors.base import ExtractedReport, Passage, PageText, compute_extraction_status
from extractors import generic


def extract(pages: list[PageText]) -> ExtractedReport:
    result = generic.extract(pages)
    result.extractor_used = "bnp_paribas"
    result.low_confidence = False
    head = pages[0].text if pages else ""

    m = re.search(r"^([A-Z][A-Z0-9&\.\- ]{2,40})\s+(OUTPERFORM|UNDERPERFORM|BUY|HOLD|SELL)\b", head, re.M)
    if m:
        result.company = m.group(1).title().strip()
        result.rating_change = f"Reiterate {m.group(2).title()}" if "reiterate" in head.lower() else f"Rating: {m.group(2).title()}"

    m = re.search(r"TARGET PRICE\s+([A-Z]{3})?\s*([\d,\.]+)", head, re.I)
    if m:
        result.target_price = f"{(m.group(1) or 'EUR')}{m.group(2)}"

    # revision arrows block
    norm = re.sub(r"\s+", " ", head)
    m = re.search(
        r"TARGET PRICE\s+EPS 26e\s+EPS 27e.*?([+\-]?\d+%)\s+([+\-]?\d+%)\s+([+\-]?\d+%)",
        norm,
        re.I,
    )
    if m:
        result.revisions = [
            {"metric": "Target price", "fy1": "", "change_fy1": m.group(1), "fy2": "", "change_fy2": ""},
            {"metric": "EPS", "fy1": "26", "change_fy1": m.group(2), "fy2": "27", "change_fy2": m.group(3)},
        ]

    m = re.search(r"trim\s+20(\d{2})/(\d{2})\s+EPS\s+by\s+(\d+%)/(\d+%)", norm, re.I)
    if m and not result.revisions:
        result.revisions = [
            {"metric": "EPS", "fy1": m.group(1), "change_fy1": f"-{m.group(3)}", "fy2": m.group(2), "change_fy2": f"-{m.group(4)}"},
        ]

    # Absolute EPS levels from financial summary table
    if not result.broker_eps:
        be, ce = generic.parse_eps_numbers(head + "\n" + "\n".join(p.text for p in pages[1:3]))
        if be:
            result.broker_eps = be
        if ce and not result.consensus_eps:
            result.consensus_eps = ce

    if not result.key_passages:
        m = re.search(r"(Weak Q1|We reiterate|Management reiterated).{40,450}", norm, re.I)
        if m:
            result.key_passages = [Passage(page=1, text=m.group(0)[:400], label="why_now")]

    result.extraction_status = compute_extraction_status(result)
    return result
