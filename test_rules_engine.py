import pytest
from app.knowledge import load_kb
from app.agents.rules_engine import evaluate

KB = load_kb()


def verdict(sid, facts, skipped=()):
    return evaluate(sid, KB.schemes[sid].rules_doc, facts, skipped).verdict


def test_unknown_is_not_no():
    assert verdict("pmkisan", {}) == "NEED_INFO"


def test_pmjay_any_of_short_circuits_unknowns():
    # one satisfied branch is enough even though other facts are unknown
    assert verdict("pmjay", {"ration_card": "bpl"}) == "ELIGIBLE"


@pytest.mark.parametrize("age,exp", [(69, "NEED_INFO"), (70, "ELIGIBLE")])
def test_pmjay_age_boundary(age, exp):
    assert verdict("pmjay", {"age": age}) == exp


@pytest.mark.parametrize("inc,exp", [(120000, "ELIGIBLE"), (120001, "NEED_INFO")])
def test_pmjay_income_boundary(inc, exp):
    assert verdict("pmjay", {"annual_income": inc}) == exp


def test_pmjay_all_branches_false_is_not_eligible():
    f = {"ration_card": "apl", "age": 40, "kutcha_house": False, "annual_income": 400000}
    assert verdict("pmjay", f) == "NOT_ELIGIBLE"


def test_pmkisan_exclusion_beats_requirement():
    assert verdict("pmkisan", {"owns_land": True, "income_tax_payer": True}) == "NOT_ELIGIBLE"
    assert verdict("pmkisan", {"owns_land": True, "income_tax_payer": False, "govt_employee_or_pensioner": False}) == "ELIGIBLE"
    assert verdict("pmkisan", {"owns_land": False}) == "NOT_ELIGIBLE"


def test_gruhalakshmi_requires_woman_head_with_card():
    ok = {"gender": "female", "is_head_of_family": True, "ration_card": "apl", "income_tax_payer": False}
    assert verdict("gruhalakshmi", ok) == "ELIGIBLE"
    assert verdict("gruhalakshmi", {**ok, "gender": "male"}) == "NOT_ELIGIBLE"
    assert verdict("gruhalakshmi", {**ok, "ration_card": "none"}) == "NOT_ELIGIBLE"


@pytest.mark.parametrize("age,exp", [(18, "NOT_ELIGIBLE"), (19, "ELIGIBLE")])
def test_pmmvy_age_boundary(age, exp):
    f = {"gender": "female", "pregnant_or_lactating": True, "age": age, "children_born_alive": 0, "govt_employee_or_pensioner": False}
    assert verdict("pmmvy", f) == exp


def test_pmmvy_second_child_only_if_girl_and_skip_gives_likely():
    base = {"gender": "female", "pregnant_or_lactating": True, "age": 25, "children_born_alive": 1, "govt_employee_or_pensioner": False}
    assert verdict("pmmvy", base) == "NEED_INFO"
    assert verdict("pmmvy", {**base, "second_child_is_girl": True}) == "ELIGIBLE"
    assert verdict("pmmvy", {**base, "second_child_is_girl": False}) == "NOT_ELIGIBLE"
    assert verdict("pmmvy", base, skipped=["second_child_is_girl"]) == "LIKELY"
    assert verdict("pmmvy", {**base, "children_born_alive": 2}) == "NOT_ELIGIBLE"


def test_every_rule_cites_an_existing_chunk():
    for s in KB.schemes.values():
        for r in s.rules_doc["rules"]:
            assert r["source"] in KB.chunks
