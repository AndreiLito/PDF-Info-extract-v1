"""Full-corpus extraction audit: apply current model to every PDF and classify misses."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import load_config
from corpus import build_index
from extractors.registry import extract_with_registry, resolve_extractor
from extractors.validate import (
    _has_substantive_consensus,
    _has_substantive_eps,
    _has_substantive_rating,
    _has_substantive_revision,
    _has_substantive_tp,
)


METRICS = [
    "company",
    "target_price",
    "rating_change",
    "revisions",
    "broker_eps",
    "consensus_eps",
    "key_passages",
    "analyst_email",
]


def pdf_signals(text: str) -> dict:
    return {
        "has_tp_lang": _has_substantive_tp(text),
        "tp_is_na": bool(re.search(r"target\s*price.{0,20}n\.?a|tp\s*[:=].{0,10}n\.?a", text, re.I)),
        "has_email": "@" in text,
        "has_rating_word": _has_substantive_rating(text),
        "has_revision_lang": _has_substantive_revision(text),
        # Align with validate._has_substantive_eps (not disclaimer-only "EPS")
        "has_eps_table": _has_substantive_eps(text),
        "has_consensus": _has_substantive_consensus(text),
        "looks_multi_name": bool(
            re.search(r"morning news|brief news|flash|weekly|tracker|sector report", text[:2500], re.I)
        ),
    }


def classify_miss(metric: str, extracted_ok: bool, signals: dict) -> str | None:
    if extracted_ok:
        return None
    if not signals:
        return f"extractor_gap_{metric.split('_')[0]}" if metric != "key_passages" else "extractor_gap_passages"
    if metric == "company":
        return "extractor_gap_company"
    if metric == "target_price":
        if signals.get("tp_is_na"):
            return "field_na_tp"
        if not signals.get("has_tp_lang"):
            return "field_absent_tp"
        return "extractor_gap_tp"
    if metric == "rating_change":
        if not signals.get("has_rating_word"):
            return "field_absent_rating"
        return "extractor_gap_rating"
    if metric == "analyst_email":
        if not signals.get("has_email"):
            return "field_absent_email"
        return "extractor_gap_email"
    if metric == "revisions":
        if not signals.get("has_revision_lang"):
            return "field_absent_revisions"
        return "extractor_gap_revisions"
    if metric == "broker_eps":
        if not signals.get("has_eps_table"):
            return "field_absent_eps"
        return "extractor_gap_eps"
    if metric == "consensus_eps":
        if not signals.get("has_consensus"):
            return "field_absent_consensus"
        return "extractor_gap_consensus"
    if metric == "key_passages":
        return "extractor_gap_passages"
    return "unknown"


def main() -> None:
    cfg = load_config()
    corpus = cfg["corpus_path"]
    records = build_index(force=False)
    out_dir = Path(__file__).resolve().parent.parent / ".find-rpt"
    out_dir.mkdir(exist_ok=True)

    rows = []
    status = Counter()
    metric_hits = Counter()
    issue_counts = Counter()
    by_broker = defaultdict(lambda: Counter())
    by_extractor = defaultdict(lambda: Counter())
    issue_examples = defaultdict(list)

    for r in records:
        pdf = corpus / r.file
        if not pdf.exists():
            continue
        try:
            ex = extract_with_registry(
                pdf,
                r.broker,
                ticker_hint=(r.tickers[0] if getattr(r, "tickers", None) else ""),
            )
            st = ex.extraction_status
            text = "\n".join(p.text for p in ex.pages[:4])
        except Exception as e:
            st = "error"
            ex = None
            text = ""
            issue_counts["runtime_error"] += 1
            issue_examples["runtime_error"].append({"file": r.file, "error": str(e)[:200]})

        status[st] += 1
        ext = resolve_extractor(r.broker)
        signals = pdf_signals(text) if text else {}

        vals = {
            "company": bool(ex and (ex.company or r.company)),
            "target_price": bool(ex and ex.target_price),
            "rating_change": bool(ex and ex.rating_change),
            "revisions": bool(ex and ex.revisions),
            "broker_eps": bool(ex and ex.broker_eps),
            "consensus_eps": bool(ex and ex.consensus_eps),
            "key_passages": bool(ex and ex.key_passages),
            "analyst_email": bool(ex and (ex.analyst_email or getattr(r, "analyst_email", ""))),
        }
        for k, ok in vals.items():
            if ok:
                metric_hits[k] += 1
            issue = classify_miss(k, ok, signals)
            if issue:
                issue_counts[issue] += 1
                by_broker[r.broker][issue] += 1
                by_extractor[ext][issue] += 1
                if len(issue_examples[issue]) < 5:
                    issue_examples[issue].append(
                        {
                            "file": r.file,
                            "broker": r.broker,
                            "extractor": ext,
                            "ticker": r.tickers[0] if r.tickers else "",
                        }
                    )

        # applicable rates
        applicable = {
            "tp_applicable": signals.get("has_tp_lang") and not signals.get("tp_is_na"),
            "email_applicable": signals.get("has_email"),
            "rating_applicable": signals.get("has_rating_word"),
            "revisions_applicable": signals.get("has_revision_lang"),
            "eps_applicable": signals.get("has_eps_table"),
            "consensus_applicable": signals.get("has_consensus"),
        }

        row = {
            "file": r.file,
            "broker": r.broker,
            "extractor": ext,
            "status": st,
            "ticker": r.tickers[0] if r.tickers else "",
            **vals,
            **signals,
            **applicable,
            "multi_name": signals.get("looks_multi_name", False),
        }
        rows.append(row)
        by_broker[r.broker]["n"] += 1
        by_broker[r.broker][st] += 1
        by_extractor[ext]["n"] += 1
        by_extractor[ext][st] += 1

    n = len(rows)

    def rate(hits: int) -> float:
        return round(100 * hits / n, 1) if n else 0.0

    # conditional success among applicable
    conditional = {}
    for key, flag, metric in [
        ("target_price", "tp_applicable", "target_price"),
        ("analyst_email", "email_applicable", "analyst_email"),
        ("rating_change", "rating_applicable", "rating_change"),
        ("revisions", "revisions_applicable", "revisions"),
        ("broker_eps", "eps_applicable", "broker_eps"),
        ("consensus_eps", "consensus_applicable", "consensus_eps"),
    ]:
        app = [r for r in rows if r.get(flag)]
        hit = sum(1 for r in app if r.get(metric))
        conditional[key] = {
            "applicable": len(app),
            "hit": hit,
            "pct": round(100 * hit / len(app), 1) if app else None,
        }

    # priority fix list: extractor gaps by broker
    gap_by_broker = []
    for broker, c in by_broker.items():
        gaps = {k: v for k, v in c.items() if k.startswith("extractor_gap")}
        if gaps:
            gap_by_broker.append(
                {
                    "broker": broker,
                    "n": c.get("n", 0),
                    "full": c.get("full", 0),
                    "partial": c.get("partial", 0),
                    "failed": c.get("failed", 0),
                    "gaps": dict(sorted(gaps.items(), key=lambda x: -x[1])),
                    "gap_total": sum(gaps.values()),
                }
            )
    gap_by_broker.sort(key=lambda x: -x["gap_total"])

    summary = {
        "total_pdfs": n,
        "status_counts": dict(status),
        "status_pct": {k: rate(v) for k, v in status.items()},
        "raw_metric_success_pct": {k: rate(metric_hits[k]) for k in METRICS},
        "conditional_success": conditional,
        "issue_counts": dict(issue_counts.most_common()),
        "top_brokers_by_extractor_gaps": gap_by_broker[:15],
        "multi_name_notes": sum(1 for r in rows if r.get("multi_name")),
        "recommended_fix_batch": [
            x["broker"] for x in gap_by_broker[:8]
        ],
    }

    report = {
        "summary": summary,
        "issue_examples": dict(issue_examples),
        "by_extractor_status": {
            ext: {
                "n": c.get("n", 0),
                "full": c.get("full", 0),
                "partial": c.get("partial", 0),
                "failed": c.get("failed", 0),
                "full_pct": round(100 * c.get("full", 0) / max(c.get("n", 1), 1), 1),
            }
            for ext, c in sorted(by_extractor.items(), key=lambda x: -x[1].get("n", 0))
        },
        "rows": rows,
    }

    (out_dir / "full_corpus_audit.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # human-readable markdown
    md = [
        "# Full corpus extraction audit",
        "",
        f"Total PDFs: **{n}**",
        "",
        "## Status",
        "",
        f"- full: {status.get('full', 0)} ({rate(status.get('full', 0))}%)",
        f"- partial: {status.get('partial', 0)} ({rate(status.get('partial', 0))}%)",
        f"- failed: {status.get('failed', 0)} ({rate(status.get('failed', 0))}%)",
        "",
        "## Raw metric success %",
        "",
    ]
    for k in METRICS:
        md.append(f"- {k}: {rate(metric_hits[k])}%")
    md += ["", "## Conditional success (only when field appears present in PDF)", ""]
    for k, v in conditional.items():
        md.append(f"- {k}: {v['pct']}% ({v['hit']}/{v['applicable']} applicable)")
    md += ["", "## Issue taxonomy (counts)", ""]
    for k, v in issue_counts.most_common():
        md.append(f"- `{k}`: {v}")
    md += ["", "## Top brokers by extractor gaps (fix these first)", ""]
    for x in gap_by_broker[:12]:
        md.append(
            f"- **{x['broker']}** (n={x['n']}, full={x['full']}): gaps={x['gaps']}"
        )
    md += [
        "",
        "## Recommended fix batch",
        "",
        "1. Treat `field_absent_*` / `field_na_tp` as non-failures in scoring.",
        "2. Fix `extractor_gap_*` for top brokers listed above.",
        "3. Special-case multi-name morning/brief notes using query ticker.",
        "",
        "Full JSON: `.find-rpt/full_corpus_audit.json`",
    ]
    (out_dir / "full_corpus_audit.md").write_text("\n".join(md), encoding="utf-8")

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print("\nWrote .find-rpt/full_corpus_audit.json and .find-rpt/full_corpus_audit.md")


if __name__ == "__main__":
    main()
