"""Validation loop: if PDF signals say a field exists but extraction missed it, try alternate strategies."""

from __future__ import annotations

import re
from dataclasses import dataclass

from extractors.base import Passage, compute_extraction_status
from extractors import generic

# Preferred analyst email domains by broker keyword
BROKER_EMAIL_DOMAINS = {
    "ubs": ["ubs.com"],
    "jefferies": ["jefferies.com"],
    "goldman": ["gs.com"],
    "jp morgan": ["jpmorgan.com", "jpmchase.com"],
    "morgan stanley": ["morganstanley.com"],
    "deutsche": ["db.com"],
    "bnp": ["bnpparibas.com"],
    "berenberg": ["berenberg.com"],
    "abg": ["abgsc.se", "abgsc.no", "abgsc.com"],
    "dnb": ["dnbcarnegie.dk", "dnbcarnegie.no", "dnb.no"],
    "kepler": ["keplercheuvreux.com"],
    "citi": ["citi.com"],
    "danske": ["danskebank.com", "danskebank.se", "danskebank.dk"],
    "nordea": ["nordea.com"],
    "redburn": ["rothschildandco.com", "redburn.com"],
    "rothschild": ["rothschildandco.com"],
    "stifel": ["stifel.com"],
    "cic": ["cic.fr"],
    "oddo": ["oddo-bhf.com"],
    "pareto": ["paretosec.com"],
    "bofa": ["bofa.com", "bofasecurities.com"],
    "bank of america": ["bofa.com"],
}


@dataclass
class FieldSignals:
    has_tp: bool
    tp_is_na: bool
    has_rating: bool
    has_email: bool
    has_revision: bool
    has_eps: bool
    has_consensus: bool


def detect_signals(text: str) -> FieldSignals:
    return FieldSignals(
        has_tp=_has_substantive_tp(text),
        tp_is_na=bool(re.search(r"target\s*price.{0,30}n\.?a|tp\s*[:=].{0,15}n\.?a", text, re.I)),
        has_rating=_has_substantive_rating(text),
        has_email="@" in text,
        has_revision=_has_substantive_revision(text),
        # Substantive EPS (levels / adj / FY), not disclaimer lists like "EBITDA, EPS, cash flow"
        has_eps=_has_substantive_eps(text),
        has_consensus=_has_substantive_consensus(text),
    )


def _has_substantive_consensus(text: str) -> bool:
    """Only when consensus EPS/levels are stated — not bare 'vs consensus' narrative."""
    return bool(
        re.search(
            r"(?:Consensus EPS|EPS Consensus)\s*(?:\([^)]*\))?\s+[+\-\d\(]",
            text[:15000],
            re.I,
        )
        or re.search(
            r"EPS\s*-\s*Bloomberg\s*\([^)]*\)\s+[+\-\d\(]",
            text[:15000],
            re.I,
        )
    )


def _has_substantive_rating(text: str) -> bool:
    """Cover/recommendation rating — not disclaimer lists of rating definitions."""
    head = text[:4500]
    # Strip common ratings-definition boilerplate
    cleaned = re.sub(
        r"(?:Investment Banking Relationships|Ratings Distribution|Rating system|"
        r"definitions of our ratings|rating definitions).{0,2000}",
        " ",
        head,
        flags=re.I,
    )
    return bool(
        re.search(
            r"(?:Rating|Recommendation|Stock Rating|RATING|Action)\s*[:=\|\n]\s*"
            r"(Buy|Hold|Sell|Neutral|Overweight|Underweight|Outperform|Underperform|"
            r"Equal-?weight|Market Perform|Accumulate|Reduce|Conviction Buy)",
            cleaned,
            re.I,
        )
        or re.search(
            r"\n\s*(Buy|Hold|Sell|Neutral|Overweight|Underweight|Outperform|Underperform|"
            r"Equal-?weight|Market Perform|Accumulate|Reduce)\s*\n",
            cleaned,
            re.I,
        )
        or re.search(
            r"\b(?:reiterate|remain|maintain|upgrade|downgrade|initiate)\s+"
            r"(?:our\s+)?(?:to\s+)?(Buy|Hold|Sell|Neutral|Overweight|Underweight|Outperform|Underperform)",
            cleaned,
            re.I,
        )
    )


