#!/usr/bin/env python3
"""Locate a sell-side report and extract structured context for /find-rpt briefs.

Usage (repo root):
  python scripts/find_rpt.py "SHA0 GY" 20260622 "Kepler Cheuvreux"

Extraction is broker-pluggable via extractors/registry.py + validate_and_backfill.
Corpus quality (N=172): see scripts/README.md or .find-rpt/full_corpus_audit.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Allow running as `python scripts/find_rpt.py` from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cite import make_citation, pdf_page_uri, search_snippet
from corpus import build_index, find_report, normalize_date
from extract import extract_report


def format_date_display(yyyymmdd: str) -> str:
    dt = datetime.strptime(yyyymmdd, "%Y%m%d")
    return dt.strftime("%d %b %Y")


def pct_vs_consensus(broker: float, consensus: float) -> str | None:
    if consensus == 0:
        return None
    return f"{((broker / consensus) - 1) * 100:+.0f}%"


def build_estimate_picture(extracted) -> dict:
    picture = {"broker_eps": extracted.broker_eps, "consensus_eps": extracted.consensus_eps, "rows": []}
    if extracted.broker_eps and extracted.consensus_eps:
        labels = ["FY26E", "FY27E", "FY28E"][: len(extracted.broker_eps)]
        for i, label in enumerate(labels):
            b = extracted.broker_eps[i] if i < len(extracted.broker_eps) else None
            c = extracted.consensus_eps[i] if i < len(extracted.consensus_eps) else None
            if b is not None and c is not None:
                picture["rows"].append(
                    {
                        "year": label,
                        "broker_eps": b,
                        "consensus_eps": c,
                        "vs_consensus": pct_vs_consensus(b, c),
                    }
                )
    return picture


def ambiguity_check(extracted) -> dict:
    if extracted.extraction_status in ("partial", "failed"):
        return {
            "revisions_without_clear_rationale": False,
            "should_offer_email_draft": False,
            "note": (
                "Extraction incomplete for this broker template — review the source PDF directly. "
                "Do not offer analyst email escalation due to extractor gaps."
            ),
        }

    has_revisions = bool(extracted.revisions) or bool(extracted.rating_change)
    rationale_labels = {"why_now", "drivers", "investment_case", "valuation"}
    has_rationale = any(p.label in rationale_labels for p in extracted.key_passages)
    unclear = has_revisions and not has_rationale
    return {
        "revisions_without_clear_rationale": unclear,
        "should_offer_email_draft": unclear,
        "note": "" if not unclear else "Report has revisions but rationale passages not found in source.",
    }


def run(ticker: str, date: str, broker: str, rebuild_index: bool = False) -> dict:
    if rebuild_index:
        build_index(force=True)

    record, pdf_path = find_report(ticker, date, broker)
    from extractors.registry import extract_with_registry

    extracted = extract_with_registry(pdf_path, record.broker, ticker_hint=ticker)
    company = extracted.company or record.company

    citations = []
    for i, passage in enumerate(extracted.key_passages, start=1):
        snippet = search_snippet(passage.text, passage.text)
        citations.append(
            make_citation(
                pdf_path,
                passage.page,
                passage.label.replace("_", " ").title(),
                snippet,
                f"c{i}",
            )
        )

    if not citations:
        citations.append(
            make_citation(
                pdf_path,
                1,
                "Report cover",
                search_snippet(extracted.pages[0].text, company or ticker),
                "c1",
            )
        )

    analyst_email = extracted.analyst_email or getattr(record, "analyst_email", "") or ""

    return {
        "query": {"ticker": ticker, "date": normalize_date(date), "broker": broker},
        "header": {
            "ticker": ticker,
            "broker": record.broker,
            "date": format_date_display(record.date),
            "filename": record.file,
            "company": company,
            "analyst": record.analyst,
            "analyst_email": analyst_email,
            "report_type": record.report_type,
            "title_line": record.title_line,
            "pdf_uri": pdf_page_uri(pdf_path, 1),
        },
        "extracted": {
            "extraction_status": extracted.extraction_status,
            "extractor_used": extracted.extractor_used,
            "low_confidence": extracted.low_confidence,
            "rating_change": extracted.rating_change,
            "target_price": extracted.target_price,
            "revisions": extracted.revisions,
            "estimate_picture": build_estimate_picture(extracted),
            "key_passages": [
                {"label": p.label, "page": p.page, "text": p.text[:500]} for p in extracted.key_passages
            ],
        },
        "citations": citations,
        "ambiguity": ambiguity_check(extracted),
        "brief_instructions": (
            "Compose the /find-rpt brief from this JSON. Use citations inline. "
            "Follow the output template in the skill. If ambiguity.should_offer_email_draft "
            "is true, include a draft email to the analyst (never send)."
        ),
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Find sell-side report and extract brief context")
    parser.add_argument("ticker", help='Bloomberg ticker, e.g. "SHA0 GY"')
    parser.add_argument("date", help="Report date YYYYMMDD or '22 Jun 2026'")
    parser.add_argument("broker", help='Broker name, e.g. "Kepler Cheuvreux"')
    parser.add_argument("--rebuild-index", action="store_true", help="Rebuild corpus index")
    parser.add_argument("--json", action="store_true", default=True, help="Output JSON (default)")
    args = parser.parse_args()

    try:
        result = run(args.ticker, args.date, args.broker, rebuild_index=args.rebuild_index)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except FileNotFoundError as e:
        print(json.dumps({"error": str(e)}, indent=2), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"error": f"{type(e).__name__}: {e}"}, indent=2), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
