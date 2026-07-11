from __future__ import annotations

import re

from extractors.base import ExtractedReport, Passage, PageText, compute_extraction_status
from extractors import generic


def extract(pages: list[PageText]) -> ExtractedReport:
    result = generic.extract(pages)
    result.extractor_used = "jefferies"
    result.low_confidence = False
    head = pages[0].text if pages else ""
    norm = re.sub(r"\s+", " ", head)

    m = re.search(
        r"(?:Denmark|Sweden|Norway|Germany|France|UK|Italy|Spain|Switzerland|Netherlands|Belgium|US)\s*\|\s*[^|\n]+\n([^\n|]+)\nEquity Research",
        head,
        re.I,
    )
    if m:
        result.company = m.group(1).strip()

    m = re.search(r"RATING\s*\n\s*(BUY|HOLD|SELL|NEUTRAL|UNDERPERFORM|OVERWEIGHT)", head, re.I)
    if m:
        result.rating_change = f"Rating: {m.group(1).title()}"

    m = re.search(r"PRICE TARGET\s*\|\s*% TO PT\s*\n\s*(USD|EUR|GBP|\$)?\s*([\d,\.]+)", head, re.I)
    if m:
        ccy = m.group(1) or ""
        if ccy == "$":
            ccy = "USD"
        result.target_price = f"{ccy}{m.group(2)}"
    else:
        m = re.search(r"PRICE TARGET.*?\n\s*\$?\s*([\d,\.]+)\s*\|", head, re.I)
        if m:
            result.target_price = f"USD{m.group(1)}"

    m = re.search(rf"adj\.?\s*EPS[^\d(]{{0,40}}({generic._EPS_NUM})\s*p?\b", norm, re.I)
    if m:
        result.broker_eps = [generic._eps_float(m.group(1))]
    elif not result.broker_eps:
        be, ce = generic.parse_eps_numbers("\n".join(p.text for p in pages[:6]))
        if be:
            result.broker_eps = be
        if ce and not result.consensus_eps:
            result.consensus_eps = ce

    if not result.key_passages:
        m = re.search(r"(We think|Importantly|Organic growth|Reiterate Buy).{40,400}", norm, re.I)
        if m:
            result.key_passages = [Passage(page=1, text=m.group(0)[:400], label="why_now")]

    result.extraction_status = compute_extraction_status(result)
    return result
