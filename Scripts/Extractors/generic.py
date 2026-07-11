from __future__ import annotations

import re

from extractors.base import ExtractedReport, PageText, compute_extraction_status, find_passages

# --- shared helpers used by generic + broker modules ---

TP_PATTERNS = [
    r"Target\s*[Pp]rice[:\s]*([A-Z]{3})?\s*([\d,\.]+)\s*(?:\((?:was\s+|from\s+|up from\s+|down from\s+)?([A-Z]{3})?\s*([\d,\.]+)\))?",
    r"Price\s*[Tt]arget[:\s\(]*([A-Z]{3})?\)?[:\s]*([\d,\.]+)",
    r"Price\s*Target\s*\(([A-Z]{3})\)\s*\n?\s*([\d,\.]+)",
    r"Price target\s*\n\s*([A-Z]{3})\s*([\d,\.]+)",
    r"TP[:\s]+([A-Z]{3})?\s*([\d,\.]+)",
    r"price target has been revised to\s*([A-Z]{3})?\s*([\d,\.]+)",
    r"target price\s+(?:increases|reduced|raised|cut|revised)?\s*(?:to\s+)?([A-Z]{3}|S[Ff]r|SEK|EUR|GBP|USD|NOK|DKK|CHF)?\s*([\d,\.]+)\s*(?:\((?:from|was|up from|down from)\s*([\d,\.]+)\))?",
    r"TARGET PRICE\s+([A-Z]{3})?\s*([\d,\.]+)",
    r"Price objective[:\s]*([A-Z]{3})?\s*([\d,\.]+)",
    r"(?:PT|PO)\s*[:=]\s*([A-Z]{3})?\s*([\d,\.]+)",
    r"revised to\s*(SEK|EUR|NOK|DKK|GBP|USD|CHF)\s*([\d,\.]+)\s*\((?:up from|from)\s*(?:SEK|EUR|NOK|DKK|GBP|USD|CHF)?\s*([\d,\.]+)\)",
]

RATING_PATTERNS = [
    r"\b(Overweight|Underweight|Equal-weight|Equal Weight|Outperform|Underperform|Neutral|Buy|Sell|Hold|OW|UW|EW|OP)\b",
    r"Stock Rating\s*\n\s*([A-Za-z\- ]+)",
    r"Rating:\s*\n?\s*(Hold|Buy|Sell|Neutral|Overweight|Underweight)(?:\s*\([^)]*\))?",
    r"We reiterate (?:our )?(Hold|Buy|Sell|Outperform|Overweight|Equal-weight)",
    r"reiterate (?:our )?(OP|OW|UW|EW|Hold|Buy)",
]

COMPANY_PATTERNS = [
    r"^([A-Z][A-Za-z0-9&\.\-'\s]{1,60}?)\s*\(([A-Z0-9\.]+(?:\s*,\s*[A-Z0-9\.]+)*)\)",  # Hexagon AB (HEXAB SS)
    r"Company\s*\n\s*([^\n]+)",
    r"Share price:\s*\S+\s*\n\s*([A-Za-z][^\n]{2,60})",
    r"^([A-Z][A-Za-z0-9&\.\-'\s]{2,50})\n(?:Sound|Weak|Strong|Focus|NTT|Headline|Our Take|Fast|Update)",
    r"([A-Za-z][A-Za-z0-9&\.\-'\s]{2,50})\s*\(([A-Z]{2,6}\.[A-Z]{1,3})\):",  # FinecoBank SpA (FBK.MI):
    r"CEMENTIR|Compass Group|Hannover Re|Grenergy|Ericsson|Bavarian Nordic|AstraZeneca|Vodafone",
]


def parse_target_price(text: str) -> str:
    head = text[:5000]
    for pat in TP_PATTERNS:
        m = re.search(pat, head, re.I)
        if m:
            groups = [g for g in m.groups() if g]
            # normalize currency-ish tokens
            ccy = ""
            nums = []
            for g in m.groups():
                if not g:
                    continue
                if re.fullmatch(r"[A-Za-z]{2,3}", g) or g.lower() in {"sfr", "sek", "eur", "gbp", "usd", "nok", "dkk"}:
                    ccy = g.upper().replace("SFR", "SFr")
                elif re.match(r"^[\d,\.]+$", g):
                    nums.append(g.replace(",", ""))
            if nums:
                if len(nums) >= 2:
                    return f"{ccy}{nums[0]} (was {ccy}{nums[1]})".strip()
                return f"{ccy}{nums[0]}".strip()
    return ""


