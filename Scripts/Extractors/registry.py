from __future__ import annotations

from pathlib import Path

from extractors.base import ExtractedReport, extract_pages
from extractors import (
    abg_sundal,
    berenberg,
    bnp_paribas,
    bofa,
    cic,
    citi,
    deutsche_bank,
    dnb_carnegie,
    generic,
    goldman_sachs,
    jefferies,
    jp_morgan,
    kepler_cheuvreux,
    morgan_stanley,
    nordic_eu,
    redburn,
    ubs,
    zurcher,
)
from extractors.validate import validate_and_backfill


def resolve_extractor(broker: str) -> str:
    b = broker.lower()
    rules = [
        ("kepler", "kepler_cheuvreux"),
        ("dnb", "dnb_carnegie"),
        ("carnegie", "dnb_carnegie"),
        ("deutsche bank", "deutsche_bank"),
        ("bnp", "bnp_paribas"),
        ("berenberg", "berenberg"),
        ("abg", "abg_sundal"),
        ("jp morgan", "jp_morgan"),
        ("j.p. morgan", "jp_morgan"),
        ("morgan stanley", "morgan_stanley"),
        ("goldman", "goldman_sachs"),
        ("citi", "citi"),
        ("ubs", "ubs"),
        ("bofa", "bofa"),
        ("bank of america", "bofa"),
        ("jefferies", "jefferies"),
        ("cic", "cic"),
        ("zurcher", "zurcher"),
        ("zürcher", "zurcher"),
        ("redburn", "redburn"),
        ("rothschild", "redburn"),
        ("nordea", "nordic_eu"),
        ("stifel", "nordic_eu"),
        ("oddo", "nordic_eu"),
        ("danske", "nordic_eu"),
        ("pareto", "nordic_eu"),
        ("panmure", "nordic_eu"),
        ("kbc", "nordic_eu"),
        ("ing", "nordic_eu"),
        ("degroof", "nordic_eu"),
        ("intermonte", "nordic_eu"),
        ("alantra", "nordic_eu"),
        ("bestinver", "nordic_eu"),
    ]
    for needle, name in rules:
        if needle in b:
            return name
    return "generic_fallback"


def extract_with_registry(
    pdf_path: Path | str,
    broker: str,
    ticker_hint: str = "",
) -> ExtractedReport:
    pages = extract_pages(pdf_path)
    name = resolve_extractor(broker)

    extractors = {
        "kepler_cheuvreux": kepler_cheuvreux.extract,
        "dnb_carnegie": dnb_carnegie.extract,
        "deutsche_bank": deutsche_bank.extract,
        "bnp_paribas": bnp_paribas.extract,
        "berenberg": berenberg.extract,
        "abg_sundal": abg_sundal.extract,
        "jp_morgan": jp_morgan.extract,
        "morgan_stanley": morgan_stanley.extract,
        "goldman_sachs": goldman_sachs.extract,
        "citi": citi.extract,
        "ubs": ubs.extract,
        "bofa": bofa.extract,
        "jefferies": jefferies.extract,
        "cic": cic.extract,
        "zurcher": zurcher.extract,
        "redburn": redburn.extract,
        "nordic_eu": nordic_eu.extract,
        "generic_fallback": generic.extract,
    }
    result = extractors[name](pages)
    result, _signals, _attempts = validate_and_backfill(result, broker, ticker_hint=ticker_hint)
    return result
