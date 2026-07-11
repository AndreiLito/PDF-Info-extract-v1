from __future__ import annotations

import re

from extractors.base import ExtractedReport, Passage, PageText, compute_extraction_status
from extractors import generic


def extract(pages: list[PageText]) -> ExtractedReport:
    result = generic.extract(pages)
    result.extractor_used = "morgan_stanley"
    result.low_confidence = False
    head = pages[0].text if pages else ""
    norm = re.sub(r"\s+", " ", head)

    m = re.search(r"([A-Za-z][A-Za-z0-9&\.\-'\s]{1,40})\s*\(([A-Z]{2,6}\.[A-Z]|[A-Z]{2,6}\s+[A-Z]{2})\)", head)
    # prefer ABB (ABBN.S, ABBN SE) style near Price target
    m = re.search(r"([A-Z]{2,10})\s*\(([A-Z0-9]+\.[A-Z]),\s*([A-Z0-9]+\s+[A-Z]{2})\)", head)
    if m:
        result.company = m.group(1)

    # "Aurubis AG | Europe" / "SSAB AB | Europe"
    if not result.company:
        m = re.search(
            r"^([A-Z][A-Za-z0-9&\.\-/'+\s]{1,55}?)\s*\|\s*(?:Europe|US|Asia|Global|UK)\b",
            head,
            re.M,
        )
        if m and not re.search(r"update|research|equity", m.group(1), re.I):
            result.company = m.group(1).strip()

    m = re.search(r"Price target\s*\n\s*([A-Za-z]+)\s*([\d,\.]+)", head, re.I)
    if m:
        result.target_price = f"{m.group(1)} {m.group(2)}"
    m = re.search(r"Price Target\s+([A-Za-z]+)\s*([\d,\.]+)\s+([A-Za-z]+)\s*([\d,\.]+)", norm)
    if m:
        result.target_price = f"{m.group(3)}{m.group(4)} (was {m.group(1)}{m.group(2)})"
        result.revisions = [
            {
                "metric": "Target price",
                "fy1": "",
                "change_fy1": "",
                "fy2": "",
                "change_fy2": "",
                "from_value": m.group(2),
                "to_value": m.group(4),
            }
        ]

    m = re.search(r"Stock Rating\s*\n\s*([A-Za-z\-]+)", head)
    if m:
        result.rating_change = f"Rating: {m.group(1)}"

    m = re.search(
        r"(?:increase|reduce)\s+our\s+20(\d{2})/(\d{2})/(\d{2})\s+EPS\s+by\s+([+\-]?\d+\.?\d*%?)/([+\-]?\d+\.?\d*%?)/([+\-]?\d+\.?\d*%?)",
        norm,
        re.I,
    )
    if m:
        verb = "increase" if "increase" in m.group(0).lower() else "reduce"
        sign = "+" if verb == "increase" else "-"
        result.revisions = []
        for i, fy in enumerate([m.group(1), m.group(2), m.group(3)]):
            ch = m.group(4 + i)
            if not ch.startswith(("+", "-")):
                ch = sign + ch
            result.revisions.append({"metric": "EPS", "fy1": fy, "change_fy1": ch, "fy2": "", "change_fy2": ""})

    # EPS / Prior EPS block
    m = re.search(
        rf"EPS\s*\([^)]*\)\s*\*{{0,2}}\s+({generic._EPS_NUM})\s+({generic._EPS_NUM})\s+({generic._EPS_NUM})\s+({generic._EPS_NUM})\s+Prior EPS",
        norm,
        re.I,
    )
    if m:
        result.broker_eps = [generic._eps_float(m.group(i)) for i in range(2, 5)]
    elif not result.broker_eps:
        be, ce = generic.parse_eps_numbers("\n".join(p.text for p in pages[:3]))
        if be:
            result.broker_eps = be
        if ce and not result.consensus_eps:
            result.consensus_eps = ce

    # Prior EPS revision deltas when both present
    m = re.search(
        r"EPS\s*\([^)]*\)\s*([\d\.\-]+)\s+([\d\.\-]+)\s+([\d\.\-]+)\s+([\d\.\-]+)\s+Prior EPS\s*\([^)]*\)\s*\S+\s+([\d\.\-]+)\s+([\d\.\-]+)\s+([\d\.\-]+)",
        norm,
        re.I,
    )
    if m:
        result.broker_eps = [float(m.group(i)) for i in range(2, 5)]
        if not result.revisions:
            result.revisions = []
            for i, fy in enumerate(["26", "27", "28"]):
                old, new = float(m.group(5 + i)), float(m.group(2 + i))
                if old:
                    result.revisions.append(
                        {
                            "metric": "EPS",
                            "fy1": fy,
                            "change_fy1": f"{(new / old - 1) * 100:+.1f}%",
                            "fy2": "",
                            "change_fy2": "",
                            "from_value": str(old),
                            "to_value": str(new),
                        }
                    )

    if not result.key_passages:
        m = re.search(r"Reason for change.{40,500}", norm, re.I)
        if m:
            result.key_passages = [Passage(page=1, text=m.group(0)[:400], label="drivers")]

    result.extraction_status = compute_extraction_status(result)
    return result
