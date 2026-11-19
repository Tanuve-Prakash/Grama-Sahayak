"""The fact schema: every piece of information about a user that any scheme rule can need.

Having one schema is what lets the system (a) ask exactly one follow-up question by voice
when information is missing, (b) merge facts from speech, typed text and document photos,
and (c) continue with partial information instead of failing."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class FactDef:
    key: str
    kind: str                       # int | float | bool | enum
    label: Dict[str, str]
    question: Dict[str, str]
    choices: Optional[List[str]] = None
    priority: int = 50              # lower = asked earlier when several are missing
    sensitive: bool = False


FACTS: Dict[str, FactDef] = {f.key: f for f in [
    FactDef("ration_card", "enum",
            {"en": "Ration card", "kn": "ಪಡಿತರ ಚೀಟಿ"},
            {"en": "Which ration card do you have: BPL, APL, Antyodaya, or none?",
             "kn": "ನಿಮ್ಮ ಬಳಿ ಯಾವ ಪಡಿತರ ಚೀಟಿ ಇದೆ: ಬಿಪಿಎಲ್, ಎಪಿಎಲ್, ಅಂತ್ಯೋದಯ, ಅಥವಾ ಇಲ್ಲವೇ?"},
            ["bpl", "apl", "aay", "none"], 10),
    FactDef("gender", "enum",
            {"en": "Gender", "kn": "ಲಿಂಗ"},
            {"en": "Are you a woman or a man?", "kn": "ನೀವು ಮಹಿಳೆಯೇ ಅಥವಾ ಪುರುಷರೇ?"},
            ["female", "male"], 12),
    FactDef("age", "int",
            {"en": "Age", "kn": "ವಯಸ್ಸು"},
            {"en": "How old are you?", "kn": "ನಿಮ್ಮ ವಯಸ್ಸು ಎಷ್ಟು?"}, None, 14),
    FactDef("owns_land", "bool",
            {"en": "Owns farmland", "kn": "ಕೃಷಿ ಜಮೀನು ಇದೆ"},
            {"en": "Is farmland registered in your name or your family's name?",
             "kn": "ಕೃಷಿ ಜಮೀನು ನಿಮ್ಮ ಅಥವಾ ನಿಮ್ಮ ಕುಟುಂಬದ ಹೆಸರಿನಲ್ಲಿ ಇದೆಯೇ?"}, None, 20),
    FactDef("land_acres", "float",
            {"en": "Land (acres)", "kn": "ಜಮೀನು (ಎಕರೆ)"},
            {"en": "How many acres of land do you have?", "kn": "ನಿಮ್ಮ ಬಳಿ ಎಷ್ಟು ಎಕರೆ ಜಮೀನು ಇದೆ?"}, None, 90),
    FactDef("annual_income", "float",
            {"en": "Family income per year (₹)", "kn": "ಕುಟುಂಬದ ವಾರ್ಷಿಕ ಆದಾಯ (₹)"},
            {"en": "What is your family's income in a year, in rupees?",
             "kn": "ನಿಮ್ಮ ಕುಟುಂಬದ ಒಂದು ವರ್ಷದ ಆದಾಯ ಎಷ್ಟು ರೂಪಾಯಿ?"}, None, 30),
    FactDef("is_head_of_family", "bool",
            {"en": "Head of family on ration card", "kn": "ಪಡಿತರ ಚೀಟಿಯಲ್ಲಿ ಕುಟುಂಬದ ಯಜಮಾನಿ"},
            {"en": "Is your name shown as the head of the family on the ration card?",
             "kn": "ಪಡಿತರ ಚೀಟಿಯಲ್ಲಿ ಕುಟುಂಬದ ಯಜಮಾನಿ ಎಂದು ನಿಮ್ಮ ಹೆಸರು ಇದೆಯೇ?"}, None, 22),
    FactDef("income_tax_payer", "bool",
            {"en": "Income tax / GST payer in family", "kn": "ಕುಟುಂಬದಲ್ಲಿ ಆದಾಯ ತೆರಿಗೆ / ಜಿಎಸ್‌ಟಿ ಪಾವತಿದಾರರು"},
            {"en": "Does anyone in your family pay income tax or GST?",
             "kn": "ನಿಮ್ಮ ಕುಟುಂಬದಲ್ಲಿ ಯಾರಾದರೂ ಆದಾಯ ತೆರಿಗೆ ಅಥವಾ ಜಿಎಸ್‌ಟಿ ಕಟ್ಟುತ್ತಾರೆಯೇ?"}, None, 40),
    FactDef("govt_employee_or_pensioner", "bool",
            {"en": "Government employee / pensioner", "kn": "ಸರ್ಕಾರಿ ನೌಕರ / ಪಿಂಚಣಿದಾರ"},
            {"en": "Is anyone in your family a government employee or a pensioner?",
             "kn": "ನಿಮ್ಮ ಕುಟುಂಬದಲ್ಲಿ ಯಾರಾದರೂ ಸರ್ಕಾರಿ ನೌಕರರೋ ಅಥವಾ ಪಿಂಚಣಿದಾರರೋ ಇದ್ದಾರೆಯೇ?"}, None, 42),
    FactDef("kutcha_house", "bool",
            {"en": "Lives in a kutcha (mud / thatched) house", "kn": "ಮಣ್ಣಿನ / ಹುಲ್ಲಿನ ಮನೆಯಲ್ಲಿ ವಾಸ"},
            {"en": "Do you live in a house made of mud, thatch or other temporary material?",
             "kn": "ನೀವು ಮಣ್ಣು, ಹುಲ್ಲು ಅಥವಾ ತಾತ್ಕಾಲಿಕ ವಸ್ತುಗಳಿಂದ ಮಾಡಿದ ಮನೆಯಲ್ಲಿ ವಾಸಿಸುತ್ತೀರಾ?"}, None, 35),
    FactDef("pregnant_or_lactating", "bool",
            {"en": "Pregnant or breastfeeding", "kn": "ಗರ್ಭಿಣಿ ಅಥವಾ ಬಾಣಂತಿ"},
            {"en": "Are you pregnant or breastfeeding a baby?",
             "kn": "ನೀವು ಗರ್ಭಿಣಿಯೇ ಅಥವಾ ಮಗುವಿಗೆ ಹಾಲುಣಿಸುತ್ತಿದ್ದೀರಾ?"}, None, 24),
    FactDef("children_born_alive", "int",
            {"en": "Children born alive before this one", "kn": "ಈ ಮಗುವಿಗಿಂತ ಮೊದಲು ಜನಿಸಿದ ಮಕ್ಕಳು"},
            {"en": "How many living children do you already have, not counting this pregnancy?",
             "kn": "ಈ ಗರ್ಭಧಾರಣೆಯನ್ನು ಬಿಟ್ಟು, ನಿಮಗೆ ಈಗಾಗಲೇ ಎಷ್ಟು ಮಕ್ಕಳಿದ್ದಾರೆ?"}, None, 26),
    FactDef("second_child_is_girl", "bool",
            {"en": "Second child is a girl", "kn": "ಎರಡನೇ ಮಗು ಹೆಣ್ಣು"},
            {"en": "Is your second child a girl? Say skip if the baby is not born yet.",
             "kn": "ನಿಮ್ಮ ಎರಡನೇ ಮಗು ಹೆಣ್ಣೇ? ಮಗು ಇನ್ನೂ ಹುಟ್ಟಿಲ್ಲದಿದ್ದರೆ, ಬಿಡಿ ಎಂದು ಹೇಳಿ."}, None, 28),
]}

# facts that are only meaningful once another is known (avoid silly questions)
DEPENDS_ON = {"land_acres": ("owns_land", True)}


def coerce(key: str, value: Any) -> Any:
    """Coerce a raw value to the fact's type; raises ValueError on failure."""
    d = FACTS[key]
    if value is None:
        raise ValueError("none")
    if d.kind == "int":
        v = int(float(value))
        if not 0 <= v <= 120:
            raise ValueError("range")
        return v
    if d.kind == "float":
        v = float(value)
        if v < 0 or v > 1e9:
            raise ValueError("range")
        return v
    if d.kind == "bool":
        if isinstance(value, bool):
            return value
        s = str(value).strip().lower()
        if s in {"true", "yes", "1", "y"}:
            return True
        if s in {"false", "no", "0", "n"}:
            return False
        raise ValueError("bool")
    if d.kind == "enum":
        s = str(value).strip().lower()
        if s not in (d.choices or []):
            raise ValueError("enum")
        return s
    raise ValueError("kind")


def display_value(key: str, value: Any, lang: str = "en") -> str:
    d = FACTS[key]
    if d.kind == "bool":
        return ("ಹೌದು" if value else "ಇಲ್ಲ") if lang == "kn" else ("Yes" if value else "No")
    if d.kind == "enum":
        names = {
            "bpl": {"en": "BPL", "kn": "ಬಿಪಿಎಲ್"}, "apl": {"en": "APL", "kn": "ಎಪಿಎಲ್"},
            "aay": {"en": "Antyodaya", "kn": "ಅಂತ್ಯೋದಯ"}, "none": {"en": "None", "kn": "ಇಲ್ಲ"},
            "female": {"en": "Woman", "kn": "ಮಹಿಳೆ"}, "male": {"en": "Man", "kn": "ಪುರುಷ"},
        }
        return names.get(str(value), {}).get(lang, str(value))
    if key == "annual_income":
        return f"₹{int(value):,}"
    if d.kind == "float":
        return f"{value:g}"
    return str(value)
