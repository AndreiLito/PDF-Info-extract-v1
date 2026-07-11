"""PDF extraction — dispatches to broker-specific extractors via registry.

Prefer extract_with_registry(pdf, broker, ticker_hint=...) so validate_and_backfill runs.
Full-corpus metrics: python scripts/audit_full_corpus.py  (N≈172).
"""

from __future__ import annotations

from pathlib import Path

from extractors.base import ExtractedReport, PageText, Passage, extract_pages
from extractors.registry import extract_with_registry

__all__ = [
    "ExtractedReport",
    "PageText",
    "Passage",
    "extract_pages",
    "extract_report",
    "extract_with_registry",
]


def extract_report(pdf_path: Path | str, broker: str = "") -> ExtractedReport:
    if broker:
        return extract_with_registry(pdf_path, broker)
    return extract_with_registry(pdf_path, "generic_fallback")
