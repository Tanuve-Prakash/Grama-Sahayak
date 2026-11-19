"""Central configuration. Everything is overridable with environment variables
(see .env.example) so the same code runs on a laptop, in Docker, or on a server."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    return default if v is None else v.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # ---- paths
    data_dir: Path = ROOT / "data"
    web_dir: Path = ROOT / "web"
    index_path: Path = ROOT / "data" / ".index" / "schemes.npz"

    # ---- LLM (optional: the system works fully offline without one)
    llm_provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "none"))  # none|anthropic|openai
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "claude-sonnet-5-5"))
    llm_base_url: str = field(default_factory=lambda: os.getenv("LLM_BASE_URL", "http://localhost:11434/v1"))
    llm_api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", os.getenv("ANTHROPIC_API_KEY", "")))
    llm_timeout_s: float = field(default_factory=lambda: float(os.getenv("LLM_TIMEOUT_S", "20")))
    llm_polish: bool = field(default_factory=lambda: _bool("LLM_POLISH", True))

    # ---- retrieval
    embedder: str = field(default_factory=lambda: os.getenv("EMBEDDER", "auto"))  # auto|hashing|st
    st_model: str = field(default_factory=lambda: os.getenv(
        "ST_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"))
    top_k: int = field(default_factory=lambda: int(os.getenv("TOP_K", "6")))
    max_retrieval_retries: int = field(default_factory=lambda: int(os.getenv("MAX_RETRIEVAL_RETRIES", "2")))
    min_relevance: float = field(default_factory=lambda: float(os.getenv("MIN_RELEVANCE", "0.10")))

    # ---- speech
    whisper_model: str = field(default_factory=lambda: os.getenv("WHISPER_MODEL", "small"))
    enable_server_stt: bool = field(default_factory=lambda: _bool("ENABLE_SERVER_STT", True))
    enable_server_tts: bool = field(default_factory=lambda: _bool("ENABLE_SERVER_TTS", True))

    # ---- vision
    ocr_engine: str = field(default_factory=lambda: os.getenv("OCR_ENGINE", "auto"))  # auto|tesseract|easyocr|none
    tesseract_langs: str = field(default_factory=lambda: os.getenv("TESSERACT_LANGS", "auto"))
    max_image_bytes: int = field(default_factory=lambda: int(os.getenv("MAX_IMAGE_BYTES", str(6 * 1024 * 1024))))
    max_audio_bytes: int = field(default_factory=lambda: int(os.getenv("MAX_AUDIO_BYTES", str(10 * 1024 * 1024))))

    # ---- privacy / safety
    session_ttl_s: int = field(default_factory=lambda: int(os.getenv("SESSION_TTL_S", "1800")))
    max_text_chars: int = field(default_factory=lambda: int(os.getenv("MAX_TEXT_CHARS", "600")))
    rate_limit_per_min: int = field(default_factory=lambda: int(os.getenv("RATE_LIMIT_PER_MIN", "60")))
    cors_origins: str = field(default_factory=lambda: os.getenv("CORS_ORIGINS", ""))


settings = Settings()
