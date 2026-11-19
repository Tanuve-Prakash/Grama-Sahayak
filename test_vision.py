import shutil
from datetime import date
import pytest
from app.agents.vision import VisionAgent, parse_document_text
from .conftest import make_doc_image

TODAY = date(2026, 11, 18)


def fields(text):
    d, f, m = parse_document_text(text, 0.9, TODAY)
    return d, {x.key: x.value for x in f}, m


def test_aadhaar_masks_number_and_computes_age():
    d, f, m = fields("Government of India\nRamesh\nDOB: 12/05/1972\nMALE\n1234 5678 9012")
    assert d == "aadhaar" and f == {"age": 54, "gender": "male"}
    assert m == "XXXX XXXX 9012" and "1234" not in m


def test_female_not_confused_with_male():
    assert fields("UIDAI Aadhaar Year of Birth: 1980 Female 2345 6789 0123")[1]["gender"] == "female"


def test_karnataka_ration_card_codes():
    assert fields("Food and Civil Supplies Ration Card NPHH")[1] == {"ration_card": "apl"}     # NPHH checked before PHH
    assert fields("Ration Card PHH")[1] == {"ration_card": "bpl"}
    assert fields("Ration Card Antyodaya AAY")[1] == {"ration_card": "aay"}
    assert fields("ಪಡಿತರ ಚೀಟಿ ಬಿಪಿಎಲ್")[1] == {"ration_card": "bpl"}


def test_income_land_mcp():
    assert fields("INCOME CERTIFICATE Tahsildar annual income of the family is Rs. 90,000/-")[1] == {"annual_income": 90000.0}
    assert fields("RTC Pahani Survey No 45 Extent: 2-10 Cultivator")[1] == {"land_acres": 2.25, "owns_land": True}
    assert fields("Mother and Child Protection Card LMP EDD")[1]["pregnant_or_lactating"] is True


def test_low_ocr_confidence_lowers_field_confidence():
    _, hi, _ = parse_document_text("Ration Card PHH", 0.95)
    _, lo, _ = parse_document_text("Ration Card PHH", 0.40)
    assert lo[0].confidence < 0.6 <= hi[0].confidence


def test_unknown_document_yields_nothing():
    assert fields("hello world this is a shopping list")[1] == {}


@pytest.mark.skipif(not shutil.which("tesseract"), reason="tesseract not installed")
def test_real_ocr_on_tilted_jpeg():
    img = make_doc_image(["INCOME CERTIFICATE", "Tahsildar Office, Puttur", "annual income of the family", "is Rs. 90,000/- only"])
    r = VisionAgent().run(img)
    assert r.doc_type == "income_certificate"
    assert {f.key: f.value for f in r.fields}["annual_income"] == 90000.0


def test_garbage_bytes_do_not_crash():
    r = VisionAgent().run(b"not an image")
    assert r.fields == [] and r.warnings
