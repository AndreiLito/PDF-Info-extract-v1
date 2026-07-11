# /find-rpt — Sell-Side Research Retrieval Skill

**Repo:** https://github.com/AndreiLito/PDF-Info-extract-v1

Locate a broker research PDF by **ticker + date + broker** and produce a structured, citation-backed brief (revisions, why/context, estimate picture, inline PDF citations, analyst email draft when rationale is unclear — never auto-send).

## Quick start

```bash
git clone https://github.com/AndreiLito/PDF-Info-extract-v1.git
cd PDF-Info-extract-v1
pip install -r requirements.txt
```

Point at your local corpus (PDFs are **not** in this repo):

```bash
# Preferred — keep machine paths out of committed files
export FIND_RPT_CORPUS=/path/to/corpus          # macOS/Linux
set FIND_RPT_CORPUS=C:\path\to\corpus           # Windows
```

Or create gitignored `config/local.yaml`:

```yaml
corpus_path: "/path/to/corpus"
```

Empty / unset → `./corpus` under the repo root.

```bash
python scripts/build_index.py --force
python scripts/find_rpt.py "SHA0 GY" 20260622 "Kepler Cheuvreux"
```

## What to give Claude (or reviewers)

Upload / clone from GitHub — **relative repo paths only**, no personal drives:

| Include | Path |
|---------|------|
| Skill | `.claude/skills/find-rpt/SKILL.md` |
| Engine | `scripts/` |
| Config defaults | `config/default.yaml` |
| Deps | `requirements.txt` |
| README (optional) | `README.md` |
| Examples (optional) | `examples/` |

**Do not include:** corpus PDFs, `.find-rpt/` cache, `config/local.yaml`.

Step-by-step: [CLAUDE_TESTING.md](CLAUDE_TESTING.md).

## Agent usage

| Environment | Skill path | Invoke |
|-------------|------------|--------|
| **Cursor** | `.cursor/skills/find-rpt/SKILL.md` | `/find-rpt SHA0 GY 20260622 Kepler Cheuvreux` |
| **Claude** | `.claude/skills/find-rpt/SKILL.md` | same |

Both skills are twins. The agent runs `python scripts/find_rpt.py …` from the **repo root**, then writes the brief from JSON.

## Command

```
/find-rpt {ticker} {date} {broker}
```

| Parameter | Example | Notes |
|-----------|---------|-------|
| ticker | `SHA0 GY`, `BP/ LN` | Bloomberg format; matched in PDF content |
| date | `20260622` or `22 Jun 2026` | Must match filename date |
| broker | `Kepler Cheuvreux` | Fuzzy-matched to filename |

## Extraction quality (N = 172 corpus PDFs)

Metrics are from `python scripts/audit_full_corpus.py`.

**Conditional** = success when the field is actually present in the note (we do not invent missing fields).

| Field | Conditional | Raw | Notes |
|-------|-------------|-----|-------|
| Company | — | **100%** | Always identified |
| Key passages / citations | — | **100%** | |
| Broker EPS | **100%** (140/140) | 82.6% | When EPS levels exist |
| Analyst email | **100%** (153/153) | 89.0% | When `@` present |
| Consensus EPS | **100%** (16/16) | 9.9% | Rare; only when levels stated |
| Target price | **98.3%** (114/116) | 83.7% | |
| Rating | **95.5%** (128/134) | 81.4% | |
| Revisions | **94.5%** (52/55) | 37.2% | Many notes have no revision table |

**Status:** full extraction on **172/172 (100%)** notes.

```bash
python scripts/audit_full_corpus.py
```

## Architecture

```
PDF-Info-extract-v1/   (or find-rpt/)
├── .cursor/skills/find-rpt/SKILL.md   # Cursor skill
├── .claude/skills/find-rpt/SKILL.md   # Claude skill
├── config/
│   ├── default.yaml                   # Shared defaults (no personal paths)
│   └── local.yaml                     # Gitignored machine corpus path
├── scripts/
│   ├── find_rpt.py                    # Main CLI → JSON for the agent
│   ├── build_index.py / corpus.py     # Filename index + ticker lookup
│   ├── cite.py                        # Highlighted PDF citations
│   ├── audit_full_corpus.py           # Full-corpus metric report
│   └── extractors/                    # Broker-pluggable parsers
│       ├── registry.py
│       ├── validate.py
│       ├── generic.py / nordic_eu.py
│       └── kepler_cheuvreux.py, ubs.py, …
├── examples/                          # Sample briefs + transcript
├── CLAUDE_TESTING.md                  # Claude upload / test guide
└── requirements.txt
```

See also `scripts/README.md`, `scripts/extractors/README.md`, `config/README.md`.

**How it works**

1. Index filenames `{YYYYMMDD}_{Broker}_{hash}.pdf`; tickers come from PDF text.
2. `registry.resolve_extractor(broker)` picks a dedicated Python module (or `nordic_eu` / `generic`). Extraction is **code**, not per-broker brief templates.
3. Parsers read cover pages for company / TP / rating; deeper pages for EPS / revisions when needed.
4. `validate_and_backfill` retries missing fields only when PDF signals say they exist.
5. Agent fills **one** shared brief template from JSON; never invents numbers; email draft only when `ambiguity.should_offer_email_draft` is true.

## Output sections (agent brief)

1. Title + one-line summary  
2. What changed (revision table)  
3. Why it changed, and why now (plain English, inline PDF links)  
4. Estimate picture (broker vs consensus when available)  
5. Ambiguity escalation (draft analyst email — never auto-send)  
6. Inline source citations with highlighted PDF snippets  

## Citation links

- URIs returned by the CLI (`pdf_uri`, `citations[].markdown`) — use those as-is  
- Highlighted copies under `.find-rpt/highlights/` when text can be located (generated locally)

## Examples / submission artifacts

| File | Use |
|------|-----|
| [`examples/cursor-agent-transcript.md`](examples/cursor-agent-transcript.md) | Development transcript |
| [`examples/live-brief-sha0.md`](examples/live-brief-sha0.md) | Sample agent brief |
| [`examples/live-cli-sha0.json`](examples/live-cli-sha0.json) | Live CLI JSON |
| [`examples/example-runs.md`](examples/example-runs.md) | More test queries |

## Confidentiality

Research PDFs are confidential — kept local (`FIND_RPT_CORPUS` / `config/local.yaml`). This repo contains tooling and skills only (no corpus).