def parse_rating(text: str) -> str:
    head = text[:4000]
    # prefer explicit rating lines
    for pat in [
        r"Stock Rating\s*\n\s*([A-Za-z\- ]+)",
        r"Rating:\s*\n?\s*(Hold|Buy|Sell|Neutral|Overweight|Underweight)(?:\s*\(([^)]*)\))?",
        r"\n(HOLD|BUY|SELL|OUTPERFORM|UNDERPERFORM|OVERWEIGHT|UNDERWEIGHT|EQUAL-WEIGHT)\s*\n",
        r"We reiterate (?:our )?(Hold|Buy|Sell|Outperform|Overweight|Equal-weight|OP|OW|EW)",
        r"(?:rating|reiterate).*?\b(Hold|Buy|Sell|Outperform|Overweight|Equal-weight)\b",
    ]:
        m = re.search(pat, head, re.I)
        if m:
            return re.sub(r"\s+", " ", m.group(1)).strip()
    return ""


def _clean_company(name: str) -> str:
    name = re.sub(r"\s+", " ", (name or "").strip())
    name = re.sub(r"^PDF_TITLE:\s*", "", name, flags=re.I)
    name = re.sub(r"^(BRIEF NEWS|Flash Comment|Update|Global Research)\s+", "", name, flags=re.I)
    if len(name) > 55:
        name = name[:55].rsplit(" ", 1)[0]
    name = name.strip(" -–—|:")
    # Reject obvious non-names
    low = name.lower()
    if low in {"ebit", "ebitda", "eps", "buy", "hold", "sell", "update", "neutral", "pdf_title"}:
        return ""
    if re.search(r"\b(reasons to|grow more|reiterating buy|positioned at|lower ad growth|blockbuster|hamburg complex|fy\d{2}/\d{2})\b", low):
        return ""
    if name.startswith("PDF_TITLE"):
        return ""
    return name


def parse_company(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("PDF_TITLE:")]
    head = "\n".join(lines[:80])
    # Keep metadata separately
    meta = ""
    m = re.search(r"PDF_TITLE:\s*([^\n]+)", text[:300])
    if m:
        meta = m.group(1).strip()
        mm = re.search(r"^([A-Za-z][^\n(]{1,60}?)\s*\(([A-Za-z0-9]+\.[A-Z]{1,3})\)", meta)
        if mm:
            return _clean_company(mm.group(1))

    # MS: "Aurubis AG | Europe"
    m = re.search(r"^([A-Z][^\n|]{1,55}?)\s*\|\s*(?:Europe|US|Asia|Global|Nordic|UK)\b", head, re.M)
    if m and not re.search(r"research|update|equity|securities", m.group(1), re.I):
        co = _clean_company(m.group(1))
        if co:
            return co

    # Nordea: "Gränges – Hold:"
    m = re.search(
        r"^(\d+\s*)?([A-ZÀ-ÖØ-Ý][^\n–—-]{1,50}?)\s+[–—-]\s+(Hold|Buy|Sell|Neutral)\b",
        head,
        re.M | re.I,
    )
    if m:
        co = _clean_company(m.group(2))
        if co:
            return co

    # Alantra: "ACS (€137.20, NEUTRAL, TP €113.70):"
    m = re.search(
        r"^(?:BRIEF NEWS\s+)?([A-Z][^\n(]{1,40}?)\s*\([€$£]?[\d\.,]+,\s*(?:NEUTRAL|BUY|SELL|HOLD|OUTPERFORM)",
        head,
        re.M | re.I,
    )
    if m:
        co = _clean_company(m.group(1))
        if co:
            return co

    # Citi/GS ticker form
    m = re.search(r"^([A-Z][^\n(]{1,55}?)\s*\(([A-Za-z0-9]{1,8}\.[A-Z]{1,3})\)", head, re.M)
    if m and not any(x in m.group(1).lower() for x in ("equity", "research", "goldman", "morgan", "deutsche", "jefferies")):
        co = _clean_company(m.group(1))
        if co:
            return co

    m = re.search(
        r"^([A-Z][^\n(]{1,55}?)\s*\(([A-Z0-9]{1,6}(?:\.[A-Z]{1,3})?(?:\s*,\s*[A-Z0-9\.]+)*)\)",
        head,
        re.M,
    )
    if m and not any(x in m.group(1).lower() for x in ("equity", "research", "goldman", "morgan", "deutsche", "jefferies")):
        co = _clean_company(m.group(1))
        if co:
            return co

    m = re.search(r"Company\s*\n\s*([^\n]+)", text)
    if m:
        co = _clean_company(m.group(1))
        if co:
            return co

    m = re.search(r"Global Research\s*\n+([A-Z][^\n]{1,50})\n", head, re.I)
    if m and not re.search(r"research|update|equity|page|disclosure", m.group(1), re.I):
        co = _clean_company(m.group(1))
        if co:
            return co

    m = re.search(r"^([A-Z][^\n]{2,50})\nNEWSFLASH\b", head, re.M)
    if m:
        co = _clean_company(m.group(1))
        if co:
            return co

    m = re.search(
        r"^([A-Z][^\n]{2,40})\n(?:1Q|2Q|3Q|4Q|Q1|CMD|Nice|We reiterate)",
        head,
        re.M,
    )
    if m and not re.search(r"for disclosures|pareto securities|may 20", m.group(1), re.I):
        co = _clean_company(m.group(1))
        if co:
            return co

    skip = {
        "equity research", "fast comment", "fast take", "global research", "europe equity research",
        "update", "hold", "buy", "sell", "overweight", "underweight", "contents", "our take",
        "flash", "securities research report", "equities", "brief news", "ab", "m", "1",
        "flash comment", "ebit", "ebitda",
    }
    for i, line in enumerate(lines[:40]):
        low = line.lower().strip("•- ")
        if low in skip or len(line) < 3 or len(line) > 55:
            continue
        if re.search(r"@|http|page \d|disclosure|analyst|finra|refer to|for disclosures|cut pt|offset by", low):
            continue
        if re.match(r"^\d{1,2}\s+\w+\s+\d{4}", line):
            continue
        if line.count("|") >= 2:
            parts = [p.strip() for p in line.split("|")]
            if parts[-1] and len(parts[-1]) > 2:
                co = _clean_company(parts[-1])
                if co:
                    return co
        if re.match(r"^[A-ZÀ-ÖØ-Ý].{1,50}$", line) and not re.search(r"\d{4}", line):
            if i + 1 < len(lines) and (
                re.search(r"\b(HOLD|BUY|SELL|Target|Share price|Overweight|OUTPERFORM|Headline|Equity Research|NEWSFLASH|Guidance|UBS Rheintal)\b", lines[i + 1], re.I)
                or re.search(r"[A-Z]{2,6}[\.\-][A-Z]{1,3}|[A-Z]{2,6}\s+[A-Z]{2}", lines[i + 1])
            ):
                co = _clean_company(line)
                if co:
                    return co
            if re.search(r"\([A-Z0-9\.\s,]+\)", line):
                co = _clean_company(re.split(r"\s*\(", line)[0])
                if co:
                    return co

    m = re.search(r"^([A-Z][A-Z0-9&\.\- ]{2,40})\s+(OUTPERFORM|UNDERPERFORM|BUY|HOLD|SELL)\b", head, re.M)
    if m:
        co = _clean_company(m.group(1).title() if m.group(1).isupper() else m.group(1))
        if co:
            return co

    m = re.search(
        r"(?:Denmark|Sweden|Norway|Germany|France|UK|Italy|Spain|Switzerland|Netherlands|Belgium|Americas)\s*\|\s*[^|]+\|\s*([^\n|]+)",
        head,
    )
    if m:
        co = _clean_company(m.group(1))
        if co:
            return co

    m = re.search(r"(?:Americas|Europe|Asia)\s*-\s*[^\n]+\n([A-Z][^\n]{2,50})\n", head)
    if m:
        co = _clean_company(m.group(1))
        if co:
            return co

    return ""


