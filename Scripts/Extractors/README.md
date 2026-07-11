# extractors/

Broker-specific PDF parsers for `/find-rpt`  
(repo: https://github.com/AndreiLito/PDF-Info-extract).

Extraction is **Python code per broker** (or shared `nordic_eu` / `generic`). There is **one** agent brief template in the skill — not one template file per broker.

## How to add a broker

1. Add `my_broker.py` with `extract(pages) -> ExtractedReport` (usually start from `generic.extract`).
2. Register keywords in `registry.py` → `resolve_extractor` + `extractors` dict.
3. Re-run `python scripts/audit_full_corpus.py` and check conditional rates.

## Shared pieces

- `base.py` — page text, passages, `compute_extraction_status`
- `generic.py` — company / TP / rating / EPS / revision heuristics
- `validate.py` — `_has_substantive_*` signals + `validate_and_backfill`
- `registry.py` — broker name → module

## Quality bar (N = 172)

Prefer **conditional** metrics (field present → extracted). Latest: EPS/email/consensus/company/passages at or near 100% conditional; TP ~98%; rating/revisions ~95%. See `scripts/README.md`.
