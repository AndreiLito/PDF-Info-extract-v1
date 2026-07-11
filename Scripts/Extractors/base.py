from __future__ import annotations

import re
from dataclasses import dataclass, field

import fitz


@dataclass
class PageText:
    page: int
    text: str


@dataclass
class Passage:
    page: int
    text: str
    label: str


@dataclass
class ExtractedReport:
    pages: list[PageText] = field(default_factory=list)
    revisions: list[dict] = field(default_factory=list)
    rating_change: str = ""
    target_price: str = ""
    consensus_eps: list[float] = field(default_factory=list)
    broker_eps: list[float] = field(default_factory=list)
    key_passages: list[Passage] = field(default_factory=list)
    full_text: str = ""
    company: str = ""
    analyst_email: str = ""
    extraction_status: str = "failed"  # full | partial | failed
    extractor_used: str = "generic"
    low_confidence: bool = False


def extract_pages(pdf_path) -> list[PageText]:
    doc = fitz.open(pdf_path)
    pages = [PageText(page=i + 1, text=doc[i].get_text()) for i in range(len(doc))]
    # Stash metadata title on page 0 text prefix for extractors that need it (GS Quark layouts)
    meta_title = (doc.metadata or {}).get("title") or ""
    doc.close()
    if meta_title and pages:
        pages[0].text = f"PDF_TITLE: {meta_title}\n" + pages[0].text
    return pages


def find_passages(pages: list[PageText], patterns: list[tuple[str, str]]) -> list[Passage]:
    found: list[Passage] = []
    for label, pattern in patterns:
        rx = re.compile(pattern, re.I | re.DOTALL)
        for pg in pages:
            m = rx.search(pg.text)
            if m:
                snippet = re.sub(r"\s+", " ", m.group(0).strip())[:400]
                found.append(Passage(page=pg.page, text=snippet, label=label))
                break
    return found


def extract_analyst_email(text: str) -> str:
    emails = re.findall(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", text[:12000])
    for email in emails:
        low = email.lower()
        if any(x in low for x in ("factset", "example.com", "noreply", "donotreply", "bloomberg.net")):
            continue
        return email
    return ""


def compute_extraction_status(result: ExtractedReport) -> str:
    has_company = bool(result.company)
    has_numbers = bool(result.revisions) or bool(result.broker_eps) or bool(result.target_price) or bool(result.rating_change)
    has_narrative = bool(result.key_passages)
    score = sum([has_company, has_numbers, has_narrative])
    if score >= 2:
        return "full"
    if score >= 1:
        return "partial"
    return "failed"