_EPS_NUM = r"(?:\((?:\-)?[\d]+(?:\.\d+)?\)|(?:\-)?[\d]+(?:\.\d+)?)(?!\s*%)"


def _eps_float(tok: str) -> float:
    tok = tok.strip().replace(",", "")
    if tok.startswith("(") and tok.endswith(")"):
        return -float(tok[1:-1])
    return float(tok)


def parse_revision_mentions(text: str) -> list[dict]:
    rows: list[dict] = []
    head = text[:12000]
    norm = re.sub(r"\s+", " ", head)

    def _add(metric: str, fy1: str, ch: str, fy2: str = "", ch2: str = "", **extra):
        rows.append(
            {
                "metric": metric,
                "fy1": fy1,
                "change_fy1": ch,
                "fy2": fy2,
                "change_fy2": ch2,
                **extra,
            }
        )

    # "increase/reduce our 2026/27/28 EPS by x%/y%/z%"
    m = re.search(
        r"(?:increase|reduce|raise|cut|trim|lower|nudge)\s+(?:our\s+)?(?:20)?(\d{2})/(\d{2})(?:/(\d{2}))?\s+EPS\s+by\s+"
        r"([+\-]?\d+\.?\d*%?)/([+\-]?\d+\.?\d*%?)(?:/([+\-]?\d+\.?\d*%?))?",
        norm,
        re.I,
    )
    if m:
        fys = [m.group(1), m.group(2)] + ([m.group(3)] if m.group(3) else [])
        chgs = [m.group(4), m.group(5)] + ([m.group(6)] if m.group(6) else [])
        verb = m.group(0).lower()
        for fy, ch in zip(fys, chgs):
            sign = "" if ch.startswith(("+", "-")) else ("+" if any(v in verb for v in ("increase", "raise")) else "-")
            if any(v in verb for v in ("reduce", "cut", "trim", "lower")) and not ch.startswith("-"):
                sign = "-"
            _add("Adj. EPS", fy, f"{sign}{ch}".replace("++", "+").replace("--", "-"))

    # Berenberg: "We trim FY26/27/28 revenues and EBIT by c1%, and EPS by 1.5-2.7%"
    m = re.search(
        r"(?:trim|cut|lower|raise|increase)\s+FY\s*(\d{2})/(\d{2})/(\d{2})\s+"
        r"(?:revenues?\s+and\s+EBIT\s+by\s+c?([\d\.]+)\s*%[^.]{0,40})?"
        r"(?:EPS\s+by\s+([\d\.]+)\s*[-–]\s*([\d\.]+)\s*%|EPS\s+by\s+c?([\d\.]+)\s*%)",
        norm,
        re.I,
    )
    if m:
        lo = m.group(5) or m.group(7)
        hi = m.group(6) or m.group(7)
        if lo:
            ch = f"-{lo}%" if "trim" in m.group(0).lower() or "cut" in m.group(0).lower() or "lower" in m.group(0).lower() else f"+{lo}%"
            if hi and hi != lo:
                ch = f"-{lo}–{hi}%" if ch.startswith("-") else f"+{lo}–{hi}%"
            _add("EPS", m.group(1), ch, m.group(2), ch)

    # Prefer EPS/CEPS row when present in ABG block (last matching financial row wins if we search EPS first)
    m = re.search(
        r"Estimate changes\s*\(%\)\s*20(\d{2})e\s+20(\d{2})e\s+20(\d{2})e\s+"
        r".{0,260}?\b(EPS|CEPS)\s+([+\-]?\d+\.?\d*)\s+([+\-]?\d+\.?\d*)\s+([+\-]?\d+\.?\d*)",
        norm,
        re.I,
    )
    if not m:
        m = re.search(
            r"Estimate changes\s*\(%\)\s*20(\d{2})e\s+20(\d{2})e\s+20(\d{2})e\s+"
            r".{0,260}?\b(EBIT|Sales|NOI)\s+([+\-]?\d+\.?\d*)\s+([+\-]?\d+\.?\d*)\s+([+\-]?\d+\.?\d*)",
            norm,
            re.I,
        )
    if m:
        metric = m.group(4)
        for i in range(3):
            _add(metric, m.group(i + 1), f"{m.group(i + 5)}%")

    # Nordea: "Estimate Changes … 2026E 2027E 2028E … EPS (adj. SEK) -2% -2% -3%"
    m = re.search(
        r"Estimate Changes.{0,80}?20(\d{2})E\s+20(\d{2})E\s+20(\d{2})E\s+"
        r".{0,400}?\bEPS\s*\(adj[^)]*\)\s+([+\-]?\d+\s*%|n\.?a\.?)\s+([+\-]?\d+\s*%|n\.?a\.?)\s+([+\-]?\d+\s*%|n\.?a\.?)",
        norm,
        re.I,
    )
    if m:
        for i in range(3):
            ch = m.group(i + 4).replace(" ", "")
            if not re.search(r"n\.?a", ch, re.I):
                _add("EPS adj", m.group(i + 1), ch if ch.endswith("%") else f"{ch}%")

    # BNP arrows style near EPS 26e / 27e
    m = re.search(r"TARGET PRICE\s+EPS 26e\s+EPS 27e\s+.*?([+\-]?\d+%)\s+([+\-]?\d+%)\s+([+\-]?\d+%)", norm, re.I)
    if m:
        _add("Target price", "", m.group(1))
        _add("EPS", "26", m.group(2), "27", m.group(3))

    # trim 2026/27 EPS by 2%/3%
    m = re.search(r"trim\s+20(\d{2})/(\d{2})\s+EPS\s+by\s+([+\-]?\d+\.?\d*%?)/([+\-]?\d+\.?\d*%?)", norm, re.I)
    if m:
        _add("EPS", m.group(1), f"-{m.group(3).lstrip('+-')}", m.group(2), f"-{m.group(4).lstrip('+-')}")

    # PT / TP from → to (Berenberg, Danske, BofA PO)
    m = re.search(
        r"(?:reduce|raise|cut|trim|lower|increase|lift)?\s*(?:our\s+)?"
        r"(?:price target|target price|12M(?:\s+target)?(?:\s+price)?|TP|PO)\s+"
        r"(?:from\s+)?([A-Z]{3}|€|£|\$|p)?\s*([\d',\./]+)\s*(?:p|€|£)?\s+"
        r"(?:to\s+)?([A-Z]{3}|€|£|\$|p)?\s*([\d',\./]+)\s*(?:p|€|£)?",
        norm,
        re.I,
    )
    # Prefer clearer patterns:
    for pat, g_from, g_to in [
        (
            r"(?:reduce|raise|cut|trim|lower|increase)\s+our\s+price target\s+from\s+(\d+[\d,.]*)\s*p?\s+to\s+(\d+[\d,.]*)\s*p?",
            1,
            2,
        ),
        (
            r"(?:raise|cut|trim|lower|increase)\s+our\s+(?:12M\s+)?(?:target price|TP|PO)\s+to\s+([A-Z]{3}|€|£|\$)?\s*([\d',\./]+)\s*\(([A-Z]{3}|€|£|\$)?\s*([\d',\./]+)\)",
            4,
            2,
        ),
        (
            r"(?:trim|cut|lower)\s+our\s+PO\s+to\s+(€|£|\$|[A-Z]{3})?\s*([\d',\./]+)\s*\((?:from\s+)?(€|£|\$|[A-Z]{3})?\s*([\d',\./]+)\)",
            4,
            2,
        ),
        (
            r"(?:lower|reduce)\s+our\s+(?:multiples-based\s+)?target price\s+to\s+([A-Z]{3})?\s*([\d',\./]+)\s*\((\d+[\d,.]*)\)",
            3,
            2,
        ),
    ]:
        m = re.search(pat, norm, re.I)
        if m:
            _add(
                "Target price",
                "",
                "",
                from_value=m.group(g_from),
                to_value=m.group(g_to),
            )
            break

    # BofA / prose PO moves: "raise our PO from $175 to $205" / "PO goes up to 5,730GBp (from 4,800)"
    # / "Our PO also declines to GBp500/... (from GBp540/...)"
    for pat, gf, gt in [
        (
            r"(?:raise|cut|trim|lower|increase)\s+our\s+PO\s+from\s+(€|£|\$|[A-Z]{3})?\s*([\d',\./]+)\s+to\s+(€|£|\$|[A-Z]{3})?\s*([\d',\./]+)",
            2,
            4,
        ),
        (
            r"PO\s+(?:goes\s+up|also\s+declines|declines|rises)\s+to\s+(?:GBp|GBP|EUR|USD|\$|€|£)?\s*([\d',\.]+).{0,60}?\(from\s+(?:GBp|GBP|EUR|USD|\$|€|£)?\s*([\d',\.]+)",
            2,
            1,
        ),
        (
            r"(?:increase|raise|lift)\s+our\s+(?:value[-\s]creation-based\s+)?(?:target price|TP)\s+to\s+"
            r"(?:[A-Z]{3}|€|£|\$|GBp)?\s*([\d',\./]+)\s*(?:p(?:/sh)?|€)?\s*"
            r"(?:\((?:vs\.?|from)\s+(?:[A-Z]{3}|€|£|\$|GBp)?\s*([\d',\./]+)|from\s+(?:[A-Z]{3}|€|£|\$|GBp)?\s*([\d',\./]+))",
            2,
            1,
        ),
        (
            r"(?:increase|raise)\s+our\s+(?:target price|TP)\s+from\s+(?:[A-Z]{3}|€|£|\$)?\s*([\d',\./]+)\s+to\s+(?:[A-Z]{3}|€|£|\$)?\s*([\d',\./]+)",
            1,
            2,
        ),
        (
            r"(?:cut|reduce|lower)\s+our\s+(?:price target|target price|TP)\s+from\s+(€|£|\$|[A-Z]{3})?\s*([\d',\./]+)\s+to\s+(€|£|\$|[A-Z]{3})?\s*([\d',\./]+)",
            2,
            4,
        ),
        (
            r"raise\s+our\s+Target Price\s+to\s+(€|£|\$|[A-Z]{3})?\s*([\d',\./]+)",
            2,
            2,
        ),
    ]:
        m = re.search(pat, norm, re.I)
        if m:
            fv = m.group(gf) if gf else None
            # group 2 vs 3 alternate for "from X" capture
            if gt == 1 and m.lastindex >= 3 and m.group(3):
                fv = m.group(2) or m.group(3)
                tv = m.group(1)
            else:
                tv = m.group(gt)
                if gf == 2 and m.lastindex >= 3 and not fv:
                    fv = m.group(3)
            if tv:
                _add("Target price", "", "", from_value=str(fv or ""), to_value=str(tv))
            break

    # Stifel / multi: "cut our FY 26-28E EBITDA/EPS/FCF estimates by 8%/1%/46%"
    m = re.search(
        r"cut\s+our\s+FY\s*(\d{2})-(\d{2})E?\s+([\w/]+)\s+estimates\s+by\s+"
        r"([\d\.]+)%/([\d\.]+)%/([\d\.]+)%",
        norm,
        re.I,
    )
    if m:
        metrics = m.group(3).split("/")
        chgs = [m.group(4), m.group(5), m.group(6)]
        for metric, ch in zip(metrics, chgs):
            _add(metric, m.group(1), f"-{ch}%", m.group(2), f"-{ch}%")

    # Intermonte: EPS New Adj / EPS Old Adj
    m = re.search(
        r"EPS New Adj\s*\([^)]*\)\s+([\d\.\-]+)\s+([\d\.\-]+)\s+([\d\.\-]+)\s+([\d\.\-]+)\s+([\d\.\-]+)\s+"
        r"EPS Old Adj\s*\([^)]*\)\s+([\d\.\-]+)\s+([\d\.\-]+)\s+([\d\.\-]+)\s+([\d\.\-]+)\s+([\d\.\-]+)",
        norm,
        re.I,
    )
    if m:
        for i, fy in enumerate(["26", "27", "28"]):
            try:
                new, old = float(m.group(3 + i)), float(m.group(8 + i))
            except ValueError:
                continue
            if old:
                _add("EPS", fy, f"{(new / old - 1) * 100:+.1f}%", from_value=str(old), to_value=str(new))

    # "raise our estimates and target price (+1%)" / "increase EBITDA estimates by ~2%"
    m = re.search(r"raise\s+our\s+estimates\s+and\s+target price\s*\(\+?([\d\.]+)\s*%\)", norm, re.I)
    if m:
        _add("Estimates/TP", "", f"+{m.group(1)}%")
    m = re.search(
        r"increase\s+(\w+)\s+estimates\s+by\s+~?([\d\.]+)\s*%\s*(?:in\s+)?(?:20)?(\d{2})e?",
        norm,
        re.I,
    )
    if m:
        _add(m.group(1), m.group(3), f"+{m.group(2)}%")

    # "raise EPS c3-4% for FY27" / "EPS estimates raised 4%"
    m = re.search(r"raise\s+EPS\s+c?([\d\.]+)(?:\s*[-–]\s*([\d\.]+))?\s*%\s*(?:for\s+)?FY\s*(\d{2})", norm, re.I)
    if m:
        ch = f"+{m.group(1)}%" if not m.group(2) else f"+{m.group(1)}–{m.group(2)}%"
        _add("EPS", m.group(3), ch)
    m = re.search(r"EPS estimates raised\s+(\d+)\s*%", norm, re.I)
    if m:
        _add("EPS", "", f"+{m.group(1)}%")

    # Oddo: "Target price raised"
    if re.search(r"Target price raised|TP raised", norm, re.I):
        m = re.search(
            r"Target Price\s*:\s*([A-Z]{3})?\s*([\d',\./]+).{0,40}?(?:from|was|prev(?:ious)?)\s*([A-Z]{3})?\s*([\d',\./]+)",
            norm,
            re.I,
        )
        if m:
            _add("Target price", "", "", from_value=m.group(4), to_value=m.group(2))
        elif not any(r.get("metric") == "Target price" for r in rows):
            _add("Target price", "", "raised")

    # Danske / prose: "We increase our adj. EBIT estimates 2% 26E"
    m = re.search(
        r"(?:increase|reduce|raise|cut|lower)\s+our\s+(?:adj\.?\s+)?(EBIT|EPS|Sales|revenue)s?\s+estimates?\s+"
        r"([+\-]?\d+\.?\d*)\s*%\s*(?:for\s+)?(?:20)?(\d{2})E?",
        norm,
        re.I,
    )
    if m:
        sign = "+" if any(v in m.group(0).lower() for v in ("increase", "raise")) else "-"
        ch = m.group(2)
        if not ch.startswith(("+", "-")):
            ch = sign + ch
        _add(m.group(1), m.group(3), f"{ch}%")

    # GS: "we lower … FY26/27/28e adjusted EPS by 1-6%"
    m = re.search(
        r"(?:lower|raise|cut|trim|increase)\s+(?:of\s+)?FY\s*(\d{2})/(\d{2})/(\d{2})e?\s+"
        r"(?:adjusted\s+)?EPS\s+by\s+([\d\.]+)\s*[-–]\s*([\d\.]+)\s*%",
        norm,
        re.I,
    )
    if m:
        sign = "-" if any(v in m.group(0).lower() for v in ("lower", "cut", "trim")) else "+"
        _add("Adj. EPS", m.group(1), f"{sign}{m.group(4)}–{m.group(5)}%", m.group(2), f"{sign}{m.group(4)}–{m.group(5)}%")

    # DNB-style / MS What's Changed From/To Price Target
    m = re.search(
        r"(?:Price [Tt]arget|Target [Pp]rice)\s+(?:[A-Za-z]{2,3}\s*)?([\d,\.]+)\s+(?:[A-Za-z]{2,3}\s*)?([\d,\.]+)",
        norm,
    )
    if m and re.search(r"what.?s changed|updated components", head, re.I):
        _add("Target price", "", "", from_value=m.group(1), to_value=m.group(2))

    # Prior EPS vs EPS rows (MS) — either order
    m = re.search(
        r"Prior EPS\s*\([^)]*\)\s*\*{0,2}\s*([\-\.]+|\d[\d\.]*)\s+([\d\.\-]+)\s+([\d\.\-]+)\s+([\d\.\-]+)"
        r".{0,80}?EPS\s*\([^)]*\)\s*\S*\s+([\d\.\-]+)\s+([\d\.\-]+)\s+([\d\.\-]+)\s+([\d\.\-]+)",
        norm,
        re.I,
    )
    if not m:
        m2 = re.search(
            r"EPS\s*\([^)]*\)\s*\*{0,2}\s*([\d\.\-]+)\s+([\d\.\-]+)\s+([\d\.\-]+)\s+([\d\.\-]+)\s+"
            r"Prior EPS\s*\([^)]*\)\s*\S+\s+([\d\.\-\.]+)\s+([\d\.\-]+)\s+([\d\.\-]+)",
            norm,
            re.I,
        )
        if m2:
            for i, fy in enumerate(["26", "27", "28"]):
                try:
                    old, new = float(m2.group(5 + i)), float(m2.group(2 + i))
                except ValueError:
                    continue
                if old:
                    _add("EPS", fy, f"{(new / old - 1) * 100:+.1f}%", from_value=str(old), to_value=str(new))
    else:
        for i, fy in enumerate(["26", "27", "28"]):
            try:
                old, new = float(m.group(2 + i)), float(m.group(6 + i))
            except (TypeError, ValueError):
                continue
            if old:
                _add("EPS", fy, f"{(new / old - 1) * 100:+.1f}%", from_value=str(old), to_value=str(new))

    # ZKB: EPS old / EPS new → revisions
    m = re.search(
        rf"EPS\s+old\s+({_EPS_NUM})\s+({_EPS_NUM})(?:\s+({_EPS_NUM}))?"
        rf".{{0,60}}?EPS\s+new\s+({_EPS_NUM})\s+({_EPS_NUM})(?:\s+({_EPS_NUM}))?",
        norm,
        re.I,
    )
    if m:
        olds = [_eps_float(g) for g in m.groups()[:3] if g]
        news = [_eps_float(g) for g in m.groups()[3:] if g]
        for i, (old, new) in enumerate(zip(olds, news)):
            if old:
                _add(
                    "EPS",
                    str(25 + i),
                    f"{(new / old - 1) * 100:+.1f}%",
                    from_value=str(old),
                    to_value=str(new),
                )

    # Berenberg estimate changes table often has ∆ %
    if re.search(r"Estimates changes|Changes made in this note", head, re.I):
        for m in re.finditer(r"(20\d{2})E?\s+.*?([+\-]?\d+\.?\d*)\s*%", norm[:2500], re.I):
            _add("Estimate", m.group(1)[-2:], f"{m.group(2)}%")
            if len(rows) >= 10:
                break

    # dedupe by metric+fy1
    seen = set()
    uniq = []
    for r in rows:
        key = (r.get("metric"), r.get("fy1"), r.get("change_fy1"), r.get("from_value"), r.get("to_value"))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(r)
    return uniq[:12]


