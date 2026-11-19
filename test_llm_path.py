"""The LLM is optional and untrusted: its wording is only used if the Verifier accepts it."""
import app.agents.composer as composer_mod


class FakeLLM:
    available = True
    name = "fake"

    def __init__(self, reply):
        self.reply = reply

    def complete(self, system, user, max_tokens=400, mask=True):
        return self.reply(user) if callable(self.reply) else self.reply


def _ask(orch, sessions, monkeypatch, reply):
    monkeypatch.setattr(composer_mod, "llm", FakeLLM(reply))
    s = sessions.create("en")
    return orch.handle_text(s, "health insurance, I have a BPL card")


def test_faithful_rephrase_is_accepted(orch, sessions, monkeypatch):
    r = _ask(orch, sessions, monkeypatch, lambda u: u + " Please go soon.")
    assert r["polished"] and "Please go soon." in r["text"]


def test_rephrase_with_invented_number_falls_back_to_template(orch, sessions, monkeypatch):
    r = _ask(orch, sessions, monkeypatch, lambda u: u.replace("5,00,000", "50,00,000"))
    assert not r["polished"] and "50,00,000" not in r["text"] and not r["abstained"]
    assert any("unsupported_number" in str(t.get("detail")) for t in r["trace"])


def test_rephrase_that_changes_the_verdict_is_rejected(orch, sessions, monkeypatch):
    r = _ask(orch, sessions, monkeypatch, "You may or may not get some health help. Ask around.")
    assert not r["polished"] and "You are eligible" in r["text"]


def test_overclaiming_rephrase_is_rejected(orch, sessions, monkeypatch):
    r = _ask(orch, sessions, monkeypatch, lambda u: u + " This is guaranteed, 100% sure.")
    assert not r["polished"] and "guaranteed" not in r["text"].lower()
