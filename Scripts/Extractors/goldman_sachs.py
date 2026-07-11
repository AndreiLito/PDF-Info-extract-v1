from __future__ import annotations

import re

from extractors.base import ExtractedReport, Passage, PageText, compute_extraction_status
from extractors import generic


def extract(pages: list[PageText]) -> ExtractedReport:
    result = generic.extract(pages)
    result.extractor_used = "goldman_sachs"
    result.low_confidence = False
    head = pages[0].text if pages else ""
    norm = re.sub(r"\s+", " ", head)

    # Prefer PDF metadata title when present
    m = re.search(
        r"PDF_TITLE:\s*([A-Za-z][^\n(]{1,60}?)\s*\(([A-Za-z0-9]+\.[A-Z]{1,3})\)",
        head,
    )
    if m:
        result.company = generic._clean_company(m.group(1))

    if not result.company:
        m = re.search(r"^([A-Za-z][^\n(]{2,50})\s*\(([A-Z0-9]+\.[A-Z]{1,3})\):", head, re.M)
        if m and "Goldman" not in m.group(1):
            result.company = generic._clean_company(m.group(1))

    # Quark layouts / body: "Siemens Healthineers AG (SHLG.DE):"
    if not result.company:
        m = re.search(
            r"(?m)^([A-Z][^\n(]{2,50})\s*\(([A-Za-z0-9]+\.[A-Z]{1,3})\):",
            head,
        )
        if m and "Goldman" not in m.group(1):
            result.company = generic._clean_company(m.group(1))

    # Body fallback: "We downgrade Elia to Neutral"
    if not result.company:
        m = re.search(
            r"(?:downgrade|upgrade|reiterate|initiate)\s+([A-Z][A-Za-z0-9&\.\-'\s]{1,40}?)\s+to\s+(Buy|Sell|Neutral)",
            head,
            re.I,
        )
        if m:
            result.company = generic._clean_company(m.group(1))

    # GS often has no TP on meeting notes — still capture rating if present
    m = re.search(r"\b(Buy|Sell|Neutral|Conviction Buy)\b", head)
    if m:
        result.rating_change = f"Rating: {m.group(1)}"

    # 12m Price Target: €25.00 / Our 12-month price target of €25.0
    body = "\n".join(p.text for p in pages[:3])
    m = re.search(r"12m\s+Price Target:\s*(€|EUR)?\s*([\d,\.]+)", body, re.I)
    if not m:
        m = re.search(r"12-month\s+price target\s+(?:of|is)\s*(€|EUR)?\s*([\d,\.]+)", body, re.I)
    if m:
        result.target_price = f"EUR{m.group(2)}"

    if not result.key_passages:
        m = re.search(r"(Today, we hosted|Key takeaways|Management noted).{40,500}", norm, re.I)
        if m:
            result.key_passages = [Passage(page=1, text=m.group(0)[:400], label="why_now")]

    # If still no company, try title line before date
    if not result.company:
        m = re.search(r"\n([A-Z][^\n]{3,60})\n\d{1,2} \w+ 20\d{2}", head)
        if m and "Goldman" not in m.group(1):
            result.company = re.sub(r"\s*\(.*$", "", m.group(1)).strip()

    result.extraction_status = compute_extraction_status(result)
    return result
