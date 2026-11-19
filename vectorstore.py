"""Vector store: FAISS (IndexFlatIP) when installed, otherwise exact NumPy cosine search.
Vectors are L2-normalised so inner product == cosine similarity. The index is persisted
to disk together with a content hash, so a changed knowledge base triggers a rebuild."""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import numpy as np

from .embeddings import Embedder
from .knowledge import Chunk

log = logging.getLogger("grama.vs")
try:  # optional accelerator
    import faiss  # type: ignore
    HAVE_FAISS = True
except Exception:
    faiss = None
    HAVE_FAISS = False


def content_hash(chunks: Sequence[Chunk], embedder_name: str) -> str:
    h = hashlib.sha256(embedder_name.encode())
    for c in sorted(chunks, key=lambda c: c.id):
        h.update(c.id.encode()); h.update(c.text.encode())
    return h.hexdigest()


class VectorStore:
    def __init__(self, ids: List[str], vectors: np.ndarray, scheme_ids: List[str]):
        self.ids = ids
        self.vectors = vectors.astype(np.float32)
        self.scheme_ids = scheme_ids
        self._index = None
        if HAVE_FAISS:
            self._index = faiss.IndexFlatIP(self.vectors.shape[1])
            self._index.add(self.vectors)

    @property
    def backend(self) -> str:
        return "faiss" if self._index is not None else "numpy"

    def search(self, qvec: np.ndarray, k: int, scheme_filter: Optional[Sequence[str]] = None) -> List[Tuple[str, float]]:
        q = qvec.reshape(1, -1).astype(np.float32)
        if scheme_filter:
            mask = np.array([s in set(scheme_filter) for s in self.scheme_ids])
            sims = (self.vectors @ q.T).ravel()
            sims = np.where(mask, sims, -1.0)
            order = np.argsort(-sims)[:k]
            return [(self.ids[i], float(sims[i])) for i in order if sims[i] > -1.0]
        if self._index is not None:
            scores, idx = self._index.search(q, min(k, len(self.ids)))
            return [(self.ids[i], float(s)) for s, i in zip(scores[0], idx[0]) if i >= 0]
        sims = (self.vectors @ q.T).ravel()
        order = np.argsort(-sims)[:k]
        return [(self.ids[i], float(sims[i])) for i in order]

    # ---- persistence
    def save(self, path: Path, digest: str, embedder_name: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, ids=np.array(self.ids), vectors=self.vectors,
                            scheme_ids=np.array(self.scheme_ids), digest=digest, embedder=embedder_name)

    @classmethod
    def load(cls, path: Path, digest: str) -> Optional["VectorStore"]:
        try:
            z = np.load(path, allow_pickle=False)
            if str(z["digest"]) != digest:
                return None
            return cls([str(i) for i in z["ids"]], z["vectors"], [str(s) for s in z["scheme_ids"]])
        except Exception:
            return None


def build_or_load(chunks: Sequence[Chunk], embedder: Embedder, path: Path, force: bool = False) -> VectorStore:
    digest = content_hash(chunks, embedder.name)
    if not force:
        vs = VectorStore.load(path, digest)
        if vs is not None:
            log.info("loaded index (%s, %d chunks)", vs.backend, len(vs.ids))
            return vs
    vecs = embedder.encode([c.text for c in chunks])
    vs = VectorStore([c.id for c in chunks], vecs, [c.scheme_id for c in chunks])
    try:
        vs.save(path, digest, embedder.name)
    except OSError as e:  # read-only FS is fine; index is cheap to rebuild
        log.warning("could not persist index: %s", e)
    log.info("built index (%s, %d chunks)", vs.backend, len(vs.ids))
    return vs
