"""Intake agent (slide 4): language, intent, and entities from what the person said.

Speech-to-text itself happens before this (Whisper on the server, or the browser's Web Speech API);
this agent turns the resulting text into structured intent + facts. Everything is rule-based so it is
fast, testable and works offline; an LLM may *add* facts when the rules find none (strictly validated)."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .. import facts as F
from ..i18n import normalize_digits
from ..knowledge import KnowledgeBase
from ..llm import llm

# ------------------------------------------------------------------ Kannada number words (1-99)
_UNITS = {1: ["ಒಂದು", "ೊಂದು"], 2: ["ಎರಡು", "ೆರಡು"], 3: ["ಮೂರು"], 4: ["ನಾಲ್ಕು"], 5: ["ಐದು", "ೈದು"],
          6: ["ಆರು", "ಾರು"], 7: ["ಏಳು", "ೇಳು"], 8: ["ಎಂಟು", "ೆಂಟು"], 9: ["ಒಂಬತ್ತು", "ೊಂಬತ್ತು"]}
_TENS = {10: "ಹತ್ತು", 20: "ಇಪ್ಪತ್ತು", 30: "ಮೂವತ್ತು", 40: "ನಲವತ್ತು", 50: "ಐವತ್ತು", 60: "ಅರವತ್ತು",
         70: "ಎಪ್ಪತ್ತು", 80: "ಎಂಬತ್ತು", 90: "ತೊಂಬತ್ತು"}
KN_NUMBER_WORDS: Dict[str, int] = {"ಸೊನ್ನೆ": 0}
for _n, _forms in _UNITS.items():
    KN_NUMBER_WORDS[_forms[0]] = _n
for _t, _w in _TENS.items():
    KN_NUMBER_WORDS[_w] = _t
    stem = _w[:-1]                       # drop final ು -> ...ತ್ತ
    for _n, _forms in _UNITS.items():
        for _f in _forms:
            KN_NUMBER_WORDS[stem + _f] = _t + _n
KN_NUMBER_WORDS.update({"ನೂರು": 100})
_NUM_WORD_RE = re.compile("|".join(sorted(map(re.escape, KN_NUMBER_WORDS), key=len, reverse=True)))


def kn_words_to_digits(text: str) -> str:
    return _NUM_WORD_RE.sub(lambda m: f" {KN_NUMBER_WORDS[m.group(0)]} ", text)


_EN_UNITS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
                                       "fifteen sixteen seventeen eighteen nineteen".split())}
_EN_TENS = {w: 10 * i for i, w in enumerate("_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()) if w != "_"}
_EN_NUM_RE = re.compile(r"\b(?:(" + "|".join(_EN_TENS) + r")(?:[\s-]+(" + "|".join(list(_EN_UNITS)[1:10]) + r"))?|(" +
                        "|".join(list(_EN_UNITS)[1:]) + r"))\b", re.I)


def en_words_to_digits(text: str) -> str:
    def rep(m: re.Match) -> str:
        if m.group(1):
            return str(_EN_TENS[m.group(1).lower()] + (_EN_UNITS[m.group(2).lower()] if m.group(2) else 0))
        return str(_EN_UNITS[m.group(3).lower()])
    return _EN_NUM_RE.sub(rep, text)


# ------------------------------------------------------------------ patterns
def _kn_ratio(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if "\u0c80" <= c <= "\u0cff") / len(letters)


YES = re.compile(r"\b(yes|yeah|yep|yup|ya|correct|right|sure|ok|okay|true)\b|ಹೌದು|ಹೌದ|ಸರಿ|ಹ್ಞೂ|ಹೂಂ|ಉಂಟು|ಇದೆ$", re.I)
NO = re.compile(r"\b(no|nope|nah|not|never|wrong|incorrect|false)\b|ಇಲ್ಲ|ಬೇಡ|ತಪ್ಪು|ಅಲ್ಲ", re.I)
SKIP = re.compile(r"\b(skip|don'?t know|do not know|not sure|no idea|unknown|pass)\b|ಗೊತ್ತಿಲ್ಲ|ಬಿಡಿ|ಗೊತ್ತಿಲ್ಲ|ಖಚಿತವಿಲ್ಲ|ತಿಳಿದಿಲ್ಲ", re.I)
NEG_NEAR = re.compile(r"\b(no|not|don'?t|doesn'?t|never|without|none|neither)\b|ಇಲ್ಲ|ಅಲ್ಲ|ಇಲ್ಲದ", re.I)

I_RATION_NONE = re.compile(r"(no|not have|don'?t have|without|never had)\W+(?:\w+\W+){0,2}ration|ration\s*card\s*(?:is\s*)?(?:not|none)|ಪಡಿತರ\s*ಚೀಟಿ\s*ಇಲ್ಲ|ರೇಷನ್\s*ಕಾರ್ಡ್\s*ಇಲ್ಲ", re.I)
I_BPL = re.compile(r"\bbpl\b|below poverty|ಬಿಪಿಎಲ್|ಬಡತನ ರೇಖೆ", re.I)
I_APL = re.compile(r"\bapl\b|above poverty|ಎಪಿಎಲ್", re.I)
I_AAY = re.compile(r"antyodaya|\baay\b|ಅಂತ್ಯೋದಯ", re.I)
I_FEMALE = re.compile(r"\b(woman|women|female|lady|housewife|girl)\b|ಮಹಿಳೆ|ಹೆಂಗಸು|ಹೆಣ್ಣು|ಗೃಹಿಣಿ", re.I)
I_MALE = re.compile(r"\b(man|male|gentleman|boy)\b|ಪುರುಷ|ಗಂಡಸು|ಗಂಡು", re.I)
I_PREG = re.compile(r"pregnan|expecting|lactating|breast\s?feeding|nursing mother|ಗರ್ಭಿಣಿ|ಗರ್ಭ|ಬಾಣಂತಿ|ಹಾಲುಣಿಸ", re.I)
I_KUTCHA = re.compile(r"kutcha|kachcha|mud house|thatch|\bhut\b|ಮಣ್ಣಿನ ಮನೆ|ಗುಡಿಸಲು|ಹುಲ್ಲಿನ ಮನೆ", re.I)
I_HEAD = re.compile(r"head of (?:the )?(?:family|household)|yajamani|ಯಜಮಾನಿ", re.I)
I_TAX = re.compile(r"income\s*tax|\bitr\b|\bgst\b|ಆದಾಯ ತೆರಿಗೆ|ಜಿಎಸ್‌?ಟಿ", re.I)
I_GOVT = re.compile(r"government (?:job|employee|servant|service)|govt\.? (?:job|employee)|pension|ಸರ್ಕಾರಿ (?:ನೌಕರ|ಉದ್ಯೋಗ)|ಪಿಂಚಣಿ", re.I)
I_LAND_NO = re.compile(r"landless|(?:no|don'?t have|do not have|without)\W+(?:\w+\W+){0,2}(?:land|farm)|(?:ಜಮೀನು|ಭೂಮಿ)\s*ಇಲ್ಲ", re.I)
I_LAND_YES = re.compile(r"(?:own|have|has|got)\W+(?:\w+\W+){0,3}(?:land|farm)|(?:ಜಮೀನು|ಭೂಮಿ)\s*ಇದೆ", re.I)
R_ACRES = re.compile(r"(\d+(?:\.\d+)?)\s*(?:acres?|ಎಕರೆ)", re.I)
R_GUNTAS = re.compile(r"(\d+(?:\.\d+)?)\s*(?:guntas?|ಗುಂಟೆ)", re.I)
R_AGE = [
    re.compile(r"(?:\bage\b|\baged\b|ವಯಸ್ಸು|ವಯಸ್ಸ)\D{0,8}(\d{1,3})", re.I),
    re.compile(r"\b(\d{1,3})\s*(?:years?|yrs?)\s*old\b", re.I),
    re.compile(r"\bi\s*(?:am|'m)\s*(\d{1,3})\b(?!\s*(?:acres?|rupees|rs))", re.I),
    re.compile(r"\b(1[2-9]|[2-9]\d|10\d|110)\s*(?:years?|yrs?)\b(?!\s*(?:ago|of|back|old child|in))", re.I),
    re.compile(r"(\d{1,3})\s*ವರ್ಷ(?!\s*(?:ದ|ಕ್ಕೆ)?\s*(?:ಮಗು|ಮಗ))", re.I),
]
I_INCOME_KW = re.compile(r"income|earn|salary|wage|ಆದಾಯ|ಸಂಬಳ|ಸಂಪಾದನೆ|ಗಳಿಕೆ", re.I)
R_AMOUNT = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(lakhs?|lacs?|ಲಕ್ಷ|thousand|ಸಾವಿರ|k\b|crore)?", re.I)
I_PER_MONTH = re.compile(r"per month|a month|monthly|/month|ತಿಂಗಳಿಗೆ|ತಿಂಗಳು|ಮಾಸಿಕ", re.I)
R_CHILDREN = re.compile(r"(\d+)\s*(?:children|kids|child|ಮಕ್ಕಳು|ಮಕ್ಕಳ|ಮಗು)", re.I)
I_FIRST_CHILD = re.compile(r"first (?:child|baby|pregnancy|delivery)|ಮೊದಲ(?:ನೇ)? (?:ಮಗು|ಹೆರಿಗೆ|ಗರ್ಭ)|no (?:other |more )?(?:children|kids)|ಮಕ್ಕಳಿಲ್ಲ|ಮಕ್ಕಳು ಇಲ್ಲ", re.I)
I_SECOND_CHILD = re.compile(r"second (?:child|baby)|one (?:child|kid) already|ಎರಡನೇ ಮಗು|ಒಂದು ಮಗು ಇದೆ", re.I)

INT_FORGET = re.compile(r"forget (?:me|everything|my)|delete my (?:data|details)|erase|clear my|ಅಳಿಸು|ಮರೆತುಬಿಡಿ|ಮರೆತು ಬಿಡಿ", re.I)
INT_HELPLINE = re.compile(r"helpline|phone number|toll.?free|contact number|\bcall\b|ಸಹಾಯವಾಣಿ|ಫೋನ್|ದೂರವಾಣಿ", re.I)
INT_DOCS = re.compile(r"document|papers?\b|\bbring\b|\bcarry\b|what (?:do )?i need|certificates? (?:needed|required)|ದಾಖಲೆ|ಕಾಗದ|ತರಬೇಕು|ಬೇಕಾದ ದಾಖಲೆ", re.I)
INT_APPLY = re.compile(r"\bapply\b|application|register|enrol|sign up|where (?:to|can i) (?:go|get)|ಅರ್ಜಿ|ನೋಂದ", re.I)
INT_BENEFIT = re.compile(r"how much|amount|\bbenefits?\b|what (?:do|will) i get|\bcover(?:age)?\b|rupees|ಎಷ್ಟು|ಸೌಲಭ್ಯ|ಮೊತ್ತ|ಎಷ್ಟು ಹಣ", re.I)
INT_ELIG = re.compile(r"eligib|qualif|entitled|\bcan i get\b|\bdo i get\b|\bam i\b|will i get|\bcan i\b|ಅರ್ಹ|ಸಿಗುತ್ತ|ಸಿಗಬಹುದ|ಸಿಗುವ|ಪಡೆಯ", re.I)
INT_LIST = re.compile(r"(?:what|which|list|available|all).{0,25}schemes|ಯಾವ ಯೋಜನೆ|ಯೋಜನೆಗಳ ಪಟ್ಟಿ|ಯೋಜನೆಗಳು ಯಾವುವು", re.I)
INT_GREET = re.compile(r"^\s*(?:hi|hello|hey|namaste|namaskara|ನಮಸ್ಕಾರ|ಹಲೋ)\b", re.I)


@dataclass
class IntakeResult:
    lang: str                                  # language of the utterance: kn | en
    intent: str                                # see classify()
    schemes: List[str] = field(default_factory=list)
    facts: Dict[str, Any] = field(default_factory=dict)
    yes_no: Optional[bool] = None
    skip: bool = False
    answered: Optional[str] = None             # fact key answered from pending_question
    not_understood: bool = False
    used_llm: bool = False

    def summary(self) -> str:
        bits = [f"lang={self.lang}", f"intent={self.intent}"]
        if self.schemes:
            bits.append("schemes=" + ",".join(self.schemes))
        if self.facts:
            bits.append("facts=" + ",".join(f"{k}={v}" for k, v in self.facts.items()))
        return "; ".join(bits)


# ------------------------------------------------------------------ helpers
def _norm(text: str) -> str:
    t = unicodedata.normalize("NFC", text)
    t = normalize_digits(t)
    t = en_words_to_digits(kn_words_to_digits(t))
    return re.sub(r"\s+", " ", t).strip()


def _negated(text: str, m: re.Match, window: int = 28) -> bool:
    before = text[max(0, m.start() - window): m.start()]
    after = text[m.end(): m.end() + window]
    # Kannada negation follows the noun; English negation precedes it.
    return bool(NEG_NEAR.search(before)) or bool(re.match(r"\W*(?:ಇಲ್ಲ|ಅಲ್ಲ|ಇಲ್ಲದ)", after))


def _amount(m: re.Match) -> float:
    n = float(m.group(1).replace(",", ""))
    unit = (m.group(2) or "").lower()
    if unit.startswith(("lakh", "lac")) or unit == "ಲಕ್ಷ":
        n *= 1e5
    elif unit in ("thousand", "ಸಾವಿರ", "k"):
        n *= 1e3
    elif unit == "crore":
        n *= 1e7
    return n


def extract_facts(text: str) -> Dict[str, Any]:
    """Rule-based entity extraction from a normalised utterance."""
    out: Dict[str, Any] = {}

    # ration card
    if I_RATION_NONE.search(text):
        out["ration_card"] = "none"
    elif I_AAY.search(text):
        out["ration_card"] = "aay"
    elif I_BPL.search(text):
        out["ration_card"] = "bpl"
    elif I_APL.search(text):
        out["ration_card"] = "apl"

    # gender
    if I_FEMALE.search(text) and not I_MALE.search(text):
        out["gender"] = "female"
    elif I_MALE.search(text) and not I_FEMALE.search(text):
        out["gender"] = "male"

    # pregnancy
    pm = I_PREG.search(text)
    if pm:
        out["pregnant_or_lactating"] = not _negated(text, pm)
        if out["pregnant_or_lactating"]:
            out.setdefault("gender", "female")

    # age
    for rx in R_AGE:
        m = rx.search(text)
        if m:
            try:
                out["age"] = F.coerce("age", m.group(1))
                break
            except ValueError:
                pass

    # land
    acres = R_ACRES.search(text)
    guntas = R_GUNTAS.search(text)
    if acres or guntas:
        total = (float(acres.group(1)) if acres else 0.0) + (float(guntas.group(1)) / 40.0 if guntas else 0.0)
        out["land_acres"] = round(total, 2)
        out["owns_land"] = True
    elif I_LAND_NO.search(text):
        out["owns_land"] = False
    elif I_LAND_YES.search(text):
        out["owns_land"] = True

    # income
    km = I_INCOME_KW.search(text)
    if km:
        cands = [m for m in R_AMOUNT.finditer(text)
                 if (m.group(2) or len(re.sub(r"\D", "", m.group(1))) >= 4)]
        after = [m for m in cands if m.start() >= km.end()]
        pick = (after or cands or [None])[0]
        if pick is not None:
            amt = _amount(pick)
            if I_PER_MONTH.search(text):
                amt *= 12
            if 0 < amt < 1e8:
                out["annual_income"] = amt

    # children
    if I_SECOND_CHILD.search(text):
        out["children_born_alive"] = 1
    elif I_FIRST_CHILD.search(text):
        out["children_born_alive"] = 0
    else:
        cm = R_CHILDREN.search(text)
        if cm and "pregnant_or_lactating" in out:
            try:
                out["children_born_alive"] = F.coerce("children_born_alive", cm.group(1))
            except ValueError:
                pass

    # simple booleans (negation-aware)
    for rx, key in ((I_KUTCHA, "kutcha_house"), (I_HEAD, "is_head_of_family"),
                    (I_GOVT, "govt_employee_or_pensioner"), (I_TAX, "income_tax_payer")):
        m = rx.search(text)
        if m:
            out[key] = not _negated(text, m)
    return out


def parse_answer(key: str, text: str) -> Optional[Any]:
    """Interpret a short reply as the answer to the question we just asked about `key`."""
    d = F.FACTS[key]
    t = text.strip()
    if d.kind == "bool":
        if SKIP.search(t):
            return None
        y, n = bool(YES.search(t)), bool(NO.search(t))
        if y and not n:
            return True
        if n and not y:
            return False
        # "ಇಲ್ಲ, ಹೌದು" style ambiguity: last word wins
        if y and n:
            last = max((m.start(), v) for rx, v in ((YES, True), (NO, False)) for m in rx.finditer(t))
            return last[1]
        return None
    if d.kind == "enum":
        ex = extract_facts(t)
        if key in ex:
            return ex[key]
        if key == "ration_card" and re.fullmatch(r"\W*(?:none|no|nothing|ಇಲ್ಲ)\W*", t, re.I):
            return "none"
        if key == "gender":
            if I_FEMALE.search(t):
                return "female"
            if I_MALE.search(t):
                return "male"
        return None
    # numeric
    m = R_AMOUNT.search(t)
    if m:
        v = _amount(m)
        if key == "annual_income" and I_PER_MONTH.search(t):
            v *= 12
        try:
            return F.coerce(key, v)
        except ValueError:
            return None
    if key == "children_born_alive" and (I_FIRST_CHILD.search(t) or re.search(r"\b(none|no|nil)\b|ಇಲ್ಲ", t, re.I)):
        return 0
    return None


# ------------------------------------------------------------------ main entry
class IntakeAgent:
    def __init__(self, kb: KnowledgeBase):
        self.kb = kb

    def detect_schemes(self, text_lc: str) -> List[str]:
        hits: Dict[str, int] = {}
        for sid, sch in self.kb.schemes.items():
            n = 0
            for a in sch.aliases.get("en", []):
                if re.search(r"(?<![a-z0-9])" + re.escape(a.lower()) + r"(?![a-z0-9])", text_lc):
                    n += 2 if " " in a or "-" in a else 1
            for a in sch.aliases.get("kn", []):
                if a in text_lc:
                    n += 2 if " " in a else 1
            if n:
                hits[sid] = n
        return [s for s, _ in sorted(hits.items(), key=lambda kv: -kv[1])]

    def classify(self, text: str, schemes: List[str], facts: Dict[str, Any]) -> str:
        if INT_FORGET.search(text):
            return "forget"
        if INT_HELPLINE.search(text):
            return "helpline"
        if INT_DOCS.search(text):
            return "documents"
        if INT_APPLY.search(text):
            return "apply"
        if INT_BENEFIT.search(text):
            return "benefits"
        if INT_ELIG.search(text):
            return "eligibility"
        if INT_LIST.search(text) and not facts:
            return "list_schemes"
        if INT_GREET.search(text) and not schemes and not facts:
            return "greeting"
        if schemes or facts:
            return "eligibility"
        return "other"

    def run(self, raw_text: str, lang_hint: str, pending_question: Optional[str],
            pending_doc: bool) -> IntakeResult:
        text = _norm(raw_text)
        lc = text.lower()
        lang = "kn" if _kn_ratio(text) > 0.3 else "en"
        if lang_hint == "kn" and _kn_ratio(text) > 0.1:
            lang = "kn"

        res = IntakeResult(lang=lang, intent="other")

        # 1) replies to something we just asked (document confirmation, or a follow-up question)
        short = len(lc.split()) <= 8
        if pending_doc and short:
            if SKIP.search(lc) is None and (YES.search(lc) or NO.search(lc)):
                y, n = bool(YES.search(lc)), bool(NO.search(lc))
                res.yes_no = True if (y and not n) else False if (n and not y) else None
                if res.yes_no is not None:
                    res.intent = "doc_yes" if res.yes_no else "doc_no"
                    return res
        if pending_question:
            if SKIP.search(lc) and short:
                res.skip, res.intent, res.answered = True, "answer", pending_question
                return res
            val = parse_answer(pending_question, lc)
            if val is not None:
                res.facts[pending_question] = val
                res.answered, res.intent = pending_question, "answer"
                # a reply may also carry extra facts ("yes, and I am 54")
                for k, v in extract_facts(lc).items():
                    res.facts.setdefault(k, v)
                res.schemes = self.detect_schemes(lc)
                return res

        # 2) a fresh request
        res.facts = extract_facts(lc)
        res.schemes = self.detect_schemes(lc)
        res.intent = self.classify(lc, res.schemes, res.facts)

        # 3) optional LLM assist, strictly validated, only when the rules found nothing
        if not res.facts and res.intent in ("eligibility", "other") and len(lc) > 15 and llm.available:
            data = llm.complete_json(
                "Extract facts about the speaker for Indian welfare-scheme eligibility from the text. "
                "Allowed keys: " + ", ".join(f"{k}({d.kind})" for k, d in F.FACTS.items()) +
                ". ration_card must be one of bpl, apl, aay, none; gender one of female, male. "
                "Include only facts explicitly stated. Never guess.", text)
            if isinstance(data, dict):
                for k, v in data.items():
                    if k in F.FACTS:
                        try:
                            res.facts[k] = F.coerce(k, v)
                            res.used_llm = True
                        except (ValueError, TypeError):
                            pass
                if res.facts and res.intent == "other":
                    res.intent = "eligibility"
        res.not_understood = (res.intent == "other")
        return res
