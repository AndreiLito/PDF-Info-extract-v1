# config/

| File | Purpose |
|------|---------|
| `default.yaml` | Shared defaults committed to git (`corpus_path` empty) |
| `local.yaml` | **Gitignored** machine-only overrides (personal corpus path) |

## Corpus path

Keep personal drives out of git and out of the Claude skill.

**Preferred:**

```bash
export FIND_RPT_CORPUS=/path/to/corpus   # macOS/Linux
set FIND_RPT_CORPUS=C:\path\to\corpus    # Windows
```

**Or** create `config/local.yaml` (not committed):

```yaml
corpus_path: "/path/to/corpus"
```

If unset / empty, the code uses `./corpus` under the repo root.

Load order: `default.yaml` → `local.yaml` → env `FIND_RPT_CORPUS` / `FIND_RPT_CACHE` (env wins).

## After extractor changes

```bash
python scripts/audit_full_corpus.py
```

Latest (N=172): company/passages 100%; EPS/email/consensus 100% conditional; TP 98.3%; rating 95.5%; revisions 94.5%.
