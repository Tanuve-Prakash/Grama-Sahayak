"""Eligibility agent (slide 4): combine facts from speech + document photo, match them to scheme
rules, and decide what (if anything) to ask next."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .. import facts as F
from ..knowledge import KnowledgeBase
from .rules_engine import Evaluation, evaluate


@dataclass
class EligibilityOutput:
    evaluations: Dict[str, Evaluation] = field(default_factory=dict)
    next_question: Optional[str] = None            # fact key to ask next (one at a time, by voice)

    def summary(self) -> str:
        return "; ".join(f"{s}={e.verdict}" for s, e in self.evaluations.items())


class EligibilityAgent:
    def __init__(self, kb: KnowledgeBase):
        self.kb = kb

    def run(self, scheme_ids: List[str], facts: Dict[str, Any], skipped: set) -> EligibilityOutput:
        out = EligibilityOutput()
        for sid in scheme_ids:
            out.evaluations[sid] = evaluate(sid, self.kb.schemes[sid].rules_doc, facts, skipped)
        out.next_question = self._pick_question(out)
        return out

    @staticmethod
    def _pick_question(out: EligibilityOutput) -> Optional[str]:
        """Ask about the fact that unblocks the most schemes; break ties by the schema priority."""
        counts: Counter = Counter()
        for ev in out.evaluations.values():
            if ev.verdict == "NEED_INFO":
                counts.update(ev.askable)
        # a fact also helps LIKELY-able verdicts, but those have no askable by construction
        if not counts:
            return None
        return sorted(counts, key=lambda k: (-counts[k], F.FACTS[k].priority))[0]
