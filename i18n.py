"""All user-facing text in English and Kannada. Tulu ("tcy") users are answered in Kannada
(there is no mature Tulu ASR/TTS yet; see README 'Roadblocks')."""
from __future__ import annotations

from typing import Any

SUPPORTED = ("kn", "en", "tcy")


def out_lang(lang: str) -> str:
    """Language used for *output*. Tulu falls back to Kannada."""
    return "kn" if lang in ("kn", "tcy") else "en"


T = {
    "greeting": {
        "en": "Namaste! Ask me about a health or welfare scheme. You can speak, type, or show a document.",
        "kn": "ನಮಸ್ಕಾರ! ಆರೋಗ್ಯ ಅಥವಾ ಕಲ್ಯಾಣ ಯೋಜನೆಗಳ ಬಗ್ಗೆ ಕೇಳಿ. ಮಾತನಾಡಿ, ಟೈಪ್ ಮಾಡಿ ಅಥವಾ ದಾಖಲೆಯ ಫೋಟೋ ತೋರಿಸಿ.",
    },
    "verdict_ELIGIBLE": {"en": "You are eligible", "kn": "ನೀವು ಅರ್ಹರಾಗಿದ್ದೀರಿ"},
    "verdict_LIKELY": {"en": "Likely eligible", "kn": "ನೀವು ಬಹುಶಃ ಅರ್ಹರು"},
    "verdict_NOT_ELIGIBLE": {"en": "Not eligible", "kn": "ನೀವು ಅರ್ಹರಲ್ಲ"},
    "verdict_NEED_INFO": {"en": "I need a little more information", "kn": "ಇನ್ನಷ್ಟು ಮಾಹಿತಿ ಬೇಕು"},
    "benefit_is": {"en": "Benefit", "kn": "ಸೌಲಭ್ಯ"},
    "reason_ok": {"en": "Why", "kn": "ಕಾರಣ"},
    "reason_fail": {"en": "Reason", "kn": "ಕಾರಣ"},
    "bring": {"en": "Bring", "kn": "ತರಬೇಕಾದವು"},
    "to_confirm": {"en": "Please confirm at the office", "kn": "ಕಚೇರಿಯಲ್ಲಿ ಖಚಿತಪಡಿಸಿಕೊಳ್ಳಿ"},
    "source": {"en": "Source", "kn": "ಮೂಲ"},
    "disclaimer": {
        "en": "This is guidance, not a final decision. The office decides.",
        "kn": "ಇದು ಮಾರ್ಗದರ್ಶನ ಮಾತ್ರ, ಅಂತಿಮ ತೀರ್ಮಾನವಲ್ಲ. ಅಂತಿಮ ನಿರ್ಧಾರ ಕಚೇರಿಯದು.",
    },
    "ask_missing_prefix": {"en": "One question:", "kn": "ಒಂದು ಪ್ರಶ್ನೆ:"},
    "skipped_note": {
        "en": "I could not check everything, so please verify the remaining points at the office.",
        "kn": "ಎಲ್ಲವನ್ನೂ ಪರಿಶೀಲಿಸಲು ಆಗಲಿಲ್ಲ, ಆದ್ದರಿಂದ ಉಳಿದ ಅಂಶಗಳನ್ನು ಕಚೇರಿಯಲ್ಲಿ ಪರಿಶೀಲಿಸಿ.",
    },
    "unsure": {
        "en": "I am not sure about this, and I do not want to guess. Please ask {office}, or call {helpline}.",
        "kn": "ಈ ಬಗ್ಗೆ ನನಗೆ ಖಚಿತವಿಲ್ಲ, ಊಹೆ ಮಾಡಲು ಇಷ್ಟವಿಲ್ಲ. ದಯವಿಟ್ಟು {office} ಅನ್ನು ಕೇಳಿ, ಅಥವಾ {helpline} ಗೆ ಕರೆ ಮಾಡಿ.",
    },
    "unsure_verifier": {
        "en": "I could not confirm this answer from the scheme documents, so I will not give it. Please ask {office}, or call {helpline}.",
        "kn": "ಈ ಉತ್ತರವನ್ನು ಯೋಜನೆಯ ದಾಖಲೆಗಳಿಂದ ಖಚಿತಪಡಿಸಲು ಆಗಲಿಲ್ಲ, ಆದ್ದರಿಂದ ನೀಡುವುದಿಲ್ಲ. ದಯವಿಟ್ಟು {office} ಅನ್ನು ಕೇಳಿ, ಅಥವಾ {helpline} ಗೆ ಕರೆ ಮಾಡಿ.",
    },
    "which_schemes": {
        "en": "I can help with these schemes:", "kn": "ನಾನು ಈ ಯೋಜನೆಗಳ ಬಗ್ಗೆ ಸಹಾಯ ಮಾಡಬಲ್ಲೆ:",
    },
    "helpline_intro": {"en": "You can call", "kn": "ನೀವು ಕರೆ ಮಾಡಬಹುದು"},
    "apply_intro": {"en": "How to apply", "kn": "ಅರ್ಜಿ ಹೇಗೆ"},
    "benefit_only": {"en": "Benefit", "kn": "ಸೌಲಭ್ಯ"},
    "doc_read": {"en": "I read this from your {doc}:", "kn": "ನಿಮ್ಮ {doc} ನಿಂದ ನಾನು ಓದಿದ್ದು:"},
    "doc_confirm": {"en": "Is this correct? Say yes or no.", "kn": "ಇದು ಸರಿಯೇ? ಹೌದು ಅಥವಾ ಇಲ್ಲ ಎಂದು ಹೇಳಿ."},
    "doc_none": {
        "en": "I could not read this photo clearly. Please take another photo in good light, or tell me the details by voice.",
        "kn": "ಈ ಫೋಟೋ ಸ್ಪಷ್ಟವಾಗಿ ಓದಲು ಆಗಲಿಲ್ಲ. ದಯವಿಟ್ಟು ಬೆಳಕಿನಲ್ಲಿ ಇನ್ನೊಂದು ಫೋಟೋ ತೆಗೆಯಿರಿ, ಅಥವಾ ವಿವರಗಳನ್ನು ಮಾತಿನ ಮೂಲಕ ಹೇಳಿ.",
    },
    "doc_saved": {
        "en": "Thank you. I have noted these details.", "kn": "ಧನ್ಯವಾದಗಳು. ಈ ವಿವರಗಳನ್ನು ಗಮನಿಸಿದ್ದೇನೆ.",
    },
    "doc_discarded": {
        "en": "Okay, I have discarded what I read. Please take another photo or tell me by voice.",
        "kn": "ಸರಿ, ಓದಿದ ವಿವರಗಳನ್ನು ತೆಗೆದುಹಾಕಿದ್ದೇನೆ. ದಯವಿಟ್ಟು ಇನ್ನೊಂದು ಫೋಟೋ ತೆಗೆಯಿರಿ ಅಥವಾ ಮಾತಿನ ಮೂಲಕ ಹೇಳಿ.",
    },
    "low_conf": {"en": "(please check)", "kn": "(ದಯವಿಟ್ಟು ಪರಿಶೀಲಿಸಿ)"},
    "input_rejected": {
        "en": "I cannot act on that request. Please ask about a health or welfare scheme.",
        "kn": "ಆ ವಿನಂತಿಯನ್ನು ನಾನು ಪೂರೈಸಲಾರೆ. ದಯವಿಟ್ಟು ಆರೋಗ್ಯ ಅಥವಾ ಕಲ್ಯಾಣ ಯೋಜನೆಯ ಬಗ್ಗೆ ಕೇಳಿ.",
    },
    "forgot": {"en": "I have erased everything I knew about you.", "kn": "ನಿಮ್ಮ ಬಗ್ಗೆ ನನಗೆ ಗೊತ್ತಿದ್ದ ಎಲ್ಲವನ್ನೂ ಅಳಿಸಿದ್ದೇನೆ."},
    "tulu_note": {
        "en": "Tulu voice recognition is limited, so I will listen in Kannada and answer in Kannada.",
        "kn": "ತುಳು ಧ್ವನಿ ಗುರುತಿಸುವಿಕೆ ಸೀಮಿತವಾಗಿದೆ, ಆದ್ದರಿಂದ ನಾನು ಕನ್ನಡದಲ್ಲಿ ಕೇಳಿ ಕನ್ನಡದಲ್ಲಿ ಉತ್ತರಿಸುತ್ತೇನೆ.",
    },
    "not_understood_answer": {
        "en": "Sorry, I did not catch that.", "kn": "ಕ್ಷಮಿಸಿ, ನನಗೆ ಅರ್ಥವಾಗಲಿಲ್ಲ.",
    },
}

