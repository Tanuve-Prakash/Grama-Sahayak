"""In-memory sessions. Nothing here is ever written to disk or a database: sessions expire after a
TTL (default 30 min) and the user can erase theirs at any time ("forget me")."""
from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .config import settings


@dataclass
class Session:
    id: str
    lang: str = "kn"
    facts: Dict[str, Any] = field(default_factory=dict)
    fact_source: Dict[str, str] = field(default_factory=dict)       # key -> speech|document|typed|button
    skipped: set = field(default_factory=set)                       # facts the user said "I don't know" to
    pending_question: Optional[str] = None                          # fact key we just asked about
    pending_doc: Optional[dict] = None                              # extracted-but-unconfirmed document fields
    last_intent: Optional[str] = None
    last_schemes: List[str] = field(default_factory=list)
    last_text: str = ""
    turns: int = 0
    clarify_count: int = 0                                          # failed attempts to answer the pending question
    question_streak: int = 0                                        # follow-ups asked in a row (capped)
    created: float = field(default_factory=time.time)
    touched: float = field(default_factory=time.time)

    def set_fact(self, key: str, value: Any, source: str) -> None:
        self.facts[key] = value
        self.fact_source[key] = source
        self.skipped.discard(key)

    def forget(self) -> None:
        self.facts.clear(); self.fact_source.clear(); self.skipped.clear()
        self.pending_question = None; self.pending_doc = None
        self.last_intent = None; self.last_schemes = []; self.last_text = ""; self.question_streak = 0; self.clarify_count = 0


class SessionStore:
    MAX_SESSIONS = 5000

    def __init__(self, ttl_s: int | None = None):
        self.ttl = ttl_s or settings.session_ttl_s
        self._d: Dict[str, Session] = {}
        self._lock = threading.Lock()

    def create(self, lang: str = "kn") -> Session:
        with self._lock:
            self._purge_locked()
            if len(self._d) >= self.MAX_SESSIONS:  # shed oldest rather than grow without bound
                oldest = min(self._d.values(), key=lambda s: s.touched)
                self._d.pop(oldest.id, None)
            s = Session(id=secrets.token_urlsafe(16), lang=lang)
            self._d[s.id] = s
            return s

    def get(self, sid: str) -> Optional[Session]:
        with self._lock:
            self._purge_locked()
            s = self._d.get(sid)
            if s:
                s.touched = time.time()
            return s

    def delete(self, sid: str) -> None:
        with self._lock:
            self._d.pop(sid, None)

    def _purge_locked(self) -> None:
        now = time.time()
        for sid in [k for k, v in self._d.items() if now - v.touched > self.ttl]:
            self._d.pop(sid, None)

    def __len__(self) -> int:
        return len(self._d)
