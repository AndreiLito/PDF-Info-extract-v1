from __future__ import annotations

import re

from extractors.base import ExtractedReport, Passage, PageText, compute_extraction_status
from extractors import generic


def extract(pages: list[PageText]) -> ExtractedReport:
    result = generic.extract(pages)
    result.extractor_used = "ubs"
    result.low_confidence = False
    head = pages[0].text if pages else ""
    lines = [ln.strip() for ln in head.splitlines() if ln.strip()]

    for i, line in enumerate(lines):
        if re.search(r"Fast Take", line, re.I):
            for nxt in lines[i + 1 : i + 5]:
                if 2 < len(nxt) < 50 and not re.search(r"Headline|Our Take|Global Research", nxt, re.I):
                    result.company = nxt
                    break
            break

    m = re.search(r"Target\s*[Pp]rice[:\s]*([A-Z]{3})?\s*([\d,\.]+)", head, re.I)
    if m:
        result.target_price = f"{(m.group(1) or '')}{m.group(2)}"

    m = re.search(r"\b(Buy|Neutral|Sell|Reduce|Attractive)\b", head)
    if m:
        result.rating_change = f"Rating: {m.group(1)}"

    # Company after "Global Research" (Fast Take / note) — single line only
    if not result.company:
        m = re.search(r"Global Research\s*\n+([A-Z][^\n]{1,50})\n", head, re.I)
        if m and not re.search(r"research|update|equity|page", m.group(1), re.I):
            result.company = generic._clean_company(m.group(1))
    if not result.company:
        co = generic.parse_company(head)
        if co:
            result.company = co

    if not result.broker_eps:
        be, ce = generic.parse_eps_numbers("\n".join(p.text for p in pages[:6]))
        if be:
            result.broker_eps = be
        if ce and not result.consensus_eps:
            result.consensus_eps = ce
    if not result.broker_eps:
        # Fast Takes often lack full EPS tables — capture any EPS mention
        m = re.search(rf"EPS[^\d(]{{0,40}}({generic._EPS_NUM})", re.sub(r"\s+", " ", head), re.I)
        if m:
            try:
                result.broker_eps = [generic._eps_float(m.group(1))]
            except ValueError:
                pass

    if not result.key_passages:
        m = re.search(r"(Our Take|Headline).{40,450}", re.sub(r"\s+", " ", head), re.I)
        if m:
            result.key_passages = [Passage(page=1, text=m.group(0)[:400], label="why_now")]

    result.extraction_status = compute_extraction_status(result)
    return result
