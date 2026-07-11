from __future__ import annotations

import re

from extractors.base import ExtractedReport, Passage, PageText, compute_extraction_status
from extractors import generic


def extract(pages: list[PageText]) -> ExtractedReport:
    result = generic.extract(pages)
    result.extractor_used = "jp_morgan"
    result.low_confidence = False
    head = pages[0].text if pages else ""
    lines = [ln.strip() for ln in head.splitlines() if ln.strip()]

    # Company after CAZENOVE / www.jpmorganmarkets.com
    for i, line in enumerate(lines):
        if "jpmorganmarkets" in line.lower() or line == "CAZENOVE" or set(line) <= set("CAZENOVE\n "):
            # next non-trivial line
            for nxt in lines[i + 1 : i + 8]:
                if len(nxt) > 3 and not re.search(r"Contents|Overweight|Underweight|www\.", nxt, re.I):
                    if not re.match(r"^[A-Z]$", nxt):  # skip letter-spaced CAZENOVE
                        result.company = nxt
                        break
            break
    # letter-spaced CAZENOVE means company is after those single letters
    if not result.company:
        joined = []
        collecting = False
        for line in lines[:30]:
            if line in list("CAZENOVE") or line == "www.jpmorganmarkets.com":
                collecting = True
                continue
            if collecting and len(line) > 4 and line not in ("Contents",):
                result.company = line
                break

    m = re.search(r"Price Target\s*\([^)]*\)\s*:?\s*\$?([\d,\.]+)", head, re.I)
    if m:
        result.target_price = f"${m.group(1)}" if "$" in head[m.start() : m.end() + 5] else m.group(1)
    m = re.search(r"Price Target\s*\(([^)]+)\)\s*:?\s*([^\n]+)", head, re.I)
    if m:
        result.target_price = m.group(2).strip()

    m = re.search(r"\n(Overweight|Underweight|Neutral)\s*\n", head)
    if m:
        result.rating_change = f"Rating: {m.group(1)}"

    # guidance / estimate language
    norm = re.sub(r"\s+", " ", head)
    m = re.search(r"(slightly upgraded guidance|raised its FY|JPMe|consensus).{20,300}", norm, re.I)
    if m and not result.revisions:
        result.revisions = [{"metric": "Guidance", "fy1": "", "change_fy1": "upgraded" if "upgrad" in m.group(0).lower() else "noted", "fy2": "", "change_fy2": ""}]

    if not result.key_passages:
        m = re.search(r"Our Take:.{40,500}", norm, re.I)
        if m:
            result.key_passages = [Passage(page=1, text=m.group(0)[:400], label="why_now")]

    result.extraction_status = compute_extraction_status(result)
    return result
