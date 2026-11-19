"""Verifier agent (slide 4): "checks answer against source" before anything is spoken.

Independent of the agents that built the answer, it re-checks every claim deterministically:

  verdict_mismatch    card verdict differs from a fresh re-run of the rules engine on the same facts
  missing_citation    a claim rests on a guideline section that was not actually retrieved
  unsupported_number  a number in the text appears in no retrieved passage, user fact, or helpline list
  unretrieved_scheme  the text names a scheme whose guideline was not retrieved
  verdict_dropped     (LLM rephrase) a card's verdict phrase disappeared from the text
  overclaim           absolute language ("guaranteed", "100%") that guidelines cannot support
  wrong_language      the reply is not in the language the person is using
  no_disclaimer       missing the "guidance, not a final decision" line

Outcomes: approve | retry_retrieval (dashed arrow back to the Retrieval agent) | fallback_template
(an LLM rephrase failed: use the deterministic text) | abstain (say "I am not sure" + helpline)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Set

from ..i18n import normalize_digits, out_lang, t
from ..knowledge import KnowledgeBase
from .rules_engine import evaluate
from .composer import Answer
from .retrieval import RetrievalResult

_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
_OVERCLAIM = re.compile(r"guarantee|100\s?%|definitely|certainly will|no doubt|ಖಂಡಿತ|ಖಚಿತವಾಗಿ ಸಿಗುತ್ತದೆ", re.I)
RETRIEVAL_FIXABLE = {"missing_citation", "unretrieved_scheme", "unsupported_number"}


def numbers_in(text: str) -> Set[str]:
    out = set()
    for m in _NUM.findall(normalize_digits(text)):
        n = m.replace(",", "").rstrip(".")
        out.add(n[:-2] if n.endswith(".0") else n)
    return out


@dataclass
class Report:
    approved: bool
    action: str                    # approve | retry_retrieval | fallback_template | abstain
    issues: List[dict] = field(default_factory=list)
    checks_run: int = 0

    def summary(self) -> str:
        if self.approved:
            return f"approved ({self.checks_run} checks passed)"
        return f"{self.action}: " + ", ".join(i["code"] for i in self.issues)


class VerifierAgent:
    def __init__(self, kb: KnowledgeBase):
        self.kb = kb
        self._helpline_nums: Set[str] = set()
        hl = kb.helplines
        for h in list(hl.get("general", [])) + [x for v in hl.get("by_scheme", {}).values() for x in v]:
            self._helpline_nums.add(str(h["number"]))

    def _issue(self, code: str, detail: str = "") -> dict:
        return {"code": code, "detail": detail}

    def check(self, ans: Answer, retr: RetrievalResult, facts: Dict[str, Any], skipped: set,
              lang: str, eligibility_mode: bool, attempts_left: bool) -> Report:
        issues: List[dict] = []
        n = 0
        retrieved = set(retr.ids)
        ol = out_lang(lang)

        # grounding corpus for numbers: retrieved passages (both languages), facts, helplines
        allowed: Set[str] = set(self._helpline_nums)
        for h in retr.hits:
            allowed |= numbers_in(h.chunk.text_en) | numbers_in(h.chunk.text_kn)
        for v in facts.values():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                allowed |= numbers_in(str(v))

        # 1) verdicts must equal an independent re-evaluation
        if eligibility_mode:
            for c in ans.cards:
                n += 1
                if c.verdict is None:
                    continue
                fresh = evaluate(c.scheme_id, self.kb.schemes[c.scheme_id].rules_doc, facts, skipped).verdict
                if fresh != c.verdict:
                    issues.append(self._issue("verdict_mismatch", f"{c.scheme_id}: {c.verdict} vs {fresh}"))

        # 2) every cited section must have been retrieved
        for c in ans.cards:
            for cid in c.cited_chunks:
                n += 1
                if cid not in retrieved:
                    issues.append(self._issue("missing_citation", cid))

        # 3) numbers
        n += 1
        for num in sorted(numbers_in(ans.text) | numbers_in(ans.speech)):
            if num not in allowed:
                issues.append(self._issue("unsupported_number", num))

        # 4) scheme names only if their guideline was retrieved
        n += 1
        text_all = ans.text + " " + ans.speech
        for sid, sch in self.kb.schemes.items():
            if (sch.name["en"] in text_all or sch.name["kn"] in text_all) and \
                    not any(i.startswith(sid + "#") for i in retrieved):
                issues.append(self._issue("unretrieved_scheme", sid))

        # 5) rephrase integrity: verdict phrases survive
        if ans.polished:
            for c in ans.cards:
                n += 1
                if c.verdict and c.verdict_label and c.verdict_label not in ans.text:
                    issues.append(self._issue("verdict_dropped", c.scheme_id))

        # 6) tone, language, disclaimer
        n += 1
        if _OVERCLAIM.search(text_all):
            issues.append(self._issue("overclaim"))
        n += 1
        letters = [ch for ch in ans.text if ch.isalpha()]
        if letters:
            kn_ratio = sum("\u0c80" <= ch <= "\u0cff" for ch in letters) / len(letters)
            if (ol == "kn" and kn_ratio < 0.2) or (ol == "en" and kn_ratio > 0.2):
                issues.append(self._issue("wrong_language"))
        if eligibility_mode or ans.cards:
            n += 1
            if t("disclaimer", lang) not in ans.text and not ans.polished:
                issues.append(self._issue("no_disclaimer"))

        if not issues:
            return Report(True, "approve", [], n)

        codes = {i["code"] for i in issues}
        if ans.polished and not (codes & {"verdict_mismatch", "missing_citation", "unretrieved_scheme"}):
            return Report(False, "fallback_template", issues, n)       # drop the LLM wording, keep the facts
        if codes <= RETRIEVAL_FIXABLE and attempts_left:
            return Report(False, "retry_retrieval", issues, n)
        if ans.polished:
            return Report(False, "fallback_template", issues, n)
        return Report(False, "abstain", issues, n)
