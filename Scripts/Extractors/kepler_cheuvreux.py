from __future__ import annotations

import re

from extractors.base import ExtractedReport, PageText, Passage, compute_extraction_status, find_passages

REVISION_LINE_RE = re.compile(
    r"Change in (Adj\.?\s*EPS|Adj\.?\s*EBIT|Sales|TP|Target Price)[:\s]*"
    r"([+-]?\d+\.?\d*%?)\s*(\d{2}E)?/?\s*([+-]?\d+\.?\d*%?)?\s*(\d{2}E)?",
    re.I,
)
RATING_RE = re.compile(
    r"(Downgrade|Upgrade|Dgd|Ugd|Downgrad\w*|Upgrad\w*)\s+(?:to\s+)?(\w+)\s+from\s+(\w+)",
    re.I,
)


def _parse_revisions(head: str) -> list[dict]:
    rows: list[dict] = []
    for m in REVISION_LINE_RE.finditer(head):
        metric = re.sub(r"\s+", " ", m.group(1)).strip()
        rows.append(
            {
                "metric": metric,
                "fy1": (m.group(3) or "").replace("E", ""),
                "change_fy1": m.group(2),
                "fy2": (m.group(5) or "").replace("E", ""),
                "change_fy2": m.group(4) or "",
            }
        )
    return rows


def _parse_eps_table(head: str) -> tuple[list[float], list[float]]:
    from extractors import generic as gen

    # Classic Kepler forward block
    forward = re.search(
        r"12/26E\s+12/27E\s+12/28E.*?EPS adj\. and ful\. dil\.\s+"
        r"([\d\.\-]+)\s+([\d\.\-]+)\s+([\d\.\-]+).*?"
        r"Consensus EPS\s+([\d\.\-]+)\s+([\d\.\-]+)\s+([\d\.\-]+)",
        head,
        re.I | re.DOTALL,
    )
    if forward:
        broker = [float(forward.group(i)) for i in range(1, 4)]
        consensus = [float(forward.group(i)) for i in range(4, 7)]
        return broker, consensus

    # Vertical / line-broken "Per share data" tables (EPS adjusted 0.49 0.35 …)
    broker, consensus = gen.parse_eps_numbers(head)
    if not broker:
        norm = re.sub(r"\s+", " ", head[:10000])
        m = re.search(
            rf"EPS adjusted(?:\s+and\s+fully\s+diluted)?\s+({gen._EPS_NUM})\s+({gen._EPS_NUM})(?:\s+({gen._EPS_NUM}))?",
            norm,
            re.I,
        )
        if m:
            broker = [gen._eps_float(g) for g in m.groups() if g]
        m = re.search(
            rf"(?:EPS Consensus|Consensus EPS)(?:\s*\([^)]*\))?\s+({gen._EPS_NUM})\s+({gen._EPS_NUM})(?:\s+({gen._EPS_NUM}))?",
            norm,
            re.I,
        )
        if m:
            consensus = [gen._eps_float(g) for g in m.groups() if g]
    return broker, consensus


def _extract_company(head: str) -> str:
    for line in [ln.strip() for ln in head.splitlines()[:50] if ln.strip()]:
        m = re.match(
            r"^([A-Za-z][A-Za-z0-9&\-\.'\s]+?)\s+"
            r"(Hold|Buy|Sell|Neutral)\s*[\(|\|]",
            line,
            re.I,
        )
        if m:
            return m.group(1).strip()
        m2 = re.match(
            r"^([A-Za-z][A-Za-z0-9&\-\.'\s]+?)\s+(Hold|Buy|Sell)\s*\(",
            line,
            re.I,
        )
        if m2:
            return m2.group(1).strip()
    return ""


def extract(pages: list[PageText]) -> ExtractedReport:
    head = pages[0].text if pages else ""
    full = "\n".join(p.text for p in pages)

    rating_change = ""
    rm = RATING_RE.search(head)
    if rm:
        rating_change = f"{rm.group(1)} to {rm.group(2)} from {rm.group(3)}"
    elif "Hold" in head and "Buy" in head and "#RatingChange" in head:
        rating_change = "Downgrade to Hold from Buy"

    tp_match = re.search(r"Target Price:\s*\n?EUR?([\d\.]+)\s*\(([\d\.]+)\)", head, re.I)
    target_price = ""
    if tp_match:
        target_price = f"EUR{tp_match.group(1)} (was EUR{tp_match.group(2)})"

    broker_eps, consensus_eps = _parse_eps_table(head)
    revisions = _parse_revisions(head)

    passages = find_passages(
        pages,
        [
            ("why_now", r"Why this report\?.{20,600}"),
            ("drivers", r"Deconstructing the forecasts.{20,500}"),
            ("valuation", r"Valuation and investment conclusion.{20,500}"),
            ("key_findings", r"Key findings.{20,500}"),
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
        company=_extract_company(head),
        extractor_used="kepler_cheuvreux",
    )
    result.extraction_status = compute_extraction_status(result)

    # Non-Schaeffler Kepler layouts: fill gaps via generic heuristics
    if result.extraction_status != "full" or not result.company:
        from extractors import generic as gen

        g = gen.extract(pages)
        result.company = result.company or g.company
        result.target_price = result.target_price or g.target_price
        result.rating_change = result.rating_change or g.rating_change
        result.revisions = result.revisions or g.revisions
        result.key_passages = result.key_passages or g.key_passages
        result.broker_eps = result.broker_eps or g.broker_eps
        result.consensus_eps = result.consensus_eps or g.consensus_eps
        result.extraction_status = compute_extraction_status(result)
    return result
