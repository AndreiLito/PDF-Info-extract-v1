from __future__ import annotations

import re

from extractors.base import ExtractedReport, Passage, PageText, compute_extraction_status
from extractors import generic


def extract(pages: list[PageText]) -> ExtractedReport:
    result = generic.extract(pages)
    result.extractor_used = "zurcher"
    result.low_confidence = False
    head = pages[0].text if pages else ""

    m = re.search(r"^([A-Z][A-Za-z0-9&\.\-'\s]{2,40})\s*\(([A-Z]{2,6})\)\s*$", head, re.M)
    if m:
        result.company = m.group(1).strip()

    m = re.search(r"Rating:\s*\n\s*(Market Perform|Outperform|Underperform|Buy|Hold|Sell)", head, re.I)
    if m:
        result.rating_change = f"Rating: {m.group(1)}"

    # ZKB newsflash often has no TP — mark n.a. only if no Kursziel/TP language
    if not result.target_price:
        m = re.search(r"(?:Kursziel|Target price|Price target)\s*[:=]?\s*(CHF|EUR)?\s*([\d',\.]+)", head, re.I)
        if m:
            result.target_price = f"{(m.group(1) or 'CHF')}{m.group(2).replace(chr(39), '')}"
        elif not re.search(r"target\s*price|kursziel|price target", head, re.I):
            # newsflash without TP is common — leave empty (field absent), don't invent
            pass

    # EPS block — levels or ZKB "EPS new" revision table
    norm = re.sub(r"\s+", " ", "\n".join(p.text for p in pages[:3]))
    m = re.search(
        rf"EPS\s+new\s+({generic._EPS_NUM})\s+({generic._EPS_NUM})(?:\s+({generic._EPS_NUM}))?",
        norm,
        re.I,
    )
    if m:
        result.broker_eps = [generic._eps_float(g) for g in m.groups() if g]
    else:
        m = re.search(
            rf"EPS\s+({generic._EPS_NUM})\s+({generic._EPS_NUM})\s+({generic._EPS_NUM})",
            norm,
            re.I,
        )
        if m:
            result.broker_eps = [generic._eps_float(m.group(i)) for i in range(1, 4)]
        elif not result.broker_eps:
            be, ce = generic.parse_eps_numbers(norm)
            if be:
                result.broker_eps = be
            if ce and not result.consensus_eps:
                result.consensus_eps = ce

    # ZKB: EPS old / EPS new block → revision rows
    m = re.search(
        rf"EPS\s+old\s+({generic._EPS_NUM})\s+({generic._EPS_NUM})(?:\s+({generic._EPS_NUM}))?"
        rf".{{0,40}}?EPS\s+new\s+({generic._EPS_NUM})\s+({generic._EPS_NUM})(?:\s+({generic._EPS_NUM}))?",
        norm,
        re.I,
    )
    if m and not result.revisions:
        olds = [generic._eps_float(g) for g in m.groups()[:3] if g]
        news = [generic._eps_float(g) for g in m.groups()[3:] if g]
        result.revisions = []
        for i, (old, new) in enumerate(zip(olds, news)):
            if old:
                result.revisions.append(
                    {
                        "metric": "EPS",
                        "fy1": str(25 + i),
                        "change_fy1": f"{(new / old - 1) * 100:+.1f}%",
                        "fy2": "",
                        "change_fy2": "",
                        "from_value": str(old),
                        "to_value": str(new),
                    }
                )

    if not result.key_passages:
        m = re.search(r"(Conclusion:|Facts / Assessment:).{40,450}", re.sub(r"\s+", " ", head), re.I)
        if m:
            result.key_passages = [Passage(page=1, text=m.group(0)[:400], label="why_now")]

    result.extraction_status = compute_extraction_status(result)
    return result
