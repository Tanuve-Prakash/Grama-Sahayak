"""Embedding back-ends.

* SentenceTransformerEmbedder – multilingual dense model (best quality; needs `sentence-transformers`).
* HashingEmbedder – dependency-free character n-gram embedder. It is fully offline and works for
  Kannada because it hashes sub-word character n-grams, which tolerate Kannada's rich inflection.
  It is what makes the project run on a laptop with no downloads, and it is the CI default."""
from __future__ import annotations

import logging
import re
import unicodedata
import zlib
from typing import List, Protocol

import numpy as np

from .config import settings
from .i18n import normalize_digits

log = logging.getLogger("grama.embed")
_TOKEN = re.compile(r"[^\s.,;:!?()\[\]{}\"'।|/\\\-–—#]+")


STOPWORDS = set("""a an the is are am was be been i me my we our you your to of for in on at and or with what which who how
can could do does did get gets got will would should it its this that these those there any from have has had about please tell
want need if so as by not no yes ok also very more some than then them they he she his her us up out into over under again
scheme schemes government sarkar""".split()) | set("""ಮತ್ತು ಅಥವಾ ಈ ಆ ಒಂದು ನಾನು ನನ್ನ ನನಗೆ ನೀವು ನಿಮ್ಮ ನಿಮಗೆ ಇದೆ ಇದು ಅದು ಏನು ಯಾವ ಯಾವುದು ಹೇಗೆ ಎಂದು ಎಂದರೆ
ಇದೆಯೇ ಇವೆ ಆಗಿ ಆಗಿದೆ ಕೂಡ ಸಹ ಮಾತ್ರ""".split())


def tokenize(text: str, drop_stop: bool = False) -> List[str]:
    t = normalize_digits(unicodedata.normalize("NFC", text)).lower()
    toks = _TOKEN.findall(t)
    return [w for w in toks if w not in STOPWORDS] if drop_stop else toks


class Embedder(Protocol):
    name: str
    dim: int

    def encode(self, texts: List[str]) -> np.ndarray: ...


class HashingEmbedder:
    def __init__(self, dim: int = 4096, ngram_range=(2, 4)):
        self.dim = dim
        self.ngram_range = ngram_range
        self.name = f"hashing-{dim}-{ngram_range[0]}{ngram_range[1]}-idf"
        self._idf = np.ones(dim, dtype=np.float32)

    def fit(self, corpus: List[str]) -> "HashingEmbedder":
        """Learn bucket IDF from the knowledge base so generic words stop dominating similarity."""
        df = np.zeros(self.dim, dtype=np.float32)
        for text in corpus:
            seen = {zlib.crc32(f.encode("utf-8")) % self.dim for f, _ in self._feats(text)}
            for b in seen:
                df[b] += 1.0
        n = max(len(corpus), 1)
        self._idf = (np.log((n + 1.0) / (df + 1.0)) + 1.0).astype(np.float32)
        return self

    def _feats(self, text: str):
        for tok in tokenize(text, drop_stop=True):
            yield "w:" + tok, 2.0                       # whole words count more
            padded = f"^{tok}$"
            lo, hi = self.ngram_range
            for n in range(lo, hi + 1):
                for i in range(len(padded) - n + 1):
                    yield "c:" + padded[i:i + n], 1.0

    def encode(self, texts: List[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for r, text in enumerate(texts):
            for feat, w in self._feats(text):
                h = zlib.crc32(feat.encode("utf-8"))
                out[r, h % self.dim] += w * (1.0 if (h >> 31) & 1 else -1.0)
        # sublinear scaling, IDF weighting, then L2 normalise
        out = np.sign(out) * np.log1p(np.abs(out)) * self._idf[None, :]
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return (out / norms).astype(np.float32)


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer  # lazy, optional
        self._m = SentenceTransformer(model_name)
        self.dim = int(self._m.get_sentence_embedding_dimension())
        self.name = f"st-{model_name}"

    def encode(self, texts: List[str]) -> np.ndarray:
        v = self._m.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return np.asarray(v, dtype=np.float32)


_cached: Embedder | None = None


def get_embedder() -> Embedder:
    global _cached
    if _cached is not None:
        return _cached
    choice = settings.embedder
    if choice in ("auto", "st"):
        try:
            _cached = SentenceTransformerEmbedder(settings.st_model)
            log.info("embedder: %s", _cached.name)
            return _cached
        except Exception as e:  # not installed / offline
            if choice == "st":
                raise
            log.info("sentence-transformers unavailable (%s); using hashing embedder", type(e).__name__)
    _cached = HashingEmbedder()
    return _cached
