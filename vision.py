"""Vision agent (slide 4): read a photographed ID or certificate and turn it into facts.

Privacy by design: the image is decoded, cleaned and OCR'd entirely in memory (Tesseract reads from
stdin; nothing is written to disk) and discarded. Only the *extracted fields* survive, and the Aadhaar
number is reduced to its last four digits before anything leaves this function.

Reading strategy:  vision-LLM (if configured)  ->  OCR (Tesseract / EasyOCR)  ->  rule-based parser.
Every field carries a confidence, and the UI always asks the user to confirm fields by voice before
the eligibility check runs (slide 6: "Reading low-quality document photos")."""
from __future__ import annotations

import io
import logging
import re
import shutil
import subprocess
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from .. import facts as F
from ..config import settings
from ..guards import mask_aadhaar_last4
from ..i18n import normalize_digits
from ..llm import llm

log = logging.getLogger("grama.vision")
LOW_CONF = 0.6


@dataclass
class Field_:
    key: str
    value: Any
    confidence: float
    source_doc: str

    def to_dict(self, lang: str = "en") -> dict:
        return {"key": self.key, "value": self.value, "confidence": round(self.confidence, 2),
                "label": F.FACTS[self.key].label.get(lang, self.key) if self.key in F.FACTS else self.key,
                "display": F.display_value(self.key, self.value, lang) if self.key in F.FACTS else str(self.value),
                "low_confidence": self.confidence < LOW_CONF}


@dataclass
class VisionResult:
    doc_type: str = "unknown"
    fields: List[Field_] = field(default_factory=list)
    aadhaar_masked: Optional[str] = None
    engine: str = "none"
    ocr_confidence: Optional[float] = None
    text_chars: int = 0
    warnings: List[str] = field(default_factory=list)

    def summary(self) -> str:
        return (f"doc={self.doc_type}; engine={self.engine}; fields="
                + (",".join(f"{f.key}={f.value}" for f in self.fields) or "none"))


# ======================================================================= image handling
def preprocess(image: bytes) -> "Any":
    """Decode safely, fix orientation, strip EXIF (by re-encoding), normalise size and contrast."""
    from PIL import Image, ImageOps
    Image.MAX_IMAGE_PIXELS = 40_000_000                       # decompression-bomb guard
    im = Image.open(io.BytesIO(image))
    im.load()
    im = ImageOps.exif_transpose(im)
    im = im.convert("L")
    w, h = im.size
    if max(w, h) > 2200:
        s = 2200 / max(w, h)
        im = im.resize((int(w * s), int(h * s)))
    elif max(w, h) < 1100:                                    # tiny photos OCR better when upscaled
        s = 1100 / max(w, h)
        im = im.resize((int(w * s), int(h * s)))
    return ImageOps.autocontrast(im, cutoff=1)


def _png_bytes(im) -> bytes:
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


# ======================================================================= OCR engines
@lru_cache(maxsize=1)
def _tesseract_langs() -> List[str]:
    exe = shutil.which("tesseract")
    if not exe:
        return []
    try:
        out = subprocess.run([exe, "--list-langs"], capture_output=True, text=True, timeout=10).stdout
        return [l.strip() for l in out.splitlines()[1:] if l.strip()]
    except Exception:
        return []


def _ocr_tesseract(im) -> Tuple[str, Optional[float]]:
    exe = shutil.which("tesseract")
    avail = _tesseract_langs()
    want = settings.tesseract_langs
    if want == "auto":
        want = "+".join(l for l in ("eng", "kan") if l in avail) or "eng"
    p = subprocess.run([exe, "stdin", "stdout", "-l", want, "--psm", "6", "tsv"],
                       input=_png_bytes(im), capture_output=True, timeout=45)
    words, confs = [], []
    cur_line, line_words = None, []
    lines: List[str] = []
    for row in p.stdout.decode("utf-8", "replace").splitlines()[1:]:
        c = row.split("\t")
        if len(c) < 12:
            continue
        txt, conf = c[11].strip(), float(c[10])
        key = (c[2], c[3], c[4])                               # block, paragraph, line
        if key != cur_line and line_words:
            lines.append(" ".join(line_words)); line_words = []
        cur_line = key
        if txt:
            line_words.append(txt)
            if conf >= 0:
                confs.append(conf)
    if line_words:
        lines.append(" ".join(line_words))
    return "\n".join(lines), (sum(confs) / len(confs) / 100.0 if confs else None)


@lru_cache(maxsize=1)
def _easyocr_reader():
    import easyocr  # optional, heavy
    return easyocr.Reader(["kn", "en"], gpu=False)


def _ocr_easyocr(im) -> Tuple[str, Optional[float]]:
    import numpy as np
    res = _easyocr_reader().readtext(np.array(im), detail=1, paragraph=False)
    text = "\n".join(r[1] for r in res)
    confs = [float(r[2]) for r in res]
    return text, (sum(confs) / len(confs) if confs else None)


