from __future__ import annotations

import re

from extractors.base import ExtractedReport, Passage, PageText, compute_extraction_status
from extractors import generic


def extract(pages: list[PageText]) -> ExtractedReport:
    """Nordea / Stifel / Redburn / Oddo / Danske — share similar Nordic/EU cover patterns."""
    result = generic.extract(pages)
    result.extractor_used = "nordic_eu"
    result.low_confidence = False
    head = pages[0].text if pages else ""

    m = re.search(r"^([A-Z][A-Za-z0-9&\.\-'\s]{2,50})\s*\(([A-Z0-9\.\s]+)\)", head, re.M)
    if m:
        result.company = generic._clean_company(m.group(1))

    # Nordea / ING / Pareto cover titles (accented names OK)
    if not result.company:
        m = re.search(
            r"^(\d+\s*)?([A-ZÀ-ÖØ-Ý][^\n–—-]{1,50}?)\s+[–—-]\s+(Hold|Buy|Sell|Neutral)\b",
            head,
            re.M | re.I,
        )
        if m:
            result.company = generic._clean_company(m.group(2))
    if not result.company:
        m = re.search(
            r"^([A-Z][^\n]{2,40})\n(?:1Q|2Q|3Q|4Q|Q1|CMD|Nice|We reiterate)",
            head,
            re.M,
        )
        if m and not re.search(r"for disclosures|pareto|may 20|imcd may", m.group(1), re.I):
            result.company = generic._clean_company(m.group(1))
    if not result.company:
        # Pareto: company often after disclaimer page
        body = "\n".join(p.text for p in pages[:2])
        m = re.search(
            r"Pareto Securities[^\n]*\n+(?:©[^\n]*\n+)?(\d+\n)?([A-Z][^\n]{2,50})\nNEWSFLASH",
            body,
            re.I,
        )
        if m:
            result.company = generic._clean_company(m.group(2))
    if not result.company:
        co = generic.parse_company(head) or generic.parse_company("\n".join(p.text for p in pages[:2]))
        if co and co.lower() not in {"flash comment", "brief news", "update"}:
            result.company = co

    m = re.search(r"(?:Target price|Price target|TP)\s*[:=]?\s*([A-Z]{3})?\s*([\d,\.]+)", head, re.I)
    if m:
        result.target_price = f"{(m.group(1) or '')}{m.group(2)}"

    m = re.search(r"\n(Buy|Hold|Sell|Accumulate|Reduce|Outperform|Underperform)\s*\n", head, re.I)
    if m:
        result.rating_change = f"Rating: {m.group(1).title()}"

    # Stifel / Pareto / Danske EPS tables and FY labels
    if not result.broker_eps:
        be, ce = generic.parse_eps_numbers("\n".join(p.text for p in pages[:4]))
        if be:
            result.broker_eps = be
        if ce and not result.consensus_eps:
            result.consensus_eps = ce

    if not result.revisions:
        revs = generic.parse_revision_mentions("\n".join(p.text for p in pages[:3]))
        if revs:
            result.revisions = revs

    if not result.key_passages:
        m = re.search(r"(We expect|We reiterate|In our view|Conclusion).{40,400}", re.sub(r"\s+", " ", head), re.I)
        if m:
            result.key_passages = [Passage(page=1, text=m.group(0)[:400], label="why_now")]

    result.extraction_status = compute_extraction_status(result)
    return result