def parse_eps_numbers(text: str) -> tuple[list[float], list[float]]:
    """Pull broker and consensus EPS levels from common sell-side table layouts."""
    head = text[:30000]
    norm = re.sub(r"\s+", " ", head)
    broker: list[float] = []
    consensus: list[float] = []
    n = _EPS_NUM

    def _take(*groups: str | None, prefer_forward: bool = True) -> list[float]:
        vals = [_eps_float(g) for g in groups if g]
        if prefer_forward and len(vals) >= 4:
            # BNP-style hist + 3 forward: drop first (often actual)
            return vals[1:4]
        return vals[:3] if len(vals) >= 3 else vals

    def _take_series(vals: list[float]) -> list[float]:
        if len(vals) >= 6:
            return vals[-3:]
        if len(vals) >= 4:
            return vals[1:4]
        return vals[:3]

    # BNP: "EPS, Adjusted (EUR) 1.10 1.26 1.47 1.55"
    m = re.search(
        rf"EPS,\s*Adjusted\s*\([^)]*\)\s+({n})\s+({n})\s+({n})\s+({n})",
        norm,
        re.I,
    )
    if m:
        broker = _take(*m.groups())

    # UBS: "EPS (UBS, diluted) (€) 1.72 2.11 …" — any short ccy in 2nd paren
    if not broker:
        m = re.search(
            rf"\bEPS\s*\([^)]{{1,40}}\)\s*\([^)]{{1,12}}\)\s+((?:{n}\s+){{2,12}}{n})",
            norm,
            re.I,
        )
        if m:
            nums = [_eps_float(x) for x in re.findall(n, m.group(1))]
            broker = _take_series(nums)

    # MS / generic: "EPS (£)** 1.81 2.02 2.25 2.42" or "EPS (EUR) a b c"
    if not broker:
        m = re.search(
            rf"\bEPS\s*\([^)]*\)\s*\*{{0,2}}\s+({n})\s+({n})\s+({n})(?:\s+({n}))?",
            norm,
            re.I,
        )
        if m:
            broker = _take(*m.groups(), prefer_forward=False)
            if len(broker) >= 4:
                broker = broker[1:4]

    # ZKB / Stifel / Kepler / Pareto: "EPS new -0.23 0.55 0.70", "EPS adj (p) 47.5 42.2"
    if not broker:
        m = re.search(
            rf"\bEPS\s+(?:new|old|adj(?:usted)?|reported|adj\.)"
            rf"(?:\s+and\s+fully\s+diluted)?"
            rf"(?:\s*\([^)]*\))?\s+({n})\s+({n})(?:\s+({n}))?",
            norm,
            re.I,
        )
        if m:
            broker = _take(*m.groups(), prefer_forward=False)

    if not broker:
        m = re.search(
            rf"\bEPS\s*\((?:SEK|EUR|USD|GBP|CHF|NOK|DKK|US\$|\$|c|p|cts?)\)\s+((?:{n}\s+){{1,8}}{n})",
            norm,
            re.I,
        )
        if m:
            nums = [_eps_float(x) for x in re.findall(n, m.group(1))]
            broker = _take_series(nums) if len(nums) >= 4 else nums[:3]

    # Jefferies tables: "Recurring EPS 2.78 3.49 …" / "Diluted EPS 5.76 6.96 …"
    if not broker:
        m = re.search(
            rf"\b(?:Recurring|Diluted|Basic)\s+EPS\s+((?:{n}\s+){{2,10}}{n})",
            norm,
            re.I,
        )
        if m:
            nums = [_eps_float(x) for x in re.findall(n, m.group(1))]
            broker = _take_series(nums) if len(nums) >= 3 else nums

    # Jefferies / narrative: "adj. EPS ... 72.8p"
    if not broker:
        m = re.search(rf"adj\.?\s*EPS[^\d(]{{0,40}}({n})\s*p?\b", norm, re.I)
        if m:
            broker = [_eps_float(m.group(1))]

    # Stifel cover: "FY26E EPS $28.40" / "FY27E EPS $38.67"
    if not broker:
        fy_hits = re.findall(rf"FY(\d{{2}})E?\s*EPS[^\d$£€]{{0,12}}[\$£€]?\s*({n})", norm, re.I)
        if fy_hits:
            broker = [_eps_float(v) for _, v in fy_hits[:3]]

    # Danske / prose: "EPS of USD3.31" / "EPS of USD8.72"
    if not broker:
        m = re.search(rf"\bEPS(?:\s+adj\.?)?\s+of\s+(?:USD|EUR|GBP|CHF|SEK)?\s*({n})", norm, re.I)
        if m:
            broker = [_eps_float(m.group(1))]

    # Bare multi-year "EPS 1.2 1.4 1.6" — avoid revision % rows ("EPS -4% +1%")
    if not broker:
        m = re.search(rf"\bEPS\s+({n})\s+({n})\s+({n})(?!\s*%)", norm, re.I)
        if m and not re.search(r"\bEPS\s+[+\-]?\d+\.?\d*\s*%", m.group(0)):
            # skip if any token looks like a lone percent change context
            broker = _take(*m.groups(), prefer_forward=False)

    # Consensus levels
    m = re.search(
        rf"(?:Consensus EPS|EPS Consensus)(?:\s*\([^)]*\))?\s+({n})\s+({n})(?:\s+({n}))?",
        norm,
        re.I,
    )
    if m:
        consensus = _take(*m.groups(), prefer_forward=False)

    if not consensus:
        m = re.search(
            rf"EPS\s*-\s*Bloomberg\s*\([^)]*\)\s+({n})\s+({n})\s+({n})(?:\s+({n}))?",
            norm,
            re.I,
        )
        if m:
            consensus = _take(*m.groups())

    return broker, consensus