def available_engine() -> str:
    pref = settings.ocr_engine
    if pref == "none":
        return "none"
    if pref in ("auto", "easyocr"):
        try:
            import easyocr  # noqa: F401
            return "easyocr"
        except Exception:
            if pref == "easyocr":
                return "none"
    if pref in ("auto", "tesseract") and shutil.which("tesseract"):
        return "tesseract"
    return "none"


# ======================================================================= document parsing
DOC_KEYWORDS: Dict[str, List[str]] = {
    "ration_card": ["ration card", "ration", "ಪಡಿತರ", "ರೇಷನ್", "food and civil", "ಆಹಾರ ಮತ್ತು ನಾಗರಿಕ", "antyodaya",
                    "priority household", "nphh", "phh", "bpl", "apl", "fair price"],
    "aadhaar": ["aadhaar", "aadhar", "ಆಧಾರ್", "uidai", "unique identification", "year of birth", "dob", "enrolment"],
    "income_certificate": ["income certificate", "annual income", "family income", "ಆದಾಯ ಪ್ರಮಾಣ", "tahsildar", "tahasildar",
                           "ತಹಶೀಲ್ದಾರ್", "ವಾರ್ಷಿಕ ಆದಾಯ"],
    "land_record": ["rtc", "pahani", "ಪಹಣಿ", "survey no", "ಸರ್ವೆ ನಂ", "hissa", "ಹಿಸ್ಸಾ", "khata", "extent", "cultivator", "ಸಾಗುವಳಿ", "ಎಕರೆ", "guntas", "ಗುಂಟೆ"],
    "mcp_card": ["mother and child protection", "mcp card", "mcp", "antenatal", "edd", "lmp", "ಎಂಸಿಪಿ", "ತಾಯಿ ಮತ್ತು ಮಗು", "ತಾಯಿ ಕಾರ್ಡ್"],
}


def classify_document(text: str) -> Tuple[str, Dict[str, int]]:
    lc = text.lower()
    scores = {d: sum(1 for k in kws if re.search(r"(?<![a-z])" + re.escape(k) + r"(?![a-z])", lc) if k.isascii())
                 + sum(1 for k in kws if not k.isascii() and k in lc)
              for d, kws in DOC_KEYWORDS.items()}
    if re.search(r"(?<!\d)\d{4}\s?\d{4}\s?\d{4}(?!\d)", text):
        scores["aadhaar"] += 2
    best = max(scores, key=lambda d: scores[d])
    return (best if scores[best] >= 1 else "unknown"), scores


def _age_from(day: Optional[int], month: Optional[int], year: int, today: Optional[date] = None) -> Optional[int]:
    today = today or date.today()
    if not 1900 <= year <= today.year:
        return None
    age = today.year - year
    if day and month and (today.month, today.day) < (month, day):
        age -= 1
    return age if 0 <= age <= 120 else None


