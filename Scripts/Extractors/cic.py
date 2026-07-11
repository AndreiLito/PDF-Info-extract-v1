from __future__ import annotations

import re

from extractors.base import ExtractedReport, Passage, PageText, compute_extraction_status
from extractors import generic


def extract(pages: list[PageText]) -> ExtractedReport:
    """CIC Morning News Analyser — often multi-name; take first featured company block."""
    result = generic.extract(pages)
    result.extractor_used = "cic"
    result.low_confidence = False
    head = pages[0].text if pages else ""

    m = re.search(
        r"MORNING NEWS ANALYSER.*?(?:CIC[^\n]*\n)?\s*\d+\s*\n([A-Za-z][^\n]{1,60})\n(Buy|Hold|Sell|Neutral)",
        head,
        re.I | re.S,
    )
    if m:
        result.company = m.group(1).strip()
        result.rating_change = f"Rating: {m.group(2)}"

    # OCR-spaced titles: "Bonduelle  - D ownw ard…" / clean company line after analyst email
    if not result.company:
        m = re.search(
            r"MORNING NEWS ANALYSER.*?\n\s*\d+\s*\n([A-Za-z][A-Za-z0-9&\.\-'\s]{1,40}?)\s+-\s+",
            head,
            re.I | re.S,
        )
        if m:
            result.company = re.sub(r"\s+", " ", m.group(1)).strip()
    if not result.company or re.search(r"reasons to|top picks", result.company or "", re.I):
        # Standalone company name repeated after analyst block (not the subtitle)
        m = re.search(
            r"@[^\n]+\n(?:Analyst\n)?(?:\+?\d[^\n]*\n)?([A-Z][A-Za-z0-9&\.\-']{1,40})\n(?!Five good|Downward|Space to|Our analysis)",
            head,
            re.I,
        )
        if m and not re.search(r"reasons|picks|analyst|virginie|eric|alexandre", m.group(1), re.I):
            result.company = m.group(1).strip()
    if result.company:
        result.company = generic._clean_company(result.company) or result.company

    m = re.search(r"Target Price\s*\(([A-Z]{3})\)\s*\n\s*([\d,\.]+)", head, re.I)
    if m:
        result.target_price = f"{m.group(1)}{m.group(2)}"

    if not result.key_passages:
        m = re.search(r"(Our analysis:|Conclusion & Action:|The facts:).{40,450}", re.sub(r"\s+", " ", head), re.I)
        if m:
            result.key_passages = [Passage(page=1, text=m.group(0)[:400], label="why_now")]

    result.extraction_status = compute_extraction_status(result)
    return result
