"""Orchestrator: the multi-agent pipeline from the architecture slide.

    input guard -> Intake -> [Vision] -> Retrieval -> Eligibility -> Composer -> Verifier -+-> spoken answer
                                            ^                                              |
                                            +----------- rejected: re-retrieve ------------+

A plain-Python state machine (the deck allows "LangGraph or a plain Python pipeline"): each agent is a
small class with one job, every step is traced, and the loop is bounded so a stubborn failure ends in an
honest "I am not sure" with a helpline instead of a guess."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from . import facts as F
from .agents.composer import Answer, Composer
from .agents.eligibility import EligibilityAgent
from .agents.base import Trace
from .agents.intake import IntakeAgent
from .agents.retrieval import RetrievalAgent
from .agents.verifier import VerifierAgent
from .agents.vision import VisionAgent
from .config import settings
from .embeddings import get_embedder
from .guards import guard_input, mask_pii
from .i18n import DOC_TYPE_NAMES, out_lang, t
from .knowledge import load_kb
from .session import Session

log = logging.getLogger("grama.orch")
MAX_FOLLOWUPS = 5
INFO_INTENTS = {"documents", "apply", "benefits"}


class Orchestrator:
    def __init__(self) -> None:
        self.kb = load_kb()
        self.embedder = get_embedder()
        self.intake = IntakeAgent(self.kb)
        self.vision = VisionAgent()
        self.retrieval = RetrievalAgent(self.kb, self.embedder)
        self.eligibility = EligibilityAgent(self.kb)
        self.composer = Composer(self.kb)
        self.verifier = VerifierAgent(self.kb)

    # ================================================================= public API
    def handle_text(self, s: Session, text: str, lang_hint: Optional[str] = None) -> dict:
        trace = Trace()
        s.turns += 1
        if lang_hint in ("kn", "en", "tcy"):
            s.lang = lang_hint
        lang = s.lang
        g = guard_input(text)
        trace.add("Input guard", "ok" if g.ok else "blocked: " + ",".join(g.flags), ok=g.ok, kind="safety",
                  flags=g.flags)
        if not g.ok:
            msg = t("input_rejected", lang) if "prompt_injection" in g.flags else t("not_understood_answer", lang)
            ans = Answer(lang=out_lang(lang), text=msg, speech=msg, abstained=True)
            return self._respond(s, ans, trace, "blocked")

        with trace.step("Intake") as st:
            ir = self.intake.run(g.text, s.lang, s.pending_question, s.pending_doc is not None)
            st.summary = ir.summary() + (" (+LLM)" if ir.used_llm else "")
        lang = self._reply_lang(s, g.text, ir.lang)
        s.lang = lang if s.lang != "tcy" else "tcy"

        intent = ir.intent
        if intent == "forget":
            s.forget()
            return self._respond(s, self._plain(t("forgot", lang), lang), trace, "forget")
        if intent == "doc_yes":
            return self._commit_document(s, {}, trace, lang)
        if intent == "doc_no":
            s.pending_doc = None
            return self._respond(s, self._plain(t("doc_discarded", lang), lang), trace, "doc_no")

        # ---- follow-up answer: store it, then resume the interrupted request
        if intent == "answer":
            s.clarify_count = 0
            if ir.skip and ir.answered:
                s.skipped.add(ir.answered)
            for k, v in ir.facts.items():
                s.set_fact(k, v, "speech")
            s.pending_question = None
            return self._run_pipeline(s, s.last_intent or "eligibility", s.last_schemes or list(self.kb.schemes),
                                      s.last_text or g.text, lang, trace, keep_streak=True)

        # ---- a pending question the user did not answer
        if s.pending_question and ir.intent == "other":
            s.clarify_count += 1
            if s.clarify_count >= 2:                      # never nag: treat it as "I don't know" and move on
                s.skipped.add(s.pending_question)
                s.pending_question, s.clarify_count = None, 0
                trace.add("Intake", "question not understood twice; continuing with partial information", ok=False)
                return self._run_pipeline(s, s.last_intent or "eligibility", s.last_schemes or list(self.kb.schemes),
                                          s.last_text or g.text, lang, trace, keep_streak=True)
            q = F.FACTS[s.pending_question].question[out_lang(lang)]
            msg = f"{t('not_understood_answer', lang)} {q}"
            ans = Answer(lang=out_lang(lang), text=msg, speech=msg,
                         question_key=s.pending_question, question_text=q)
            return self._respond(s, ans, trace, "clarify")

        # ---- a fresh request
        s.pending_question = None
        s.question_streak = s.clarify_count = 0
        for k, v in ir.facts.items():
            s.set_fact(k, v, "speech")
        if intent == "greeting":
            return self._respond(s, self.composer.compose_scheme_list(lang, "greeting"), trace, intent)
        if intent == "list_schemes":
            return self._respond(s, self.composer.compose_scheme_list(lang), trace, intent)
        if intent == "other":
            return self._abstain_response(s, trace, lang, "Intake", "no scheme, fact or supported intent")

        schemes = list(ir.schemes)
        if intent == "eligibility":
            schemes = schemes or (s.last_schemes if ir.facts and s.last_schemes else list(self.kb.schemes))
        elif not schemes:
            schemes = list(s.last_schemes)
        s.last_text = mask_pii(g.text)
        if not schemes and intent != "helpline":
            # information question without a scheme: is it even in our domain?
            probe = self.retrieval.run(g.text, [], 0)
            trace.add("Retrieval", probe.summary())
            if not probe.in_domain:
                return self._abstain_response(s, trace, lang, "Retrieval", "outside the knowledge base")
            return self._respond(s, self.composer.compose_scheme_list(lang), trace, "clarify")
        return self._run_pipeline(s, intent, schemes[:4] if intent != "eligibility" else schemes,
                                  g.text, lang, trace)

    def handle_image(self, s: Session, image: bytes, mime: str, lang_hint: Optional[str] = None) -> dict:
        trace = Trace()
        if lang_hint in ("kn", "en", "tcy"):
            s.lang = lang_hint
        lang = s.lang
        ol = out_lang(lang)
        with trace.step("Vision") as st:
            res = self.vision.run(image, mime)
            st.summary = res.summary()
            st.ok = bool(res.fields)
        del image                                                          # never retained
        trace.add("Data guard", "image processed in memory and discarded; Aadhaar reduced to last 4 digits",
                  kind="safety", aadhaar=res.aadhaar_masked)
        if not res.fields:
            ans = self._plain(t("doc_none", lang), lang)
            return self._respond(s, ans, trace, "vision_failed", extra={"warnings": res.warnings})
        s.pending_doc = {"doc_type": res.doc_type,
                         "fields": [{"key": f.key, "value": f.value, "confidence": f.confidence} for f in res.fields]}
        dn = DOC_TYPE_NAMES.get(res.doc_type, DOC_TYPE_NAMES["unknown"])[ol]
        rows = [f.to_dict(ol) for f in res.fields]
        lines = [t("doc_read", lang, doc=dn)] + [
            f"• {r['label']}: {r['display']}" + (f" {t('low_conf', lang)}" if r["low_confidence"] else "") for r in rows]
        spoken = [t("doc_read", lang, doc=dn)] + [f"{r['label']}: {r['display']}." for r in rows]
        lines.append(t("doc_confirm", lang)); spoken.append(t("doc_confirm", lang))
        ans = Answer(lang=ol, text="\n".join(lines), speech=" ".join(spoken))
        confirm = {"doc_type": res.doc_type, "doc_name": dn, "fields": rows, "aadhaar": res.aadhaar_masked}
        return self._respond(s, ans, trace, "confirm_document", confirm=confirm,
                             extra={"warnings": res.warnings})

    def confirm_document(self, s: Session, accept: bool, corrections: Optional[Dict[str, Any]] = None) -> dict:
        trace = Trace()
        lang = s.lang
        if not s.pending_doc:
            return self._respond(s, self._plain(t("not_understood_answer", lang), lang), trace, "noop")
        if not accept:
            s.pending_doc = None
            return self._respond(s, self._plain(t("doc_discarded", lang), lang), trace, "doc_no")
        return self._commit_document(s, corrections or {}, trace, lang)

    def forget(self, s: Session) -> dict:
        s.forget()
        return self._respond(s, self._plain(t("forgot", s.lang), s.lang), Trace(), "forget")

    # ================================================================= internals
    def _plain(self, text: str, lang: str) -> Answer:
        return Answer(lang=out_lang(lang), text=text, speech=text)

    def _reply_lang(self, s: Session, text: str, detected: str) -> str:
        """Reply in the language the person is actually speaking; short replies keep the session language."""
        if detected == "kn":
            return "tcy" if s.lang == "tcy" else "kn"
        if len(text.split()) >= 3:
            return "en"
        return s.lang

    def _commit_document(self, s: Session, corrections: Dict[str, Any], trace: Trace, lang: str) -> dict:
        doc = s.pending_doc or {"fields": []}
        n = 0
        for f in doc["fields"]:
            val = corrections.get(f["key"], f["value"])
            try:
                s.set_fact(f["key"], F.coerce(f["key"], val), "document")
                n += 1
            except (ValueError, TypeError, KeyError):
                continue
        s.pending_doc = None
        trace.add("Confirmation", f"{n} fields confirmed by the user and added to the profile")
        resp = self._run_pipeline(s, s.last_intent or "eligibility", s.last_schemes or list(self.kb.schemes),
                                  s.last_text or "eligibility", lang, trace, keep_streak=False)
        prefix = t("doc_saved", lang)
        resp["text"] = prefix + "\n" + resp["text"]
        resp["display"] = prefix + "\n" + resp["display"]
        resp["speech"] = prefix + " " + resp["speech"]
        return resp

    def _abstain_response(self, s: Session, trace: Trace, lang: str, agent: str, why: str,
                          scheme_id: Optional[str] = None, reason: str = "unsure") -> dict:
        trace.add(agent, f"abstaining: {why}", ok=False)
        ans = self.composer.compose_abstain(lang, scheme_id, reason)
        s.pending_question = None
        return self._respond(s, ans, trace, "abstain")

    def _run_pipeline(self, s: Session, intent: str, schemes: List[str], query: str, lang: str,
                      trace: Trace, keep_streak: bool = False) -> dict:
        s.last_intent, s.last_schemes = intent, list(schemes)
        max_attempt = settings.max_retrieval_retries
        ans: Optional[Answer] = None
        for attempt in range(max_attempt + 1):
            with trace.step("Retrieval") as st:
                retr = self.retrieval.run(query, schemes, attempt)
                st.summary = retr.summary()
            if attempt == 0 and not retr.in_domain and not schemes:
                return self._abstain_response(s, trace, lang, "Retrieval", "outside the knowledge base")

            skipped_any = False
            if intent == "eligibility":
                with trace.step("Eligibility") as st:
                    out = self.eligibility.run(schemes, s.facts, s.skipped)
                    st.summary = out.summary() + (f"; next question: {out.next_question}" if out.next_question else "")
                skipped_any = any(e.unresolved for e in out.evaluations.values())
                qkey = out.next_question if s.question_streak < MAX_FOLLOWUPS else None
                ans = self.composer.compose_eligibility(out, lang, skipped_any or (out.next_question and not qkey), qkey)
            elif intent in INFO_INTENTS:
                ans = self.composer.compose_info(intent, schemes, lang)
            else:                                                          # helpline
                ans = self.composer.compose_helpline(schemes, lang)
            ans.template_speech = ans.speech
            ans = self.composer.polish(ans, lang)

            with trace.step("Verifier") as st:
                rep = self.verifier.check(ans, retr, s.facts, s.skipped, lang, intent == "eligibility",
                                          attempts_left=attempt < max_attempt)
                st.summary = rep.summary()
                st.ok = rep.approved
                st.detail = {"issues": rep.issues}
            if not rep.approved and rep.action == "fallback_template":
                ans.text, ans.speech, ans.polished = ans.template_text, ans.template_speech, False
                with trace.step("Verifier") as st:
                    rep = self.verifier.check(ans, retr, s.facts, s.skipped, lang, intent == "eligibility",
                                              attempts_left=attempt < max_attempt)
                    st.summary = "re-check of template text: " + rep.summary()
                    st.ok = rep.approved
            if rep.approved:
                break
            if rep.action == "retry_retrieval":
                trace.add("Verifier → Retrieval", "answer rejected; re-retrieving with a wider, scheme-pinned search",
                          ok=False, kind="loop")
                continue
            return self._abstain_response(s, trace, lang, "Verifier", "answer could not be verified",
                                          schemes[0] if len(schemes) == 1 else None, "verifier")
        else:
            return self._abstain_response(s, trace, lang, "Verifier", "retries exhausted",
                                          schemes[0] if len(schemes) == 1 else None, "verifier")

        trace.add("Output guard", "every claim checked against retrieved guideline text; disclaimer attached", kind="safety")
        if ans.question_key:
            s.pending_question = ans.question_key
            s.question_streak = (s.question_streak + 1) if keep_streak else 1
        else:
            s.pending_question = None
        return self._respond(s, ans, trace, intent, retrieval_attempts=attempt + 1)

    # ------------------------------------------------------------------ response shaping
    def _profile(self, s: Session, lang: str) -> List[dict]:
        ol = out_lang(lang)
        return [{"key": k, "label": F.FACTS[k].label[ol], "display": F.display_value(k, v, ol),
                 "source": s.fact_source.get(k, "speech")} for k, v in s.facts.items()]

    def _respond(self, s: Session, ans: Answer, trace: Trace, intent: str, confirm: Optional[dict] = None,
                 extra: Optional[dict] = None, retrieval_attempts: int = 0) -> dict:
        ol = out_lang(s.lang)
        seen, sources = set(), []
        for c in ans.cards:
            for src in c.sources:
                if src["chunk_id"] not in seen:
                    seen.add(src["chunk_id"]); sources.append(src)
        return {
            "session_id": s.id, "lang": s.lang, "reply_lang": ol, "intent": intent,
            "text": ans.text, "display": ("\n".join(ans.tail) if ans.cards and ans.tail else ans.text),
            "speech": ans.speech or ans.text,
            "cards": [c.to_dict() for c in ans.cards],
            "question": ({"key": ans.question_key, "text": ans.question_text,
                          "choices": F.FACTS[ans.question_key].choices,
                          "kind": F.FACTS[ans.question_key].kind} if ans.question_key else None),
            "confirm": confirm,
            "helplines": ans.helplines, "abstained": ans.abstained, "polished": ans.polished,
            "sources": sources, "profile": self._profile(s, s.lang),
            "trace": trace.to_list(), "retrieval_attempts": retrieval_attempts,
            **(extra or {}),
        }