def parse_document_text(text: str, ocr_conf: Optional[float] = None, today: Optional[date] = None
                        ) -> Tuple[str, List[Field_], Optional[str]]:
    """Rule-based field extraction from OCR text. Returns (doc_type, fields, masked_aadhaar)."""
    text = normalize_digits(unicodedata.normalize("NFC", text))
    doc, _ = classify_document(text)
    q = 1.0 if ocr_conf is None else max(0.35, min(1.0, ocr_conf))       # OCR quality multiplier
    fields: List[Field_] = []
    masked: Optional[str] = None

    def add(key: str, value: Any, base: float) -> None:
        try:
            fields.append(Field_(key, F.coerce(key, value), round(base * q, 3), doc))
        except (ValueError, TypeError):
            pass

    if doc == "ration_card":
        if re.search(r"antyodaya|\bAAY\b|ಅಂತ್ಯೋದಯ", text, re.I):
            add("ration_card", "aay", 0.9)
        elif re.search(r"\bNPHH\b|non[- ]?priority", text, re.I):
            add("ration_card", "apl", 0.9)
        elif re.search(r"\bPHH\b|priority household|\bBPL\b|ಬಿಪಿಎಲ್", text, re.I):
            add("ration_card", "bpl", 0.9)
        elif re.search(r"\bAPL\b|ಎಪಿಎಲ್", text, re.I):
            add("ration_card", "apl", 0.9)

    if doc == "aadhaar":
        m = re.search(r"(?<!\d)(\d{4})\s?(\d{4})\s?(\d{4})(?!\d)", text)
        if m:
            masked = mask_aadhaar_last4(m.group(0))
        age = None
        dob = re.search(r"(?:dob|date of birth|d\.o\.b|ಜನ್ಮ ದಿನಾಂಕ)\W{0,6}(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})", text, re.I)
        yob = re.search(r"(?:year of birth|yob)\W{0,6}(\d{4})", text, re.I)
        anydate = re.search(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.]((?:19|20)\d{2})\b", text)
        if dob:
            age, base = _age_from(int(dob.group(1)), int(dob.group(2)), int(dob.group(3)), today), 0.9
        elif yob:
            age, base = _age_from(None, None, int(yob.group(1)), today), 0.8
        elif anydate:
            age, base = _age_from(int(anydate.group(1)), int(anydate.group(2)), int(anydate.group(3)), today), 0.65
        if age is not None:
            add("age", age, base)
        fem = re.search(r"\bfemale\b|ಮಹಿಳೆ|ಹೆಣ್ಣು|स्त्री|महिला", text, re.I)
        mal = re.search(r"(?<!fe)\bmale\b|ಪುರುಷ|ಗಂಡು|पुरुष", text, re.I)
        if fem and not mal:
            add("gender", "female", 0.9)
        elif mal and not fem:
            add("gender", "male", 0.9)

    if doc == "income_certificate":
        m = re.search(r"income[^\d₹]{0,60}(?:rs\.?|₹|inr|rupees)?\s*([\d,]{4,})(?:\s*/-)?", text, re.I | re.S) \
            or re.search(r"(?:rs\.?|₹)\s*([\d,]{4,})", text, re.I)
        if m:
            add("annual_income", float(m.group(1).replace(",", "")), 0.85)

    if doc == "land_record":
        acres = re.search(r"(\d+(?:\.\d+)?)\s*(?:acres?|ಎಕರೆ)", text, re.I)
        ext = re.search(r"extent\W{0,8}(\d+)\s*[-–.]\s*(\d{1,2})\b", text, re.I)    # acres-guntas e.g. 2-10
        guntas = re.search(r"(\d+)\s*(?:guntas?|ಗುಂಟೆ)", text, re.I)
        if ext:
            add("land_acres", round(int(ext.group(1)) + int(ext.group(2)) / 40.0, 2), 0.8)
            add("owns_land", True, 0.8)
        elif acres:
            total = float(acres.group(1)) + (int(guntas.group(1)) / 40.0 if guntas else 0)
            add("land_acres", round(total, 2), 0.85)
            add("owns_land", True, 0.85)
        elif re.search(r"survey no|ಸರ್ವೆ ನಂ|pahani|rtc|ಪಹಣಿ", text, re.I):
            add("owns_land", True, 0.6)          # a land record exists, extent unreadable

    if doc == "mcp_card":
        add("pregnant_or_lactating", True, 0.8)
        add("gender", "female", 0.85)
    return doc, fields, masked


# ======================================================================= agent
class VisionAgent:
    LLM_PROMPT = (
        "This is a photo of an Indian ID or certificate. Return ONLY JSON: "
        '{"doc_type": "ration_card|aadhaar|income_certificate|land_record|mcp_card|unknown", '
        '"ration_card": "bpl|apl|aay|null", "age": int|null, "gender": "female|male|null", '
        '"annual_income": number|null, "land_acres": number|null, "aadhaar_last4": "string|null"}. '
        "Karnataka cards: PHH means bpl, NPHH means apl. Use null for anything not clearly visible. Never guess.")

    def run(self, image: bytes, mime: str = "image/jpeg") -> VisionResult:
        res = VisionResult()
        # 1) vision LLM, if configured
        data = llm.vision_extract(image, mime, self.LLM_PROMPT)
        if isinstance(data, dict) and data.get("doc_type") not in (None, "unknown"):
            res.engine, res.doc_type = f"llm:{llm.name}", str(data.get("doc_type"))
            for key in ("ration_card", "age", "gender", "annual_income", "land_acres"):
                if data.get(key) not in (None, "null"):
                    try:
                        res.fields.append(Field_(key, F.coerce(key, data[key]), 0.85, res.doc_type))
                    except (ValueError, TypeError):
                        pass
            if res.doc_type == "land_record" and any(f.key == "land_acres" for f in res.fields):
                res.fields.append(Field_("owns_land", True, 0.8, res.doc_type))
            if data.get("aadhaar_last4"):
                res.aadhaar_masked = "XXXX XXXX " + re.sub(r"\D", "", str(data["aadhaar_last4"]))[-4:]
            if res.fields:
                return res

        # 2) OCR + rules
        engine = available_engine()
        res.engine = engine
        if engine == "none":
            res.warnings.append("no_ocr_engine")
            return res
        try:
            im = preprocess(image)
        except Exception as e:
            log.info("image decode failed: %s", type(e).__name__)
            res.warnings.append("bad_image")
            return res
        try:
            text, conf = _ocr_easyocr(im) if engine == "easyocr" else _ocr_tesseract(im)
        except Exception as e:
            log.warning("OCR failed: %s", type(e).__name__)
            res.warnings.append("ocr_failed")
            return res
        res.ocr_confidence, res.text_chars = conf, len(text)
        res.doc_type, res.fields, res.aadhaar_masked = parse_document_text(text, conf)
        if conf is not None and conf < 0.55:
            res.warnings.append("low_ocr_confidence")
        return res
