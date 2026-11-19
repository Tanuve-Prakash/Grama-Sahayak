"""Server-side speech (both optional; the web app falls back to the browser's Web Speech API).

STT: faster-whisper (open source). Whisper's Kannada accuracy is usable but not perfect, and Tulu is
not supported, so Tulu audio is decoded as Kannada. TTS: gTTS if installed (needs internet) – the
browser's own speechSynthesis is tried first by the UI."""
from __future__ import annotations

import io
import logging
import tempfile
from functools import lru_cache
from typing import Optional, Tuple

from .config import settings

log = logging.getLogger("grama.speech")
WHISPER_LANG = {"kn": "kn", "tcy": "kn", "en": "en"}


@lru_cache(maxsize=1)
def _whisper():
    from faster_whisper import WhisperModel  # optional dependency
    log.info("loading whisper model '%s'", settings.whisper_model)
    return WhisperModel(settings.whisper_model, compute_type="int8")


def stt_available() -> bool:
    if not settings.enable_server_stt:
        return False
    try:
        import faster_whisper  # noqa: F401
        return True
    except Exception:
        return False


def tts_available() -> bool:
    if not settings.enable_server_tts:
        return False
    try:
        import gtts  # noqa: F401
        return True
    except Exception:
        return False


def transcribe(audio: bytes, lang: str) -> Tuple[str, Optional[float]]:
    """Return (text, avg_log_prob). Audio is held in a temp file only for the duration of the call."""
    model = _whisper()
    with tempfile.NamedTemporaryFile(suffix=".webm") as f:
        f.write(audio); f.flush()
        segs, info = model.transcribe(f.name, language=WHISPER_LANG.get(lang, "en"), vad_filter=True, beam_size=5)
        parts = list(segs)
    text = " ".join(s.text.strip() for s in parts).strip()
    conf = sum(s.avg_logprob for s in parts) / len(parts) if parts else None
    return text, conf


def synthesize(text: str, lang: str) -> bytes:
    from gtts import gTTS
    buf = io.BytesIO()
    gTTS(text=text[:600], lang="kn" if lang in ("kn", "tcy") else "en").write_to_fp(buf)
    return buf.getvalue()