def _has_substantive_tp(text: str) -> bool:
    """True when a real TP/PO is stated (or explicitly n.a.), not disclaimer boilerplate."""
    head = text[:8000]
    if re.search(r"(?:target\s*price|price\s*target|price objective|kursziel|fair value)\s*[:=]?\s*(?:n\.?a\.?)", head, re.I):
        return True
    if re.search(
        r"(?:target\s*price|price\s*target|price objective|kursziel|12M\s+TP|12m\s+Price\s+Target|%\s*to\s*pt)\s*[:=]?\s*"
        r"(?:[A-Z]{3}|EUR|USD|GBP|CHF|SEK|NOK|DKK|\$|€|£)?\s*[\d]",
        head,
        re.I,
    ):
        return True
    if re.search(
        r"(?:raise|cut|trim|lower|increase|reduce|lift)\s+(?:our\s+)?(?:price target|target price|TP|PO)\s+"
        r"(?:from\s+)?(?:to\s+)?(?:[A-Z]{3}|€|£|\$)?\s*[\d]",
        head,
        re.I,
    ):
        return True
    if re.search(r"(?:Our\s+)?12-month\s+price target\s+(?:of|is)\s+(?:€|£|\$|[A-Z]{3})?\s*[\d]", head, re.I):
        return True
    return False


def _has_substantive_revision(text: str) -> bool:
    """True when estimate/TP revisions with numbers are present — not empty 'Estimate changes' headers."""
    head = text[:12000]
    norm = re.sub(r"\s+", " ", head)
    patterns = [
        r"Estimate changes\s*\(%\).{0,80}20\d{2}.{0,200}\b(?:EPS|CEPS|EBIT|Sales|NOI)\s+[+\-]?\d",
        r"Estimate Changes.{0,100}20\d{2}E.{0,400}\bEPS[^\d]{0,40}[+\-]?\d+\s*%",
        r"\bPrior EPS\b.{0,60}[\d]",
        r"\bEPS\s+new\s+[+\-\d\(]",
        r"\bEPS\s+old\s+[+\-\d\(]",
        r"(?:increase|reduce|raise|cut|trim|lower)\s+(?:our\s+)?(?:adj\.?\s+)?(?:EPS|EBIT|estimates?).{0,40}(?:by\s+)?[+\-]?\d",
        r"(?:increase|reduce|raise|cut|trim|lower).{0,30}FY\s*\d{2}/\d{2}.{0,40}(?:EPS|EBIT|revenue).{0,20}(?:by\s+)?c?[\d]",
        r"(?:price target|target price|\bTP\b|\bPO\b).{0,40}from\s+[\d]",
        r"(?:raise|cut|trim|lower|increase)\s+(?:our\s+)?(?:price target|target price|\bTP\b|\bPO\b)\s+"
        r"(?:from\s+)?(?:to\s+)?(?:[A-Z]{3}|€|£|\$)?\s*[\d]",
        r"(?:PO|TP|price target|target price)\s+goes\s+up\s+to\s+[\d]",
        r"Changes made in this note.{0,120}(?:[+\-]?\d+\.?\d*\s*%|from\s+[\d])",
        r"Estimates changes.{0,200}(?:[+\-]?\d+\.?\d*\s*%|∆\s*%)",
        r"what.?s changed.{0,80}(?:From|To|Price target).{0,40}[\d]",
        r"trim\s+20\d{2}/\d{2}\s+EPS\s+by",
        r"EPS estimates raised\s+\d+\s*%",
        r"(?:raised|cut|trimmed)\s+(?:our\s+)?(?:FY\d{2}|20\d{2}).{0,40}(?:EPS|EBIT).{0,20}\d\s*%",
        r"(?:increase|raise|lift|cut|reduce|lower)\s+our\s+(?:value[-\s]creation-based\s+)?(?:target price|TP)\s+"
        r"(?:to|from)\s+(?:[A-Z]{3}|€|£|\$|GBp)?\s*[\d]",
        r"PO\s+(?:goes\s+up|also\s+declines|declines|rises)\s+to\s+",
        r"cut\s+our\s+FY\s*\d{2}-\d{2}E?\s+[\w/]+\s+estimates\s+by",
        r"EPS New Adj",
        r"raise\s+our\s+estimates\s+and\s+target price",
        r"Target price raised|TP raised",
        r"raise\s+EPS\s+c?\d",
    ]
    return any(re.search(p, norm, re.I) for p in patterns)


