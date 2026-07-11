from __future__ import annotations

import re

from extractors.base import ExtractedReport, PageText, Passage, compute_extraction_status, find_passages


def _extract_company(head: str) -> str:
    m = re.search(
        r"Share price:\s*\S+\s*\n\s*([A-Za-z][A-Za-z0-9&\-\.'\s]+?)\s*\n",
        head,
        re.I,
    )
    if m:
        return m.group(1).strip()
    return ""


def _parse_target_price(head: str) -> str:
    m = re.search(r"Target price:\s*([A-Z]{3})([\d\.]+)(?:\s*\(([\d\.]+)\))?", head, re.I)
    if m:
        ccy, new, old = m.group(1), m.group(2), m.group(3)
        if old:
            return f"{ccy}{new} (was {ccy}{old})"
        return f"{ccy}{new}"
    return ""


def _parse_revision_table(head: str) -> list[dict]:
    rows: list[dict] = []
    block = re.search(r"Changes in this report(.{0,900})", head, re.I | re.DOTALL)
    if not block:
        return rows
    norm = re.sub(r"\s+", " ", block.group(1))
    for m in re.finditer(
        r"EPS adj\. (\d{4})e ([\d\.\-]+) ([\d\.\-]+) ([+\-]?\d+%|-%)",
        norm,
        re.I,
    ):
        rows.append(
            {
                "metric": "Adj. EPS",
                "fy1": m.group(1)[-2:],
                "change_fy1": m.group(4),
                "fy2": "",
                "change_fy2": "",
                "from_value": m.group(2),
                "to_value": m.group(3),
            }
        )
    return rows


def _parse_eps_from_key_figures(head: str) -> tuple[list[float], list[float]]:
    m = re.search(
        r"Key figures.*?EPS adj\.\s*\n([\d\.\-]+)\s*\n([\d\.\-]+)\s*\n([\d\.\-]+)\s*\n([\d\.\-]+)",
        head,
        re.I | re.DOTALL,
    )
    if m:
        return [float(m.group(i)) for i in range(2, 5)], []
    return [], []


def extract(pages: list[PageText]) -> ExtractedReport:
    head = pages[0].text if pages else ""
    full = "\n".join(p.text for p in pages)

    company = _extract_company(head)
    target_price = _parse_target_price(head)
    revisions = _parse_revision_table(head)
    broker_eps, consensus_eps = _parse_eps_from_key_figures(head)

    rating = re.search(r"\n(BUY|HOLD|SELL|Buy|Hold|Sell)\s*\n", head)
    rating_change = ""
    if "reiterate" in head.lower():
        rating_change = f"Reiterate {rating.group(1).title()}" if rating else "Reiterated"
    if "reduce our target price" in head.lower() or "reduce our tp" in head.lower():
        rating_change = (rating_change + "; TP reduced").strip("; ")

    passages = find_passages(
        pages,
        [
            ("why_now", r"(?:We expect|We estimate|We reiterate).{40,500}"),
            ("drivers", r"(?:Changes in this report|EPS adj\.\s*\d{4}e).{20,400}"),
            ("investment_case", r"(?:BUY|Reiterate BUY|We like the risk/reward).{20,400}"),
        ],
    )

    result = ExtractedReport(
        pages=pages,
        revisions=revisions,
        rating_change=rating_change,
        target_price=target_price,
        consensus_eps=consensus_eps,
        broker_eps=broker_eps,
        key_passages=passages,
        full_text=full,
        company=company,
        extractor_used="dnb_carnegie",
    )
    result.extraction_status = compute_extraction_status(result)
    return result
