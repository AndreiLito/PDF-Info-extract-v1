# Full corpus extraction audit

Total PDFs: **172**

## Status

- full: 172 (100.0%)
- partial: 0 (0.0%)
- failed: 0 (0.0%)

## Raw metric success %

- company: 100.0%
- target_price: 83.7%
- rating_change: 81.4%
- revisions: 37.2%
- broker_eps: 82.6%
- consensus_eps: 9.9%
- key_passages: 100.0%
- analyst_email: 89.0%

## Conditional success (only when field appears present in PDF)

- target_price: 98.3% (114/116 applicable)
- analyst_email: 100.0% (153/153 applicable)
- rating_change: 95.5% (128/134 applicable)
- revisions: 94.5% (52/55 applicable)
- broker_eps: 100.0% (140/140 applicable)
- consensus_eps: 100.0% (16/16 applicable)

## Issue taxonomy (counts)

- `field_absent_consensus`: 155
- `field_absent_revisions`: 105
- `field_absent_eps`: 30
- `field_absent_rating`: 26
- `field_absent_tp`: 25
- `field_absent_email`: 19
- `extractor_gap_rating`: 6
- `extractor_gap_revisions`: 3
- `extractor_gap_tp`: 2
- `field_na_tp`: 1

## Top brokers by extractor gaps (fix these first)

- **Intermonte Securities** (n=2, full=2): gaps={'extractor_gap_tp': 1, 'extractor_gap_rating': 1}
- **Pareto Securities** (n=7, full=7): gaps={'extractor_gap_rating': 2}
- **Alantra Equities Sociedad de Valores, S.A.** (n=7, full=7): gaps={'extractor_gap_rating': 1}
- **Berenberg** (n=7, full=7): gaps={'extractor_gap_revisions': 1}
- **Deutsche Bank Research** (n=7, full=7): gaps={'extractor_gap_revisions': 1}
- **Goldman Sachs** (n=7, full=7): gaps={'extractor_gap_rating': 1}
- **Jefferies** (n=7, full=7): gaps={'extractor_gap_tp': 1}
- **Panmure Liberum** (n=4, full=4): gaps={'extractor_gap_revisions': 1}
- **Oddo BHF Corporates & Markets** (n=7, full=7): gaps={'extractor_gap_rating': 1}

## Recommended fix batch

1. Treat `field_absent_*` / `field_na_tp` as non-failures in scoring.
2. Fix `extractor_gap_*` for top brokers listed above.
3. Special-case multi-name morning/brief notes using query ticker.

Full JSON: `.find-rpt/full_corpus_audit.json`