def _has_substantive_eps(text: str) -> bool:
    cleaned = re.sub(
        r"EBITDA,\s*EPS,\s*cash flow|DCF\),\s*EBITDA,\s*EPS|methodologies[^\n]{0,200}\bEPS\b",
        " ",
        text[:12000],
        flags=re.I,
    )
    # Chart titles like "consensus EPS" with no nearby levels are not estimate tables
    cleaned = re.sub(r"consensus EPS(?![^\n]{0,40}[\d])", " ", cleaned, flags=re.I)
    return bool(
        re.search(
            r"(?:EPS\s*(?:adj|adjusted|reported|new|old|,|\(|of\b|estimates)|"
            r"adj\.?\s*EPS|Consensus EPS|EPS Consensus|FY\d{2}E?\s*EPS|"
            r"EPS\s+[\d\.\-(]|Per share data|earnings per share|"
            r"EPS\s*-\s*Bloomberg|EPS\s*\(\$)",
            cleaned,
            re.I,
        )
    )


def pick_broker_email(text: str, broker: str) -> str:
    emails = re.findall(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", text[:15000])
    b = broker.lower()
    preferred = []
    for key, domains in BROKER_EMAIL_DOMAINS.items():
        if key in b:
            preferred = domains
            break
    skip = ("factset", "example.com", "noreply", "donotreply", "bloomberg.net", "copyright")
    ranked = []
    for email in emails:
        low = email.lower()
        if any(s in low for s in skip):
            continue
        score = 0
        if preferred and any(d in low for d in preferred):
            score += 10
        ranked.append((score, email))
    ranked.sort(key=lambda x: -x[0])
    return ranked[0][1] if ranked else ""


def alt_target_price(text: str) -> str:
    """Alternate TP strategies when primary parse fails but TP language exists."""
    t = (
        text[:12000]
        .replace("€", "EUR ")
        .replace("£", "GBP ")
        .replace("$", "USD ")
        .replace("\uf0a1", " ")
    )
    patterns = [
        r"12m\s+Price Target:\s*(€|EUR|£|GBP|\$|USD)?\s*([\d,\.]+)",
        r"(?:Our\s+)?12-month\s+price target\s+(?:of|is)\s*(€|EUR|£|GBP|\$|USD)?\s*([\d,\.]+)",
        r"Target Price\s*\(EUR\)\s*\n\s*([\d,\.]+)",
        r"Target Price\s*\(([A-Z]{3})\)\s*\n\s*([\d,\.]+)",
        r"PRICE TARGET\s*\|\s*% TO PT\s*\n\s*(USD|EUR|GBP|SEK)?\s*([\d,\.]+)",
        r"PRICE TARGET.*?\n\s*(USD|EUR|GBP|\$)?\s*([\d,\.]+)\s*\|",
        r"Target price:\s*([A-Z]{3})\s*([\d,\.]+)",
        r"Target Price:\s*\n\s*([A-Z]{3})\s*([\d,\.]+)",
        r"TP\s*(?:EUR|USD|GBP)?\s*([\d,\.]+)",
        r"Fair value\s*\n\s*([A-Z]{3})\s*([\d,\.]+)",
        r"Kursziel\s*[:=]?\s*(CHF|EUR)?\s*([\d',\.]+)",
    ]
    for pat in patterns:
        m = re.search(pat, t, re.I)
        if not m:
            continue
        groups = [g for g in m.groups() if g]
        ccy, num = "", ""
        for g in groups:
            if re.fullmatch(r"[A-Za-z]{2,3}|\$", g):
                ccy = "USD" if g == "$" else g.upper()
            elif re.match(r"^[\d,',\.]+$", g):
                num = g.replace(",", "").replace("'", "")
        if num:
            return f"{ccy}{num}".strip()
    # fallback to generic
    return generic.parse_target_price(t)


def alt_rating(text: str) -> str:
    patterns = [
        r"RATING\s*\n\s*(BUY|HOLD|SELL|NEUTRAL|OVERWEIGHT|UNDERWEIGHT)",
        r"Rating:\s*\n\s*(Market Perform|Buy|Hold|Sell|Neutral|Overweight|Underweight|Outperform)",
        r"\n(Buy|Hold|Sell)\s*\nSince\s+\d{2}/\d{2}/\d{4}",  # CIC
        r"remain\s+(Neutral|Overweight|Underweight|Buy|Hold)",
        r"Reiterate\s+(Buy|Hold|Sell|Neutral|Outperform|Overweight)",
        r"([A-Za-z][A-Za-z0-9&\.\-'\s]{2,40})\s+(Hold|Buy|Sell)\s*\n",  # Kepler: Company Hold
        r"We have a (Hold|Buy|Sell) rating",
        r"\b(Market Perform|Outperform|Underperform)\b",
    ]
    for pat in patterns:
        m = re.search(pat, text[:8000], re.I)
        if m:
            # last group often the rating
            g = m.group(m.lastindex or 1)
            if g.lower() in {"since"}:
                continue
            return f"Rating: {g.strip()}"
    return generic.parse_rating(text)


def alt_company(text: str, ticker_hint: str = "") -> str:
    # PDF metadata title
    m = re.search(
        r"PDF_TITLE:\s*([A-Za-z][A-Za-z0-9&\.\-'\s]{1,60}?)\s*\(([A-Za-z0-9]+\.[A-Z]{1,3})\)",
        text[:500],
    )
    if m:
        return m.group(1).strip()

    # CIC morning: first company after header (incl. OCR-spaced "Name  - …")
    m = re.search(
        r"MORNING NEWS ANALYSER.*?\n(?:Legal.*?\n)?(?:CIC.*?\n)?\d+\n([A-Za-z][^\n]{1,50})\n(Buy|Hold|Sell|Neutral)",
        text[:4000],
        re.I | re.S,
    )
    if m:
        return m.group(1).strip()
    m = re.search(
        r"MORNING NEWS ANALYSER.*?\n\s*\d+\s*\n([A-Za-z][A-Za-z0-9&\.\-'\s]{1,40}?)\s+-\s+",
        text[:4000],
        re.I | re.S,
    )
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip()

    # MS: "Company | Europe"
    m = re.search(
        r"^([A-Z][A-Za-z0-9&\.\-/'+\s]{1,55}?)\s*\|\s*(?:Europe|US|Asia|Global|UK)\b",
        text[:3000],
        re.M,
    )
    if m and not re.search(r"research|update|equity", m.group(1), re.I):
        return m.group(1).strip()

    # Nordea: "Company – Hold:"
    m = re.search(
        r"^([A-Z][A-Za-z0-9&\.\-+/' ]{1,50}?)\s+[–—-]\s+(Hold|Buy|Sell|Neutral)\b",
        text[:3000],
        re.M | re.I,
    )
    if m:
        return m.group(1).strip()

    # Alantra brief
    m = re.search(
        r"^([A-Z][A-Za-z0-9&\.\-'\s]{1,40}?)\s*\([€$£]?[\d\.,]+,\s*(?:NEUTRAL|BUY|SELL|HOLD)",
        text[:3000],
        re.M | re.I,
    )
    if m:
        return m.group(1).strip()

    # ZKB: Company (TICKER)
    m = re.search(r"^([A-Z][A-Za-z0-9&\.\-'\s]{2,40})\s*\(([A-Z]{2,6})\)\s*$", text[:3000], re.M)
    if m:
        return m.group(1).strip()

    # Kepler: "EuroGroup Laminations Hold"
    m = re.search(
        r"^([A-Z][A-Za-z0-9&\.\-'\s]{2,50})\s+(Hold|Buy|Sell)\s*$",
        text[:3000],
        re.M,
    )
    if m:
        return m.group(1).strip()

    # Jefferies: Country | Sector \n Company
    m = re.search(
        r"(?:UK|US|Denmark|Sweden|Germany|France|Italy|Spain|Switzerland|Netherlands)\s*\|\s*[^\n]+\n([A-Z][^\n]{2,50})\nEquity Research",
        text[:3000],
        re.I,
    )
    if m:
        return m.group(1).strip()

    if ticker_hint:
        base = re.split(r"[\s/]", ticker_hint)[0]
        base = re.sub(r"[^A-Za-z0-9]", "", base)
        if len(base) >= 2:
            # Prefer a short standalone line containing/near the ticker
            m = re.search(
                rf"(?m)^([A-ZÀ-ÖØ-Ý][^\n]{{2,45}})\n(?:[^\n]{{0,80}})?{re.escape(base)}\b",
                text[:8000],
                re.I,
            )
            if m:
                co = generic._clean_company(m.group(1))
                if co:
                    return co
            m = re.search(rf"(?m)^({re.escape(base)}|[A-Z][A-Za-z0-9&\.\-/'+ ]{{2,40}})\s*$", text[:5000])
            # Company name that is exactly a known short token near ticker mention
            for ln in text[:6000].splitlines():
                ln = ln.strip()
                if base.lower() in ln.lower() and 2 < len(ln) < 45 and not re.search(r"grow more|reasons|reiterating|offset", ln, re.I):
                    # "IMCD" alone or "Company (IMCD NA)"
                    if ln.upper() == base.upper() or re.match(rf"^.{{0,40}}\({re.escape(base)}", ln, re.I):
                        co = generic._clean_company(re.split(r"\s*\(", ln)[0])
                        if co:
                            return co
            # Standalone repeated name line equal to first token of long titles like "IMCD May 2026"
            for ln in text[:3000].splitlines():
                ln = ln.strip()
                if ln.upper() == base.upper() or (ln.split()[:1] and ln.split()[0].upper() == base.upper() and len(ln) < 20):
                    return ln.split()[0]

    return generic.parse_company(text)


def alt_eps(text: str) -> tuple[list[float], list[float]]:
    broker, consensus = generic.parse_eps_numbers(text)
    if broker:
        return broker, consensus

    norm = re.sub(r"\s+", " ", text[:12000])
    n = generic._EPS_NUM

    # Redburn Adjusted diluted EPS
    m = re.search(rf"Adjusted,? diluted EPS[^\d(]{{0,30}}({n})\s+({n})", norm, re.I)
    if m:
        broker = [generic._eps_float(m.group(1)), generic._eps_float(m.group(2))]

    # ZKB estimate-change block: "EPS new -0.23 0.55 0.70"
    if not broker:
        m = re.search(rf"EPS\s+new\s+({n})\s+({n})(?:\s+({n}))?", norm, re.I)
        if m:
            broker = [generic._eps_float(g) for g in m.groups() if g]

    if not consensus:
        m = re.search(
            rf"(?:Consensus EPS|EPS Consensus)(?:\s*\([^)]*\))?\s+({n})\s+({n})(?:\s+({n}))?",
            norm,
            re.I,
        )
        if m:
            consensus = [generic._eps_float(g) for g in m.groups() if g]

    return broker, consensus


def validate_and_backfill(result, broker: str, ticker_hint: str = ""):
    """Mutate ExtractedReport: retry missing fields when signals say they exist."""
    text = "\n".join(p.text for p in result.pages[:4]) if result.pages else (result.full_text or "")
    signals = detect_signals(text)
    attempts = []

    # Email — always prefer broker-domain match
    if signals.has_email:
        email = pick_broker_email(text, broker)
        if email and (not result.analyst_email or result.analyst_email.lower() != email.lower()):
            if not result.analyst_email:
                attempts.append("email_domain_pick")
            result.analyst_email = email

    # Company
    if not result.company or not generic._clean_company(result.company):
        co = alt_company(text, ticker_hint)
        if co:
            result.company = co
            attempts.append("alt_company")
        elif ticker_hint:
            # last resort: use ticker token as label rather than inventing a name
            result.company = ticker_hint.split()[0]
            attempts.append("company_ticker_fallback")
    else:
        result.company = generic._clean_company(result.company) or result.company

    # TP
    if not result.target_price and signals.has_tp:
        if signals.tp_is_na:
            result.target_price = "n.a."
            attempts.append("tp_na_explicit")
        else:
            tp = alt_target_price(text)
            if tp:
                result.target_price = tp
                attempts.append("alt_tp")

    # Rating
    if not result.rating_change and signals.has_rating:
        rating = alt_rating(text)
        if rating:
            result.rating_change = rating if rating.lower().startswith("rating") else f"Rating: {rating}"
            attempts.append("alt_rating")

    # EPS
    if not result.broker_eps and signals.has_eps:
        broker_eps, consensus = alt_eps(text)
        if broker_eps:
            result.broker_eps = broker_eps
            attempts.append("alt_eps")
        if consensus and not result.consensus_eps:
            result.consensus_eps = consensus
            attempts.append("alt_consensus")

    # Revisions when language present
    if not result.revisions and signals.has_revision:
        revs = generic.parse_revision_mentions(text)
        if revs:
            result.revisions = revs
            attempts.append("alt_revisions")

    # Passages fallback
    if not result.key_passages and result.pages:
        para = re.sub(r"\s+", " ", result.pages[0].text)[:400]
        if len(para) > 80:
            result.key_passages = [Passage(page=1, text=para, label="why_now")]
            attempts.append("alt_passage")

    result.extraction_status = compute_extraction_status(result)
    # stash debug on object if useful
    result.low_confidence = bool(attempts) and result.extractor_used.endswith("fallback")
    return result, signals, attempts
