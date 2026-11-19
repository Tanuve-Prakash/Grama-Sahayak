"""Answer composer: turns verified-able facts into (1) a spoken answer, (2) structured cards the UI
renders (verdict, reasons, document checklist, sources) and (3) one follow-up question.

The deterministic template is the source of truth. If an LLM is configured it may *rephrase* the
template into more natural speech, but the Verifier checks the rephrasing and the template is used
whenever the rephrasing drifts (a changed number, verdict, or scheme name)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .. import facts as F
from ..config import settings
from ..i18n import DOCS, doc_name, out_lang, t
from ..knowledge import KnowledgeBase
from ..llm import llm
from .eligibility import EligibilityOutput
from .retrieval import RetrievalResult


@dataclass
class Card:
    scheme_id: str
    name: str
    verdict: Optional[str]                 # None for pure-information cards (documents/apply/benefits)
    verdict_label: str = ""
    reasons: List[dict] = field(default_factory=list)       # {status: pass|fail|unknown, text, source}
    to_confirm: List[str] = field(default_factory=list)
    benefit: str = ""
    documents: List[dict] = field(default_factory=list)     # {id, name}
    apply: str = ""
    hint: str = ""
    sources: List[dict] = field(default_factory=list)       # {chunk_id, section, url}
    cited_chunks: List[str] = field(default_factory=list)   # every chunk this card's claims rest on

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class Answer:
    lang: str
    text: str = ""                         # displayed
    speech: str = ""                       # spoken (no citations)
    cards: List[Card] = field(default_factory=list)
    question_key: Optional[str] = None
    question_text: Optional[str] = None
    helplines: List[dict] = field(default_factory=list)
    abstained: bool = False
    polished: bool = False
    template_text: str = ""                # kept so the verifier can fall back to it
    template_speech: str = ""
    tail: List[str] = field(default_factory=list)   # lines shown beside the cards (question, notes, disclaimer)


class Composer:
    def __init__(self, kb: KnowledgeBase):
        self.kb = kb

    # ------------------------------------------------------------------ pieces
    def _chunk_text(self, chunk_id: str, lang: str) -> str:
        return self.kb.chunks[chunk_id].lang_text(lang)

    def _source(self, chunk_id: str) -> dict:
        c = self.kb.chunks[chunk_id]
        return {"chunk_id": chunk_id, "section": c.section, "url": c.source_url, "scheme": c.scheme_name}

    def _docs(self, sid: str, lang: str) -> List[dict]:
        return [{"id": d, "name": doc_name(d, lang)} for d in self.kb.schemes[sid].rules_doc.get("documents", [])]

    def helplines(self, sid: Optional[str], lang: str) -> List[dict]:
        out = []
        for h in self.kb.helpline_for(sid):
            out.append({"id": h["id"], "name": h["name"][out_lang(lang)], "number": h["number"], "sms": bool(h.get("sms"))})
        return out

    # ------------------------------------------------------------------ eligibility card
    def eligibility_card(self, sid: str, ev, lang: str) -> Card:
        ol = out_lang(lang)
        sch = self.kb.schemes[sid]
        rd = sch.rules_doc
        card = Card(sid, sch.name[ol], ev.verdict, t(f"verdict_{ev.verdict}", lang))
        cited: List[str] = []
        for rr in ev.rules:
            text = rr.label.get(ol, "")
            if rr.status == "pass":
                # for an any-group show only the leaf that actually satisfied it
                true_leaves = [l for l in rr.leaves if l.status is True and l.label]
                if rr.kind == "required" and len(rr.leaves) > 1 and true_leaves:
                    text = true_leaves[0].label.get(ol, text)
                card.reasons.append({"status": "pass", "text": text, "source": rr.source})
                cited.append(rr.source)
            elif rr.status == "fail":
                card.reasons.append({"status": "fail", "text": text, "source": rr.source})
                cited.append(rr.source)
            else:
                card.reasons.append({"status": "unknown", "text": text, "source": rr.source})
                card.to_confirm.append(text)
        if ev.verdict in ("ELIGIBLE", "LIKELY"):
            card.benefit = self._chunk_text(rd["sections"]["benefits"], lang)
            card.apply = self._chunk_text(rd["sections"]["apply"], lang)
            card.documents = self._docs(sid, lang)
            cited += [rd["sections"]["benefits"], rd["sections"]["apply"], rd["sections"]["documents"]]
        if ev.verdict == "NOT_ELIGIBLE" and rd.get("if_not_eligible"):
            card.hint = rd["if_not_eligible"][ol]
            cited.append(rd["if_not_eligible_source"])
        card.cited_chunks = list(dict.fromkeys(cited))
        card.sources = [self._source(c) for c in card.cited_chunks]
        return card

    # ------------------------------------------------------------------ information cards
    def info_card(self, sid: str, intent: str, lang: str) -> Card:
        ol = out_lang(lang)
        sch = self.kb.schemes[sid]
        rd = sch.rules_doc
        card = Card(sid, sch.name[ol], None)
        if intent == "documents":
            card.documents = self._docs(sid, lang)
            card.benefit = ""
            cid = rd["sections"]["documents"]
        elif intent == "apply":
            card.apply = self._chunk_text(rd["sections"]["apply"], lang)
            cid = rd["sections"]["apply"]
        else:  # benefits
            card.benefit = self._chunk_text(rd["sections"]["benefits"], lang)
            cid = rd["sections"]["benefits"]
        card.cited_chunks = [cid]
        card.sources = [self._source(cid)]
        return card

    # ------------------------------------------------------------------ text rendering
    def render_card(self, c: Card, lang: str, with_sources: bool) -> List[str]:
        ol = out_lang(lang)
        L: List[str] = []
        if c.verdict:
            L.append(f"{c.name}: {c.verdict_label}.")
            passes = [r["text"] for r in c.reasons if r["status"] == "pass"]
            fails = [r["text"] for r in c.reasons if r["status"] == "fail"]
            if c.verdict in ("ELIGIBLE", "LIKELY") and passes:
                L.append(f"{t('reason_ok', lang)}: " + "; ".join(passes) + ".")
            if c.verdict == "NOT_ELIGIBLE" and fails:
                L.append(f"{t('reason_fail', lang)}: " + "; ".join(fails) + ".")
            if c.hint:
                L.append(c.hint)
            if c.to_confirm and c.verdict == "LIKELY":
                L.append(f"{t('to_confirm', lang)}: " + "; ".join(c.to_confirm) + ".")
        else:
            L.append(f"{c.name}:")
        if c.benefit:
            L.append(c.benefit)
        if c.documents:
            L.append(f"{t('bring', lang)}: " + ", ".join(d["name"] for d in c.documents) + ".")
        if c.apply:
            L.append(c.apply if c.verdict is None else f"{t('apply_intro', lang)}: {c.apply}")
        if with_sources and c.sources:
            L.append(f"{t('source', lang)}: " + ", ".join(s["scheme"][ol] + " (" + s["section"] + ")" for s in c.sources[:2]))
        return L

    # ------------------------------------------------------------------ public builders
    def compose_eligibility(self, out: EligibilityOutput, lang: str, skipped_any: bool,
                            question_key: Optional[str]) -> Answer:
        ans = Answer(lang=out_lang(lang))
        informative, need = [], []
        for sid, ev in out.evaluations.items():
            (need if ev.verdict == "NEED_INFO" else informative).append((sid, ev))
        order = {"ELIGIBLE": 0, "LIKELY": 1, "NOT_ELIGIBLE": 2}
        informative.sort(key=lambda p: order[p[1].verdict])
        for sid, ev in informative:
            ans.cards.append(self.eligibility_card(sid, ev, lang))
        for sid, ev in need:
            ans.cards.append(self.eligibility_card(sid, ev, lang))
        disp, spoken = [], []
        for c in [c for c in ans.cards if c.verdict != "NEED_INFO"]:
            disp += self.render_card(c, lang, True) + [""]
            spoken += self.render_card(c, lang, False)
        need_cards = [c for c in ans.cards if c.verdict == "NEED_INFO"]
        tail: List[str] = []
        if need_cards:
            names = ", ".join(c.name for c in need_cards)
            line = f"{t('verdict_NEED_INFO', lang)}: {names}."
            disp.append(line); spoken.append(line); tail.append(line)
        if skipped_any:
            disp.append(t("skipped_note", lang)); spoken.append(t("skipped_note", lang)); tail.append(t("skipped_note", lang))
        if question_key:
            q = F.FACTS[question_key].question[out_lang(lang)]
            ans.question_key, ans.question_text = question_key, q
            disp.append(f"{t('ask_missing_prefix', lang)} {q}")
            spoken.append(q); tail.append(f"{t('ask_missing_prefix', lang)} {q}")
        disp.append(t("disclaimer", lang)); spoken.append(t("disclaimer", lang)); tail.append(t("disclaimer", lang))
        ans.tail = tail
        ans.template_text = "\n".join(l for l in disp if l is not None).strip()
        ans.text = ans.template_text
        ans.speech = " ".join(spoken)
        ans.helplines = self.helplines(informative[0][0] if informative else None, lang)
        return ans

    def compose_info(self, intent: str, scheme_ids: List[str], lang: str) -> Answer:
        ans = Answer(lang=out_lang(lang))
        disp, spoken = [], []
        for sid in scheme_ids:
            c = self.info_card(sid, intent, lang)
            ans.cards.append(c)
            disp += self.render_card(c, lang, True) + [""]
            spoken += self.render_card(c, lang, False)
        disp.append(t("disclaimer", lang)); spoken.append(t("disclaimer", lang))
        ans.tail = [t("disclaimer", lang)]
        ans.template_text = ans.text = "\n".join(disp).strip()
        ans.speech = " ".join(spoken)
        ans.helplines = self.helplines(scheme_ids[0] if scheme_ids else None, lang)
        return ans

    def compose_helpline(self, scheme_ids: List[str], lang: str) -> Answer:
        ans = Answer(lang=out_lang(lang))
        sid = scheme_ids[0] if len(scheme_ids) == 1 else None
        ans.helplines = self.helplines(sid, lang)
        lines = [f"{t('helpline_intro', lang)}:"] + [f"{h['name']}: {h['number']}" for h in ans.helplines]
        ans.template_text = ans.text = "\n".join(lines)
        ans.speech = " ".join(lines)
        return ans

    def compose_scheme_list(self, lang: str, prompt_key: str = "which_schemes") -> Answer:
        ol = out_lang(lang)
        ans = Answer(lang=ol)
        names = [s.name[ol] for s in self.kb.schemes.values()]
        ans.text = ans.template_text = t(prompt_key, lang) + "\n" + "\n".join("• " + n for n in names)
        ans.speech = t(prompt_key, lang) + " " + ", ".join(names) + "."
        ans.helplines = self.helplines(None, lang)
        return ans

    def compose_abstain(self, lang: str, scheme_id: Optional[str] = None, reason: str = "unsure") -> Answer:
        ol = out_lang(lang)
        ans = Answer(lang=ol, abstained=True)
        ans.helplines = self.helplines(scheme_id, lang)
        office = self.kb.office_for(scheme_id, lang)
        hl = ans.helplines[0]["number"] if ans.helplines else "104"
        key = "unsure_verifier" if reason == "verifier" else "unsure"
        ans.text = ans.template_text = t(key, lang, office=office, helpline=hl)
        ans.speech = ans.text
        return ans

    # ------------------------------------------------------------------ optional LLM polish
    def polish(self, ans: Answer, lang: str) -> Answer:
        """Rephrase for natural speech. Output is untrusted until the Verifier accepts it."""
        if not (llm.available and settings.llm_polish) or ans.abstained or not ans.speech:
            return ans
        ol = out_lang(lang)
        sys_p = ("You rewrite a government-scheme answer for a rural listener who will HEAR it. "
                 f"Write in {'Kannada' if ol == 'kn' else 'simple English'}, short sentences, warm and clear. "
                 "Keep EVERY number, scheme name, verdict phrase and document name exactly as given. "
                 "Do not add any fact, scheme, amount or promise. Do not use bullet points or markdown.")
        out = llm.complete(sys_p, ans.speech, max_tokens=500)
        if out:
            ans.text = out.strip()
            ans.speech = ans.text
            ans.polished = True
        return ans
