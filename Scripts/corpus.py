from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

import fitz

from config import load_config

GERMANY_SUFFIXES = {"GY", "GR", "DE"}
BLOOMBERG_RE = re.compile(
    r"Bloomberg:\s*([A-Z0-9/]+(?:\s+[A-Z]{2})?)",
    re.IGNORECASE,
)
TICKER_RE = re.compile(
    r"\b([A-Z]{1,5}(?:/[A-Z]+)?)\s+(GY|GR|LN|FP|NA|SW|IM|DC|SS|NO|BB|PL|AV|SM|UW|CN|HK|IT|SQ|ID|DE)\b"
)
ANALYST_RE = re.compile(
    r"^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:,\s*[A-Z]+)?)\s*$",
    re.MULTILINE,
)
RATING_CHANGE_RE = re.compile(r"#RatingChange|Rating change|Downgrade|Upgrade", re.I)
DATE_IN_FILENAME_RE = re.compile(r"^(\d{8})_(.+?)_([a-f0-9]+)\.pdf$", re.I)


@dataclass
class ReportRecord:
    file: str
    date: str
    broker: str
    company: str
    tickers: list[str]
    analyst: str
    analyst_email: str
    report_type: str
    title_line: str


def parse_filename(path: Path) -> tuple[str, str, str] | None:
    m = DATE_IN_FILENAME_RE.match(path.name)
    if not m:
        return None
    return m.group(1), m.group(2), m.group(3)


def normalize_ticker(ticker: str) -> tuple[str, str]:
    parts = ticker.strip().upper().split()
    if len(parts) >= 2:
        return parts[0], parts[1]
    return parts[0], ""


def suffixes_compatible(a: str, b: str) -> bool:
    if not a or not b:
        return True
    if a == b:
        return True
    if a in GERMANY_SUFFIXES and b in GERMANY_SUFFIXES:
        return True
    return False


def tickers_match(query: str, candidates: list[str]) -> bool:
    q_base, q_suffix = normalize_ticker(query)
    for cand in candidates:
        c_base, c_suffix = normalize_ticker(cand)
        if q_base == c_base and suffixes_compatible(q_suffix, c_suffix):
            return True
    return False


def broker_similarity(query: str, broker: str) -> float:
    q = query.lower().strip()
    b = broker.lower().strip()
    if q in b or b in q:
        return 1.0
    aliases = {
        "bofa": "bofa global research",
        "bank of america": "bofa global research",
        "jpm": "jp morgan",
        "j.p. morgan": "jp morgan",
        "gs": "goldman sachs",
        "ms": "morgan stanley",
        "db": "deutsche bank research",
        "ubs": "ubs",
    }
    q_norm = aliases.get(q, q)
    b_norm = aliases.get(b, b)
    return SequenceMatcher(None, q_norm, b_norm).ratio()


