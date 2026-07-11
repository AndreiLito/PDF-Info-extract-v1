# scripts/

CLI and extraction pipeline for `/find-rpt`.

## Entry points

| Script | Purpose |
|--------|---------|
| `find_rpt.py` | Main CLI: lookup + extract → JSON for the agent brief |
| `build_index.py` | Build `.find-rpt/index.json` from corpus filenames + PDF tickers |
| `corpus.py` | Index / fuzzy broker+ticker+date lookup |
| `extract.py` | Thin wrapper → `extractors.registry.extract_with_registry` |
| `cite.py` | Page URIs + highlighted PDF snippets under `.find-rpt/highlights/` |
| `config.py` | Loads `config/default.yaml` → optional `config/local.yaml` → env `FIND_RPT_CORPUS` |
| `audit_full_corpus.py` | **Authoritative metrics** on all indexed PDFs (N≈172) |
| `audit_corpus.py` | Optional random-50 sample audit (seed 42) |

```bash
# from repo root (https://github.com/AndreiLito/PDF-Info-extract)
# set FIND_RPT_CORPUS=/path/to/corpus  (or config/local.yaml)
python scripts/build_index.py --force
python scripts/find_rpt.py "SHA0 GY" 20260622 "Kepler Cheuvreux"
python scripts/audit_full_corpus.py
```

## extractors/

Broker-pluggable parsers. Routing lives in `extractors/registry.py`.

| Module | Brokers (keywords) |
|--------|-------------------|
| `kepler_cheuvreux.py` | Kepler |
| `dnb_carnegie.py` | DNB, Carnegie |
| `deutsche_bank.py` | Deutsche Bank |
| `bnp_paribas.py` | BNP |
| `berenberg.py` | Berenberg |
| `abg_sundal.py` | ABG |
| `jp_morgan.py` | JP Morgan |
| `morgan_stanley.py` | Morgan Stanley |
| `goldman_sachs.py` | Goldman |
| `citi.py` | Citi |
| `ubs.py` | UBS |
| `bofa.py` | BofA / Bank of America |
| `jefferies.py` | Jefferies |
| `cic.py` | CIC |
| `zurcher.py` | Zürcher / Zurcher |
| `redburn.py` | Redburn / Rothschild |
| `nordic_eu.py` | Nordea, Stifel, Oddo, Danske, Pareto, Panmure, KBC, ING, Degroof, Intermonte, Alantra, Bestinver |
| `generic.py` | Shared heuristics + fallback |
| `validate.py` | Signal detection + backfill when a field is present but missed |
| `base.py` | `ExtractedReport`, page extract (PyMuPDF), status |

**Flow:** PDF pages → dedicated extractor (or nordic/generic) → `validate_and_backfill` → `extraction_status` (`full` / `partial` / `failed`).

**Scan scope:** whole PDF is loaded; cover fields use early pages; EPS/revisions may scan deeper (e.g. mid-note tables). We do **not** invent missing fields.

## Latest quality (N = 172)

From `audit_full_corpus.py` (conditional = when field is present):

| Field | Conditional | Raw |
|-------|-------------|-----|
| Company | — | 100% |
| Passages | — | 100% |
| Broker EPS | 100% | 82.6% |
| Email | 100% | 89.0% |
| Consensus | 100% | 9.9% |
| Target price | 98.3% | 83.7% |
| Rating | 95.5% | 81.4% |
| Revisions | 94.5% | 37.2% |

Status: **full 172/172**. Details: `../.find-rpt/full_corpus_audit.md` (local, gitignored).
