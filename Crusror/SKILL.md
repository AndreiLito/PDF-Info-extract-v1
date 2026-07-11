---
name: find-rpt
description: Locates sell-side equity research PDFs by Bloomberg ticker, date, and broker, then produces structured research briefs with estimate revisions, plain-English rationale, inline PDF citations, and analyst email drafts when rationale is unclear. Use when the user invokes /find-rpt, asks to find a research report, or wants a sell-side brief from the corpus.
---

# /find-rpt - Research Retrieval Skill

## Source

- **GitHub:** https://github.com/AndreiLito/PDF-Info-extract-v1
- **This skill:** `.claude/skills/find-rpt/SKILL.md` (Claude) or `.cursor/skills/find-rpt/SKILL.md` (Cursor) - same content
- **Engine:** `scripts/find_rpt.py` + broker-pluggable `scripts/extractors/`
- **Config:** `config/default.yaml` + env `FIND_RPT_CORPUS` (or gitignored `config/local.yaml`)
- **Deps:** `requirements.txt` (`pymupdf`, `pyyaml`)

PDFs are **not** in the repo. Never hard-code personal drive paths in briefs or replies. Use URIs returned by the CLI.

**Architecture note:** extraction is **Python per broker** (registry -> dedicated / `nordic_eu` / `generic` + `validate_and_backfill`). There is **one** brief template (this skill) - not one prose template per broker.

## Setup

From the **repo root** (clone of GitHub, or the project folder available to the agent):

```bash
pip install -r requirements.txt

# corpus (machine-only - do not commit personal paths into this skill)
export FIND_RPT_CORPUS=/path/to/corpus          # macOS/Linux
set FIND_RPT_CORPUS=C:\path\to\corpus           # Windows

python scripts/build_index.py --force
```

If the clone uses `Scripts/` (capital S) on Windows, run `python Scripts/find_rpt.py` / `python Scripts/build_index.py` instead - same engine.

Empty `corpus_path` -> `./corpus` under the repo root.

## Command

```
/find-rpt {ticker} {date} {broker}
```

Examples:
- `/find-rpt SHA0 GY 20260622 Kepler Cheuvreux`
- `/find-rpt MATAS DC 20260511 DNB Carnegie`
- `/find-rpt NO/YAR NO 20260511 ABG Sundal Collier`
- `/find-rpt NDA GY 20260511 UBS`

## Workflow

1. Parse ticker, date, broker from the user message.
2. From the **repo root**, run:
   ```bash
   python scripts/find_rpt.py "{ticker}" "{date}" "{broker}"
   ```
3. Read the JSON. If top-level `error` is present, report it (and any suggestions) and stop.
4. Check `extracted.extraction_status`:
   - `full` - use numbers and passages as-is
   - `partial` / `failed` - say extraction is incomplete; open the PDF; **do not invent numbers**; **do not** offer analyst email just because a field is empty
5. Compose the brief below. Verify every number against JSON/PDF.
6. Cite inline with each citation's `markdown` / URI from `citations` (CLI links only).
7. Email escalation **only** when `ambiguity.should_offer_email_draft` is true. Never send.

## What the CLI does (so you trust the JSON)

1. Lookup `{YYYYMMDD}_{Broker}_{hash}.pdf` via `.find-rpt/index.json` (ticker from PDF text, not filename).
2. `registry.resolve_extractor(broker)` -> broker module (or nordic/generic).
3. Parse cover for company / TP / rating; deeper pages for EPS / revisions when needed.
4. `validate_and_backfill` retries a field **only** when the PDF signals that field exists - never invents missing fields.
5. Builds citations / optional highlights under `.find-rpt/highlights/` (local cache - not in git).

## JSON map

| JSON path | Use for |
|-----------|---------|
| `header.*` | Ticker, broker, date, company, analyst, `filename`, `pdf_uri` |
| `extracted.extraction_status` | `full` / `partial` / `failed` |
| `extracted.extractor_used` | Which parser ran |
| `extracted.revisions` | "What changed" table (omit section if empty) |
| `extracted.estimate_picture` | Broker vs consensus / rows with `vs_consensus` |
| `extracted.rating_change` / `target_price` | Takeaway + table |
| `extracted.key_passages` | Why / context wording |
| `citations[].markdown` | Inline PDF links |
| `ambiguity.should_offer_email_draft` | Gate for email draft |
| `header.analyst_email` | Email `To:` (else `[TODO: address]`) |

## Output template (under-a-minute read)

```markdown
# {TICKER} - {Broker} - {Date}
{One-line takeaway}

## What changed

| Metric | FY26E | FY27E |
|--------|-------|-------|
| ... | ... | ... |

{One line: vs consensus / old vs new if available; else omit}

## Why it changed, and why now

{<=2 short paragraphs, plain English. Inline [citations].}

{Context: preview/review/rating change/etc. Management contact if stated; else "not stated".}

---
**Source:** [{filename}]({pdf_uri}) · **Analyst:** {analyst} · **Company:** {company}
```

### Writing rules

- Translate house KPIs/shorthand into everyday English on first use.
- If report type, management contact, or rationale is not given, say so explicitly.
- Fold estimate picture into "What changed" when consensus exists - no empty consensus section.
- **Never fabricate** revisions, EPS, TP, rating, or consensus. Empty = field absent from the note or extractor gap - not a guess.
- Prefer conditional quality mindset: many notes legitimately lack revisions/consensus.

## Email escalation (draft only)

Only when `should_offer_email_draft` is true (revisions/rating change present **and** rationale passages missing - **not** for extractor gaps):

```markdown
## Analyst follow-up (draft - not sent)

**To:** {analyst_email or [TODO: address]}
**Subject:** Clarification on estimate revisions - {company} ({ticker})

Hi {first name},

We read your {date} note on {company} and noted estimate revisions ...
{2-4 specific questions}

Best regards,
[Your name]
```

## Extraction quality (corpus audit, N = 172)

Conditional = hit rate **when the field is present** in the PDF.

| Field | Conditional | Raw |
|-------|-------------|-----|
| Company | - | 100% |
| Passages / citations | - | 100% |
| Broker EPS | 100% (140/140) | 82.6% |
| Analyst email | 100% (153/153) | 89.0% |
| Consensus EPS | 100% (16/16) | 9.9% (rarely present) |
| Target price | 98.3% (114/116) | 83.7% |
| Rating | 95.5% (128/134) | 81.4% |
| Revisions | 94.5% (52/55) | 37.2% (often absent) |

Status: **full on 172/172**. Refresh: `python scripts/audit_full_corpus.py`.

## Worked examples

| Query | What to expect |
|-------|----------------|
| `SHA0 GY` / Kepler / `20260622` | Rating change + revision table + EPS vs consensus |
| `MATAS DC` / DNB Carnegie / `20260511` | Nordic cover layout |
| `NO/YAR NO` / ABG / `20260511` | Estimate-changes (%) table |
| `NDA GY` / UBS / `20260511` | UBS Fast Take / Global Research layout |
| Meeting / flash notes (some GS, ZKB) | May lack TP or revisions - say "not stated", do not invent |

## Ticker notes

- Ticker is in PDF content, not the filename.
- `SHA0 GY` matches `SHA0 GR` (Germany exchange codes).
- Slash tickers like `BP/ LN` are supported.

## Quality checklist

- [ ] Header + one-line takeaway
- [ ] Revision table only if revisions exist in JSON
- [ ] Why section <=2 short paragraphs, plain English, with citations
- [ ] No fabricated numbers / no invented drive paths
- [ ] Email draft only if `should_offer_email_draft`
