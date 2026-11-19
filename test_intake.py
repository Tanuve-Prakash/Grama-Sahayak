import pytest
from app.agents.intake import IntakeAgent, kn_words_to_digits
from app.knowledge import load_kb

A = IntakeAgent(load_kb())
run = lambda t, pq=None, pd=False, lang="kn": A.run(t, lang, pq, pd)


@pytest.mark.parametrize("text,facts,scheme", [
    ("Am I eligible for health insurance? I am 54, a woman, with a BPL card", {"age": 54, "gender": "female", "ration_card": "bpl"}, "pmjay"),
    ("ನಾನು ಮಹಿಳೆ, ನನಗೆ 54 ವರ್ಷ, ಬಿಪಿಎಲ್ ಕಾರ್ಡ್ ಇದೆ. ಆರೋಗ್ಯ ವಿಮೆ ಸಿಗುತ್ತದೆಯೇ?", {"age": 54, "gender": "female", "ration_card": "bpl"}, "pmjay"),
    ("ನನಗೆ ಐವತ್ತನಾಲ್ಕು ವರ್ಷ", {"age": 54}, None),                                  # Kannada number word
    ("ನನ್ನ ಬಳಿ ೨ ಎಕರೆ ಜಮೀನು ಇದೆ. ಪಿಎಂ ಕಿಸಾನ್", {"land_acres": 2.0, "owns_land": True}, "pmkisan"),   # Kannada digits
    ("I have 2 acres and 20 guntas, family income 90,000 per year", {"land_acres": 2.5, "annual_income": 90000}, None),
    ("my income is 8000 per month", {"annual_income": 96000}, None),
    ("income about 1.5 lakh", {"annual_income": 150000}, None),
    ("I am pregnant, first child, 24 years old", {"pregnant_or_lactating": True, "children_born_alive": 0, "age": 24, "gender": "female"}, "pmmvy"),
    ("I have no land", {"owns_land": False}, None),
    ("I do not have a ration card", {"ration_card": "none"}, None),
    ("we live in a mud house", {"kutcha_house": True}, None),
    ("I am fifty four years old", {"age": 54}, None),
])
def test_extraction(text, facts, scheme):
    r = run(text)
    for k, v in facts.items():
        assert r.facts.get(k) == v, (k, r.facts)
    if scheme:
        assert scheme in r.schemes


@pytest.mark.parametrize("text,intent", [
    ("which documents do I need for gruha lakshmi", "documents"),
    ("ಗೃಹ ಲಕ್ಷ್ಮಿಗೆ ಯಾವ ದಾಖಲೆ ಬೇಕು", "documents"),
    ("how do I apply for PM-KISAN", "apply"),
    ("how much money will I get from PM-KISAN", "benefits"),
    ("PM-KISAN helpline number", "helpline"),
    ("can I get Gruha Lakshmi", "eligibility"),
    ("forget everything about me", "forget"),
    ("how to get a passport", "other"),
    ("what is the weather tomorrow", "other"),
])
def test_intent(text, intent):
    assert run(text).intent == intent


@pytest.mark.parametrize("key,text,val", [
    ("income_tax_payer", "ಹೌದು", True), ("income_tax_payer", "ಇಲ್ಲ", False), ("income_tax_payer", "no", False),
    ("ration_card", "ಬಿಪಿಎಲ್", "bpl"), ("ration_card", "antyodaya", "aay"), ("age", "54", 54), ("age", "ಐವತ್ತು", 50),
    ("owns_land", "yes I do", True),
])
def test_answers(key, text, val):
    r = run(text, pq=key)
    assert r.intent == "answer" and r.facts[key] == val


def test_skip_and_confirmation_replies():
    assert run("ಗೊತ್ತಿಲ್ಲ", pq="income_tax_payer").skip
    assert run("don't know", pq="age").skip
    assert run("ಹೌದು", pd=True).intent == "doc_yes"
    assert run("no", pd=True).intent == "doc_no"


def test_negation_is_respected():
    assert run("no one in my family pays income tax").facts.get("income_tax_payer") is False
    assert run("I am not pregnant").facts.get("pregnant_or_lactating") is False


def test_number_words():
    assert kn_words_to_digits("ಅರವತ್ತೈದು").strip() == "65"