DOCS = {
    "aadhaar": {"en": "Aadhaar card", "kn": "ಆಧಾರ್ ಕಾರ್ಡ್"},
    "ration_card": {"en": "Ration card", "kn": "ಪಡಿತರ ಚೀಟಿ"},
    "income_certificate": {"en": "Income certificate (if no BPL card)", "kn": "ಆದಾಯ ಪ್ರಮಾಣ ಪತ್ರ (ಬಿಪಿಎಲ್ ಕಾರ್ಡ್ ಇಲ್ಲದಿದ್ದರೆ)"},
    "aadhaar_mobile": {"en": "Mobile number linked to Aadhaar", "kn": "ಆಧಾರ್‌ಗೆ ಲಿಂಕ್ ಆದ ಮೊಬೈಲ್ ಸಂಖ್ಯೆ"},
    "mobile": {"en": "Mobile number", "kn": "ಮೊಬೈಲ್ ಸಂಖ್ಯೆ"},
    "land_record": {"en": "Land record (RTC / Pahani)", "kn": "ಭೂ ದಾಖಲೆ (ಪಹಣಿ / ಆರ್‌ಟಿಸಿ)"},
    "bank_passbook": {"en": "Bank passbook (Aadhaar-linked)", "kn": "ಬ್ಯಾಂಕ್ ಪಾಸ್‌ಬುಕ್ (ಆಧಾರ್ ಲಿಂಕ್ ಆದದ್ದು)"},
    "mcp_card": {"en": "Mother and Child Protection (MCP) card", "kn": "ತಾಯಿ-ಮಗು ರಕ್ಷಣಾ (ಎಂಸಿಪಿ) ಕಾರ್ಡ್"},
    "husband_aadhaar": {"en": "Husband's Aadhaar card", "kn": "ಪತಿಯ ಆಧಾರ್ ಕಾರ್ಡ್"},
}

DOC_TYPE_NAMES = {
    "ration_card": {"en": "ration card", "kn": "ಪಡಿತರ ಚೀಟಿ"},
    "aadhaar": {"en": "Aadhaar card", "kn": "ಆಧಾರ್ ಕಾರ್ಡ್"},
    "income_certificate": {"en": "income certificate", "kn": "ಆದಾಯ ಪ್ರಮಾಣ ಪತ್ರ"},
    "land_record": {"en": "land record", "kn": "ಭೂ ದಾಖಲೆ"},
    "mcp_card": {"en": "MCP card", "kn": "ಎಂಸಿಪಿ ಕಾರ್ಡ್"},
    "unknown": {"en": "document", "kn": "ದಾಖಲೆ"},
}


def t(key: str, lang: str, **fmt: Any) -> str:
    s = T[key][out_lang(lang)]
    return s.format(**fmt) if fmt else s


def doc_name(doc_id: str, lang: str) -> str:
    return DOCS.get(doc_id, {}).get(out_lang(lang), doc_id)


KN_DIGITS = str.maketrans("೦೧೨೩೪೫೬೭೮೯", "0123456789")


def normalize_digits(s: str) -> str:
    return s.translate(KN_DIGITS)
