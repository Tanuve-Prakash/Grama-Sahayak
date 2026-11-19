"""Shared agent plumbing: a Trace that records what every agent did (shown in the UI as
"How I answered", and used by tests and the evaluation script)."""
from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class TraceStep:
    agent: str
    summary: str
    ms: float
    ok: bool = True
    kind: str = "agent"          # agent | safety
    detail: Dict[str, Any] = field(default_factory=dict)


class Trace:
    def __init__(self) -> None:
        self.steps: List[TraceStep] = []

    @contextmanager
    def step(self, agent: str, kind: str = "agent"):
        rec = TraceStep(agent=agent, summary="", ms=0.0, kind=kind)
        t0 = time.perf_counter()
        try:
            yield rec
        except Exception as e:                       # record, then re-raise so callers can degrade gracefully
            rec.ok = False
            rec.summary = rec.summary or f"failed: {type(e).__name__}"
            raise
        finally:
            rec.ms = round((time.perf_counter() - t0) * 1000, 1)
            self.steps.append(rec)

    def add(self, agent: str, summary: str, ok: bool = True, kind: str = "agent", **detail: Any) -> None:
        self.steps.append(TraceStep(agent, summary, 0.0, ok, kind, detail))

    def to_list(self) -> List[dict]:
        return [s.__dict__ for s in self.steps]
