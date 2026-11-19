"""Safety checks that sit at the three points marked on the architecture slide:
INPUT (sanitise + prompt-injection screen), DATA (PII masking, no persistence) and
OUTPUT (handled by the verifier agent plus the disclaimer added by the composer)."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import List

from .config import settings

_CTRL = re.compile(r"[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f\u200b-\u200f\u202a-\u202e\u2060\ufeff]")
_INJECTION = [
    r"ignore (all|any|the|your|previous|above).{0,30}(instruction|prompt|rule)",
    r"disregard (all|any|the|your|previous|above).{0,30}(instruction|prompt|rule)",
    r"(reveal|show|print|repeat).{0,20}(system prompt|hidden prompt|your instructions)",
    r"you are now\b", r"\bjailbreak\b", r"\bdeveloper mode\b", r"act as (?:an? )?(?:unfiltered|dan)\b",
    r"pretend (?:to be|you are)\b", r"<\s*/?\s*(system|assistant)\s*>",
    r"ಹಿಂದಿನ ಸೂಚನೆ.{0,20}(ನಿರ್ಲಕ್ಷಿಸು|ಬಿಡು)",
]
_INJ_RE = re.compile("|".join(_INJECTION), re.I | re.S)
_AADHAAR = re.compile(r"(?<!\d)(\d{4})[\s-]?(\d{4})[\s-]?(\d{4})(?!\d)")
_PHONE = re.compile(r"(?<!\d)([6-9]\d{9})(?!\d)")


@dataclass
class GuardReport:
    ok: bool
    text: str
    flags: List[str] = field(default_factory=list)


def guard_input(text: str) -> GuardReport:
    """Normalise, bound and screen user text. Never raises."""
    flags: List[str] = []
    t = unicodedata.normalize("NFC", text or "")
    t = _CTRL.sub("", t).strip()
    if len(t) > settings.max_text_chars:
        t = t[: settings.max_text_chars]
        flags.append("truncated")
    if _INJ_RE.search(t):
        return GuardReport(False, "", ["prompt_injection"])
    if not t:
        return GuardReport(False, "", ["empty"])
    return GuardReport(True, t, flags)


def mask_pii(text: str) -> str:
    """Mask Aadhaar and phone numbers before text is logged, traced or sent to an external LLM."""
    text = _AADHAAR.sub(lambda m: "XXXX XXXX " + m.group(3), text)
    return _PHONE.sub(lambda m: "XXXXXX" + m.group(1)[-4:], text)


def mask_aadhaar_last4(number: str) -> str:
    digits = re.sub(r"\D", "", number)
    return "XXXX XXXX " + digits[-4:] if len(digits) == 12 else "XXXX"
