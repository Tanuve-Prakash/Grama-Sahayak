"""Ingest official guideline PDFs into the knowledge base.

Drop a PDF into data/schemes/ghost/ (or pass a path) and this script splits it into sections and
writes a draft `<id>.md` in the same format as the curated documents, so a human can review it,
add the Kannada summary (KN: lines) and add a rules/<id>.yaml. Retrieval then picks it up.
Requires `pypdf` (optional dependency)."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from .config import settings


def pdf_to_md(pdf: Path, scheme_id: str, name_en: str, source_url: str = "") -> Path:
    try:
        from pypdf import PdfReader
    except ImportError:  # pragma: no cover
        sys.exit("pip install pypdf  (optional dependency for PDF ingestion)")
    text = "\n".join((p.extract_text() or "") for p in PdfReader(str(pdf)).pages)
    text = re.sub(r"[ \t]+", " ", text)
    paras = [p.strip().replace("\n", " ") for p in re.split(r"\n\s*\n", text) if len(p.strip()) > 60]
    out = ["---", f"id: {scheme_id}", f"name_en: {name_en}", f"name_kn: {name_en}", f"source_url: {source_url}", "---"]
    for i, p in enumerate(paras, 1):
        out += [f"## part-{i:02d}", f"EN: {p}", "KN: "]
    dst = settings.data_dir / "schemes" / f"{scheme_id}.md"
    dst.write_text("\n".join(out) + "\n", encoding="utf-8")
    return dst


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pdf", type=Path, nargs="?")
    ap.add_argument("--id"); ap.add_argument("--name"); ap.add_argument("--url", default="")
    ap.add_argument("--rebuild", action="store_true", help="rebuild the vector index from data/")
    a = ap.parse_args()
    if a.pdf:
        if not (a.id and a.name):
            ap.error("--id and --name are required with a PDF")
        print("wrote", pdf_to_md(a.pdf, a.id, a.name, a.url))
    from .knowledge import load_kb
    from .embeddings import get_embedder
    from .vectorstore import build_or_load
    kb = load_kb.__wrapped__()  # bypass cache
    emb = get_embedder()
    vs = build_or_load(list(kb.chunks.values()), emb, settings.index_path, force=True)
    print(f"index: {len(vs.ids)} chunks, backend={vs.backend}, embedder={emb.name}")


if __name__ == "__main__":
    main()
