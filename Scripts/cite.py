from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote

import fitz

from config import load_config


def pdf_page_uri(pdf_path: Path, page: int) -> str:
    """file:// URI with page fragment (works in Chrome, Edge, Acrobat)."""
    uri = pdf_path.resolve().as_uri()
    return f"{uri}#page={page}"


def search_snippet(page_text: str, query: str, window: int = 120) -> str:
    q = re.sub(r"\s+", " ", query.strip())
    normalized = re.sub(r"\s+", " ", page_text)
    idx = normalized.lower().find(q[:60].lower())
    if idx < 0:
        words = q.split()[:8]
        for i in range(len(words), 2, -1):
            partial = " ".join(words[:i])
            idx = normalized.lower().find(partial.lower())
            if idx >= 0:
                break
    if idx < 0:
        return q[:window]
    start = max(0, idx - 40)
    end = min(len(normalized), idx + window)
    return normalized[start:end].strip()


def highlight_passage(
    pdf_path: Path,
    page: int,
    snippet: str,
    output_path: Path,
) -> Path | None:
    doc = fitz.open(pdf_path)
    if page < 1 or page > len(doc):
        doc.close()
        return None

    pg = doc[page - 1]
    words = snippet.split()[:12]
    highlighted = False
    for n in range(len(words), 3, -1):
        phrase = " ".join(words[:n])
        rects = pg.search_for(phrase)
        if rects:
            for rect in rects[:3]:
                annot = pg.add_highlight_annot(rect)
                annot.set_colors(stroke=(1, 1, 0))
                annot.update()
            highlighted = True
            break

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(output_path)
    doc.close()
    return output_path if highlighted else None


def make_citation(
    pdf_path: Path,
    page: int,
    label: str,
    snippet: str,
    cite_id: str,
) -> dict:
    cfg = load_config()
    highlights_dir = cfg["cache_dir"] / "highlights"
    safe_name = pdf_path.stem[:60]
    out = highlights_dir / f"{safe_name}_p{page}_{cite_id}.pdf"

    highlighted = highlight_passage(pdf_path, page, snippet, out)
    link_path = highlighted or pdf_path

    return {
        "id": cite_id,
        "label": label,
        "page": page,
        "snippet": snippet,
        "uri": pdf_page_uri(link_path, page),
        "highlighted_pdf": str(highlighted) if highlighted else None,
        "markdown": f"[{label}]({pdf_page_uri(link_path, page)})",
    }