def normalize_date(date_str: str) -> str:
    s = re.sub(r"\D", "", date_str)
    if len(s) == 8:
        return s
    for fmt in ("%d %b %Y", "%d %B %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str.strip(), fmt).strftime("%Y%m%d")
        except ValueError:
            continue
    raise ValueError(f"Unrecognized date format: {date_str}")


def extract_tickers(text: str) -> list[str]:
    found: list[str] = []
    for m in BLOOMBERG_RE.finditer(text):
        found.append(m.group(1).strip().upper())
    for m in TICKER_RE.finditer(text):
        found.append(f"{m.group(1)} {m.group(2)}")
    return list(dict.fromkeys(found))


def extract_company(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    m = re.search(r"Company\s*\n\s*([^\n]+)", text)
    if m:
        return m.group(1).strip()

    m = re.search(r"Share price:\s*\S+\s*\n\s*([A-Za-z][A-Za-z0-9&\-\.'\s]+?)\s*\n", text, re.I)
    if m:
        return m.group(1).strip()

    for line in lines[:40]:
        m = re.match(
            r"^([A-Za-z][A-Za-z0-9&\-\.'\s]+?)\s+"
            r"(Hold|Buy|Sell|Neutral|Outperform|Underperform|Overweight|Underweight)\s*[\(|\|]",
            line,
            re.I,
        )
        if m:
            return m.group(1).strip()
    return ""


def extract_analyst_email(text: str) -> str:
    emails = re.findall(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", text[:4000])
    return emails[0] if emails else ""


def extract_analyst(text: str) -> str:
    for line in text.splitlines():
        if re.search(r",\s*(CFA|ACA|PhD)\b", line):
            return line.strip()
        if re.search(r"\+\d{2,3}\s*\d", line):
            idx = text.splitlines().index(line)
            if idx > 0:
                prev = text.splitlines()[idx - 1].strip()
                if prev and not prev.startswith("+"):
                    return prev
    return ""


def detect_report_type(text: str) -> str:
    head = text[:2500].lower()
    if "#ratingchange" in head or "rating change" in head:
        return "rating change"
    if "preview" in head:
        return "preview"
    if "review" in head or "results" in head:
        return "results review"
    if "initiation" in head or "initiat" in head:
        return "initiation"
    if "roadshow" in head:
        return "roadshow"
    if "reiterate" in head:
        return "reiteration"
    return "note"


def extract_title_line(text: str, company: str) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for line in lines[:30]:
        if company and company.lower() in line.lower() and re.search(
            r"\b(Buy|Hold|Sell|Neutral|Outperform|Underperform|Overweight|Underweight)\b",
            line,
            re.I,
        ):
            return line
    for line in lines[:30]:
        if re.search(r"\b(Buy|Hold|Sell)\b", line, re.I) and len(line) < 120:
            return line
    return company or "Research note"


def index_pdf(path: Path) -> ReportRecord | None:
    parsed = parse_filename(path)
    if not parsed:
        return None
    date, broker, _ = parsed
    doc = fitz.open(path)
    text = ""
    for i in range(min(3, len(doc))):
        text += doc[i].get_text() + "\n"
    doc.close()

    company = extract_company(text)
    return ReportRecord(
        file=path.name,
        date=date,
        broker=broker,
        company=company,
        tickers=extract_tickers(text),
        analyst=extract_analyst(text),
        analyst_email=extract_analyst_email(text),
        report_type=detect_report_type(text),
        title_line=extract_title_line(text, company),
    )


def build_index(corpus_path: Path | None = None, force: bool = False) -> list[ReportRecord]:
    cfg = load_config()
    corpus = corpus_path or cfg["corpus_path"]
    cache_dir = cfg["cache_dir"]
    cache_dir.mkdir(parents=True, exist_ok=True)
    index_path = cache_dir / "index.json"

    if index_path.exists() and not force:
        data = json.loads(index_path.read_text(encoding="utf-8"))
        records = []
        for row in data:
            row.setdefault("analyst_email", "")
            records.append(ReportRecord(**row))
        return records

    records: list[ReportRecord] = []
    for pdf in sorted(corpus.glob("*.pdf")):
        try:
            rec = index_pdf(pdf)
            if rec:
                records.append(rec)
        except Exception:
            continue

    index_path.write_text(
        json.dumps([asdict(r) for r in records], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return records


def find_report(
    ticker: str,
    date: str,
    broker: str,
    corpus_path: Path | None = None,
) -> tuple[ReportRecord, Path]:
    cfg = load_config()
    corpus = corpus_path or cfg["corpus_path"]
    target_date = normalize_date(date)
    records = build_index(corpus)

    candidates = [
        r
        for r in records
        if r.date == target_date and tickers_match(ticker, r.tickers)
    ]
    if not candidates:
        candidates = [
            r
            for r in records
            if r.date == target_date and ticker.split()[0].upper() in r.file.upper()
        ]

    if not candidates:
        raise FileNotFoundError(
            f"No report for ticker={ticker!r} date={target_date} in corpus."
        )

    scored = sorted(
        ((broker_similarity(broker, r.broker), r) for r in candidates),
        key=lambda x: x[0],
        reverse=True,
    )
    best_score, best = scored[0]
    if best_score < 0.55:
        names = ", ".join({r.broker for _, r in scored[:5]})
        raise FileNotFoundError(
            f"No broker match for {broker!r} on {target_date} / {ticker}. "
            f"Closest brokers: {names}"
        )

    pdf_path = corpus / best.file
    if not pdf_path.exists():
        raise FileNotFoundError(f"Indexed file missing: {pdf_path}")
    return best, pdf_path
