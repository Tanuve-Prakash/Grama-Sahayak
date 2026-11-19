"""Loads the curated knowledge: scheme guideline documents (for retrieval/grounding),
machine-readable eligibility rules, and verified helplines."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, List, Optional

import yaml

from .config import settings
from .i18n import out_lang


@dataclass
class Chunk:
    id: str            # e.g. "pmjay#eligibility"
    scheme_id: str
    section: str
    text_en: str
    text_kn: str
    source_url: str
    scheme_name: Dict[str, str]

    @property
    def text(self) -> str:             # what gets embedded (both languages => cross-lingual keyword hits)
        return f"{self.scheme_name['en']} {self.section}. {self.text_en} {self.scheme_name['kn']} {self.text_kn}"

    def lang_text(self, lang: str) -> str:
        return self.text_kn if out_lang(lang) == "kn" and self.text_kn else self.text_en


@dataclass
class Scheme:
    id: str
    name: Dict[str, str]
    source_url: str
    rules_doc: dict
    aliases: Dict[str, List[str]] = field(default_factory=dict)


@dataclass
class KnowledgeBase:
    schemes: Dict[str, Scheme]
    chunks: Dict[str, Chunk]
    helplines: dict

    def chunks_of(self, scheme_id: str) -> List[Chunk]:
        return [c for c in self.chunks.values() if c.scheme_id == scheme_id]

    def helpline_for(self, scheme_id: Optional[str]) -> List[dict]:
        by = self.helplines.get("by_scheme", {})
        return list(by.get(scheme_id, [])) or list(self.helplines.get("general", [])[:2])

    def office_for(self, scheme_id: Optional[str], lang: str) -> str:
        offices = self.helplines.get("offices", {})
        o = offices.get(scheme_id) or offices["default"]
        return o[out_lang(lang)]


_FM = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.S)


def _parse_scheme_md(path) -> List[Chunk]:
    raw = path.read_text(encoding="utf-8")
    m = _FM.match(raw)
    if not m:
        raise ValueError(f"{path}: missing front matter")
    meta = yaml.safe_load(m.group(1))
    body = m.group(2)
    chunks: List[Chunk] = []
    for sec in re.split(r"^## ", body, flags=re.M)[1:]:
        head, _, rest = sec.partition("\n")
        section = head.strip()
        en = " ".join(l[3:].strip() for l in rest.splitlines() if l.startswith("EN:"))
        kn = " ".join(l[3:].strip() for l in rest.splitlines() if l.startswith("KN:"))
        if not (en or kn):  # untagged text (e.g. an ingested PDF) is treated as English
            en = " ".join(rest.split())
        chunks.append(Chunk(
            id=f"{meta['id']}#{section}", scheme_id=meta["id"], section=section,
            text_en=en, text_kn=kn, source_url=meta.get("source_url", ""),
            scheme_name={"en": meta["name_en"], "kn": meta["name_kn"]},
        ))
    return chunks


@lru_cache(maxsize=1)
def load_kb() -> KnowledgeBase:
    d = settings.data_dir
    schemes: Dict[str, Scheme] = {}
    chunks: Dict[str, Chunk] = {}
    for md in sorted((d / "schemes").glob("*.md")):
        for c in _parse_scheme_md(md):
            chunks[c.id] = c
    for y in sorted((d / "rules").glob("*.yaml")):
        doc = yaml.safe_load(y.read_text(encoding="utf-8"))
        sid = doc["id"]
        any_chunk = next((c for c in chunks.values() if c.scheme_id == sid), None)
        if any_chunk is None:
            raise ValueError(f"rules for {sid} have no matching scheme document")
        schemes[sid] = Scheme(sid, any_chunk.scheme_name, any_chunk.source_url, doc, doc.get("aliases", {}))
        # every cited chunk must exist: fail fast at start-up, not in front of a user
        cited = [r["source"] for r in doc["rules"]] + list(doc["sections"].values()) + [doc["if_not_eligible_source"]]
        for cid in cited:
            if cid not in chunks:
                raise ValueError(f"{y.name}: cites unknown chunk '{cid}'")
    helplines = yaml.safe_load((d / "helplines.yaml").read_text(encoding="utf-8"))
    return KnowledgeBase(schemes, chunks, helplines)
