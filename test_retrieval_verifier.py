import pytest
from app.agents.composer import Answer, Card
from app.agents.retrieval import RetrievalAgent
from app.agents.verifier import VerifierAgent, numbers_in
from app.embeddings import get_embedder
from app.knowledge import load_kb

KB = load_kb()
R = RetrievalAgent(KB, get_embedder())
V = VerifierAgent(KB)


@pytest.mark.parametrize("q,scheme", [
    ("ನನಗೆ ಆರೋಗ್ಯ ವಿಮೆ ಸಿಗುತ್ತದೆಯೇ", "pmjay"), ("health insurance for hospital treatment", "pmjay"),
    ("ರೈತರಿಗೆ ಕಿಸಾನ್ ಹಣ", "pmkisan"), ("farmer income support 6000", "pmkisan"),
    ("ಗರ್ಭಿಣಿ ಮಹಿಳೆಗೆ ಸಹಾಯ", "pmmvy"), ("maternity benefit anganwadi", "pmmvy"),
    ("2000 rupees every month for women", "gruhalakshmi"), ("ಗೃಹ ಲಕ್ಷ್ಮಿ ಯೋಜನೆ", "gruhalakshmi"),
])
def test_retrieves_the_right_scheme_without_hints(q, scheme):
    assert R.run(q).hits[0].chunk.scheme_id == scheme


@pytest.mark.parametrize("q", ["how to get a passport", "what is the weather tomorrow", "ಹವಾಮಾನ ಹೇಗಿದೆ",
                               "cricket score today", "how to apply for driving licence", "tell me a joke"])
def test_out_of_domain_is_flagged(q):
    assert not R.run(q).in_domain


def test_retries_widen_and_pin():
    a0, a1, a2 = (R.run("eligibility", ["pmkisan"], i) for i in range(3))
    assert len(a1.hits) > len(a0.hits)
    assert {h.chunk.scheme_id for h in a2.hits} == {"pmkisan"} and a2.pinned == ["pmkisan"]


def _answer(text, cites, verdict="ELIGIBLE"):
    c = Card("pmjay", "Ayushman Bharat PM-JAY (Arogya Karnataka)", verdict, "You are eligible", cited_chunks=cites)
    return Answer(lang="en", text=text, speech=text, cards=[c])


DISC = "This is guidance, not a final decision. The office decides."
FULL = R.run("health insurance", ["pmjay"], 2)
OKTXT = f"Ayushman Bharat PM-JAY (Arogya Karnataka): You are eligible. Cover up to ₹5,00,000. {DISC}"


def chk(ans, facts=None, retr=FULL, attempts_left=True):
    return V.check(ans, retr, facts or {"ration_card": "bpl"}, set(), "en", True, attempts_left)


def test_good_answer_is_approved():
    assert chk(_answer(OKTXT, ["pmjay#eligibility"])).approved


def test_hallucinated_number_is_rejected():
    rep = chk(_answer(OKTXT.replace("5,00,000", "9,00,000"), ["pmjay#eligibility"]), attempts_left=False)
    assert not rep.approved and rep.action == "abstain" and rep.issues[0]["code"] == "unsupported_number"


def test_tampered_verdict_is_rejected():
    rep = chk(_answer(OKTXT, ["pmjay#eligibility"], verdict="NOT_ELIGIBLE"), attempts_left=False)
    assert "verdict_mismatch" in {i["code"] for i in rep.issues}


def test_uncited_section_triggers_retrieval_retry():
    narrow = R.run("hello", [], 0)
    narrow.hits = [h for h in narrow.hits if h.chunk.id != "pmjay#eligibility"]
    rep = chk(_answer(OKTXT, ["pmjay#eligibility"]), retr=narrow)
    assert rep.action == "retry_retrieval"


def test_overclaim_and_missing_disclaimer():
    codes = {i["code"] for i in chk(_answer("PM-JAY: You are eligible. Guaranteed 100% payout.", ["pmjay#eligibility"]), attempts_left=False).issues}
    assert {"overclaim", "no_disclaimer"} <= codes


def test_llm_rephrase_that_drops_verdict_falls_back_to_template():
    ans = _answer("Maybe you can try the hospital office, who knows.", ["pmjay#eligibility"])
    ans.polished = True
    rep = chk(ans)
    assert rep.action == "fallback_template" and "verdict_dropped" in {i["code"] for i in rep.issues}


def test_number_normalisation():
    assert numbers_in("₹5,00,000 and ೭೦ ವರ್ಷ and 2.0") == {"500000", "70", "2"}
