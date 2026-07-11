from __future__ import annotations

import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "config" / "default.yaml"


def load_config() -> dict:
    cfg: dict = {}
    if DEFAULT_CONFIG.exists():
        with DEFAULT_CONFIG.open(encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}

    # Optional machine-local overrides (gitignored) — keep personal paths out of default.yaml
    local_cfg = ROOT / "config" / "local.yaml"
    if local_cfg.exists():
        with local_cfg.open(encoding="utf-8") as f:
            cfg.update(yaml.safe_load(f) or {})

    # Env wins over yaml so machines never need to commit personal paths.
    corpus = os.environ.get("FIND_RPT_CORPUS")
    if corpus is None:
        corpus = cfg.get("corpus_path", "") or ""
    cache = os.environ.get("FIND_RPT_CACHE")
    if cache is None:
        cache = cfg.get("cache_dir", ".find-rpt")

    corpus_path = Path(corpus).expanduser().resolve() if corpus else ROOT / "corpus"
    cache_dir = (ROOT / cache).resolve() if not Path(cache).is_absolute() else Path(cache)

    return {
        "corpus_path": corpus_path,
        "cache_dir": cache_dir,
        "root": ROOT,
    }
