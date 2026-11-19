import io
import time
import pytest
from app.guards import guard_input, mask_pii
from app.session import SessionStore
from .conftest import make_doc_image


def new(client, lang="en"):
    return client.post("/api/session", json={"lang": lang}).json()["session_id"]


def test_health_and_schemes(client):
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and len(h["schemes"]) == 4 and "ocr" in h["capabilities"]


def test_ask_roundtrip_and_response_shape(client):
    sid = new(client)
    r = client.post("/api/ask", json={"session_id": sid, "text": "health insurance, I have a BPL card"}).json()
    assert r["cards"][0]["verdict"] == "ELIGIBLE"
    assert {"text", "display", "speech", "cards", "profile", "trace", "sources", "helplines"} <= set(r)
    assert "ration_card" in {p["key"] for p in r["profile"]}


def test_expired_session_is_404(client):
    assert client.post("/api/ask", json={"session_id": "nope", "text": "hi"}).status_code == 404


def test_input_validation(client):
    sid = new(client)
    assert client.post("/api/ask", json={"session_id": sid, "text": "x" * 3000}).status_code == 422
    assert client.post("/api/session", json={"lang": "fr"}).status_code == 422


def test_upload_validation(client):
    sid = new(client)
    bad = client.post("/api/vision", files={"image": ("a.jpg", b"GIF89a....", "image/jpeg")}, data={"session_id": sid})
    assert bad.status_code == 415
    big = client.post("/api/vision", files={"image": ("a.jpg", b"\xff\xd8\xff" + b"0" * (7 * 1024 * 1024), "image/jpeg")}, data={"session_id": sid})
    assert big.status_code == 413


def test_vision_confirm_flow_over_http(client):
    sid = new(client)
    img = make_doc_image(["INCOME CERTIFICATE", "Tahsildar Office", "annual income of the family", "is Rs. 90,000/- only"])
    r = client.post("/api/vision", files={"image": ("a.jpg", img, "image/jpeg")}, data={"session_id": sid, "lang": "en"}).json()
    assert r["confirm"] and r["profile"] == []
    r2 = client.post("/api/confirm", json={"session_id": sid, "accept": True}).json()
    assert any(p["key"] == "annual_income" for p in r2["profile"])


def test_forget_and_delete_session(client):
    sid = new(client)
    client.post("/api/ask", json={"session_id": sid, "text": "I am 54, BPL card, health insurance"})
    assert client.post("/api/forget", json={"session_id": sid}).json()["profile"] == []
    client.delete(f"/api/session/{sid}")
    assert client.post("/api/ask", json={"session_id": sid, "text": "hi"}).status_code == 404


def test_security_headers_and_no_store(client):
    r = client.get("/api/health")
    assert r.headers["cache-control"] == "no-store" and r.headers["x-frame-options"] == "DENY"
    assert "microphone=(self)" in r.headers["permissions-policy"]


def test_pwa_assets_are_served(client):
    for p in ["/", "/app.js", "/styles.css", "/manifest.webmanifest", "/sw.js", "/icons/icon.svg"]:
        assert client.get(p).status_code == 200, p


def test_optional_speech_endpoints_degrade_gracefully(client):
    assert client.post("/api/tts", json={"text": "hi", "lang": "en"}).status_code in (200, 501)
    r = client.post("/api/transcribe", files={"audio": ("a.webm", b"123", "audio/webm")}, data={"lang": "kn"})
    assert r.status_code in (200, 501)


# ------------------------------------------------------------------ privacy
def test_pii_masking():
    assert mask_pii("aadhaar 1234 5678 9012, mobile 9876543210") == "aadhaar XXXX XXXX 9012, mobile XXXXXX3210"


def test_guard_strips_control_chars_and_truncates():
    g = guard_input("hi\u202e\x00 there" + "a" * 1000)
    assert g.ok and "\x00" not in g.text and "\u202e" not in g.text and "truncated" in g.flags


def test_session_ttl_expires_and_nothing_is_persisted(tmp_path):
    st = SessionStore(ttl_s=1)
    s = st.create("en"); s.set_fact("age", 50, "speech")
    time.sleep(1.2)
    assert st.get(s.id) is None and len(st) == 0


def test_aadhaar_number_never_enters_session(orch, sessions):
    s = sessions.create("en")
    img = make_doc_image(["Government of India", "Ramesh", "DOB: 12/05/1972", "MALE", "1234 5678 9012", "Aadhaar"])
    orch.handle_image(s, img, "image/jpeg", "en")
    blob = repr(s.__dict__)
    assert "1234 5678" not in blob and "123456789012" not in blob


def test_last_text_is_pii_masked(orch, sessions):
    s = sessions.create("en")
    orch.handle_text(s, "my aadhaar is 1234 5678 9012, health insurance")
    assert "1234 5678" not in s.last_text