def extract(pages: list[PageText]) -> ExtractedReport:
    head = pages[0].text if pages else ""
    full = "\n".join(p.text for p in pages[:8])
    text = head + "\n" + full

    company = parse_company(head) or parse_company(text[:3000])
    target_price = parse_target_price(head) or parse_target_price(text)
    rating = parse_rating(head) or parse_rating(text)
    revisions = parse_revision_mentions(text)
    broker_eps, consensus_eps = parse_eps_numbers(text)

    passages = find_passages(
        pages,
        [
            ("why_now", r"(?:Our Take|Reason for change|Key takeaways|We expect|We reiterate|In our view).{40,500}"),
            ("drivers", r"(?:This is driven|Consequently|We have (?:reduced|increased|trimmed)|estimate).{30,400}"),
            ("valuation", r"(?:Valuation|target price|Price target|trades at).{30,350}"),
            ("investment_case", r"(?:Investment case|We like|reiterate (?:our )?(?:Buy|Hold|OP|OW)).{20,350}"),
        ],
    )
    if not passages and pages:
        from extractors.base import Passage

        para = re.sub(r"\s+", " ", pages[0].text)[:400]
        if len(para) > 80:
            passages = [Passage(page=1, text=para, label="why_now")]

    rating_change = ""
    if rating:
        if re.search(r"no change|reiterate|retain", head, re.I):
            rating_change = f"Reiterate {rating}"
        elif re.search(r"downgrade|upgrade|dgd|ugd", head, re.I):
            m = re.search(r"(downgrade|upgrade)\s+(?:to\s+)?(\w+)\s+from\s+(\w+)", head, re.I)
            rating_change = f"{m.group(1)} to {m.group(2)} from {m.group(3)}" if m else f"Rating: {rating}"
        else:
            rating_change = f"Rating: {rating}"

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
        extractor_used="generic_fallback",
        low_confidence=True,
    )
    result.extraction_status = compute_extraction_status(result)
    return result
