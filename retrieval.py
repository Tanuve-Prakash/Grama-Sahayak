"""Retrieval agent (slide 4): finds the scheme-guideline passages that match the question.

Hybrid ranking = dense similarity (multilingual embeddings, or the offline hashing embedder) fused
with IDF-weighted lexical coverage, plus a boost for schemes the user named. Each attempt widens the
search, because the Verifier may reject an answer and send it back here (the dashed arrow on the
architecture slide):

   attempt 0  top-k hybrid
   attempt 1  wider k, query expanded with scheme names, target schemes pinned
   attempt 2  every section of every target scheme (last resort before the system abstains)"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import numpy as np

from ..config import settings
from ..embeddings import Embedder, tokenize
from ..knowledge import Chunk, KnowledgeBase
from ..vectorstore import VectorStore, build_or_load


@dataclass
class Retrieved:
    chunk: Chunk
    score: float
    dense: float
    lexical: float


@dataclass
class RetrievalResult:
    hits: List[Retrieved]
    relevance: float                    # best un-boosted hybrid score (used for the out-of-scope gate)
    domain_coverage: float              # share of query content words the knowledge base knows
    attempt: int
    pinned: List[str] = field(default_factory=list)
    query: str = ""
    in_domain: bool = True

    @property
    def ids(self) -> List[str]:
        return [h.chunk.id for h in self.hits]

    def summary(self) -> str:
        top = ", ".join(f"{h.chunk.id}({h.score:.2f})" for h in self.hits[:3])
        return f"attempt {self.attempt}: {len(self.hits)} passages, relevance={self.relevance:.2f}; top: {top}"


class RetrievalAgent:
    def __init__(self, kb: KnowledgeBase, embedder: Embedder):
        self.kb = kb
        self.embedder = embedder
        chunks = list(kb.chunks.values())
        if hasattr(embedder, "fit"):
            embedder.fit([c.text for c in chunks])               # type: ignore[attr-defined]
        self.store: VectorStore = build_or_load(chunks, embedder, settings.index_path)
        # lexical statistics
        self._tok: Dict[str, set] = {c.id: set(tokenize(c.text, drop_stop=True)) for c in chunks}
        n = len(chunks)
        df: Dict[str, int] = {}
        for toks in self._tok.values():
            for t in toks:
                df[t] = df.get(t, 0) + 1
        import math
        self._idf = {t: math.log((n + 1) / (d + 0.5)) + 1 for t, d in df.items()}
        self._vocab_prefix = {t[:5] for t in df}

    # ------------------------------------------------------------ lexical helpers
    def _match(self, qt: str, toks: set) -> bool:
        if qt in toks:
            return True
        p = qt[:5]                                              # inflection tolerance (Kannada suffixes)
        return len(p) >= 4 and any(t.startswith(p) for t in toks)

    def _lexical(self, qtoks: Sequence[str], chunk_id: str) -> float:
        if not qtoks:
            return 0.0
        toks = self._tok[chunk_id]
        tot = sum(self._idf.get(q, 1.5) for q in qtoks)
        got = sum(self._idf.get(q, 1.5) for q in qtoks if self._match(q, toks))
        return got / tot if tot else 0.0

    def _domain_coverage(self, qtoks: Sequence[str]) -> float:
        if not qtoks:
            return 0.0
        known = sum(1 for q in qtoks if q in self._idf or q[:5] in self._vocab_prefix)
        return known / len(qtoks)

    # ------------------------------------------------------------ main
    def run(self, text: str, schemes: Sequence[str] = (), attempt: int = 0, k: Optional[int] = None) -> RetrievalResult:
        k = k or settings.top_k
        query = text
        if attempt >= 1 and schemes:
            query += " " + " ".join(self.kb.schemes[s].name["en"] + " " + self.kb.schemes[s].name["kn"] for s in schemes)
            query += " eligibility documents benefits how to apply"
        qtoks = tokenize(text, drop_stop=True)
        qvec = self.embedder.encode([query])[0]
        dense = dict(self.store.search(qvec, k=len(self.store.ids)))

        scored: List[Retrieved] = []
        for cid, chunk in self.kb.chunks.items():
            d = max(0.0, dense.get(cid, 0.0))
            lex = self._lexical(qtoks, cid)
            base = 0.5 * min(1.0, d / 0.35) + 0.5 * lex
            scored.append(Retrieved(chunk, base, d, lex))
        relevance = max((s.score for s in scored), default=0.0)

        if schemes:                                             # boost what the user explicitly named
            boost = 0.25 if attempt == 0 else 0.6
            for s in scored:
                if s.chunk.scheme_id in schemes:
                    s.score += boost
        scored.sort(key=lambda s: -s.score)

        pinned: List[str] = []
        if attempt == 0:
            hits = scored[:k]
        elif attempt == 1:
            hits = scored[: k + 4]
            pinned = list(schemes)
        else:
            pinned = list(schemes)
            wanted = {s.chunk.id for s in scored if s.chunk.scheme_id in schemes}
            hits = [s for s in scored if s.chunk.id in wanted] or scored[: k + 6]
        cov = self._domain_coverage(qtoks)
        # Out-of-knowledge-base gate (slide 6): named scheme, or clearly strong lexical+semantic match.
        in_domain = bool(schemes) or (relevance >= 0.45 and cov >= 0.5) or relevance >= 0.6
        return RetrievalResult(hits, relevance, cov, attempt, pinned, query, in_domain)
