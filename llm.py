"""Optional LLM access. The whole system works with LLM_PROVIDER=none; an LLM only *improves*
three things (fluent paraphrase, free-form fact extraction, document photo reading) and every
LLM output is re-checked by deterministic code (verifier / schema coercion) before use.

Providers:
  anthropic – Claude via the Messages API (set LLM_API_KEY or ANTHROPIC_API_KEY)
  openai    – any OpenAI-compatible server: Ollama, vLLM, llama.cpp, LM Studio (set LLM_BASE_URL)
  none      – disabled"""
from __future__ import annotations

import base64
import json
import logging
import re
from typing import Any, Dict, Optional

import httpx

from .config import settings
from .guards import mask_pii

log = logging.getLogger("grama.llm")


class LLM:
    def __init__(self) -> None:
        self.provider = settings.llm_provider.lower()

    @property
    def available(self) -> bool:
        if self.provider == "anthropic":
            return bool(settings.llm_api_key)
        if self.provider == "openai":
            return True
        return False

    @property
    def name(self) -> str:
        return f"{self.provider}:{settings.llm_model}" if self.available else "none"

    # ------------------------------------------------------------------ text
    def complete(self, system: str, user: str, max_tokens: int = 400, mask: bool = True) -> Optional[str]:
        if not self.available:
            return None
        user = mask_pii(user) if mask else user      # never send Aadhaar / phone numbers to a third party
        try:
            if self.provider == "anthropic":
                r = httpx.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": settings.llm_api_key, "anthropic-version": "2023-06-01"},
                    json={"model": settings.llm_model, "max_tokens": max_tokens, "system": system,
                          "messages": [{"role": "user", "content": user}]},
                    timeout=settings.llm_timeout_s)
                r.raise_for_status()
                return "".join(b.get("text", "") for b in r.json().get("content", [])).strip() or None
            r = httpx.post(
                settings.llm_base_url.rstrip("/") + "/chat/completions",
                headers={"Authorization": f"Bearer {settings.llm_api_key or 'none'}"},
                json={"model": settings.llm_model, "max_tokens": max_tokens, "temperature": 0.2,
                      "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
                timeout=settings.llm_timeout_s)
            r.raise_for_status()
            return (r.json()["choices"][0]["message"]["content"] or "").strip() or None
        except Exception as e:
            log.warning("LLM call failed (%s); using deterministic fallback", type(e).__name__)
            return None

    def complete_json(self, system: str, user: str, max_tokens: int = 300) -> Optional[Dict[str, Any]]:
        out = self.complete(system + "\nReply with a single JSON object and nothing else.", user, max_tokens)
        if not out:
            return None
        m = re.search(r"\{.*\}", out, re.S)
        try:
            return json.loads(m.group(0)) if m else None
        except json.JSONDecodeError:
            return None

    # ---------------------------------------------------------------- vision
    def vision_extract(self, image: bytes, mime: str, prompt: str) -> Optional[Dict[str, Any]]:
        """Read an ID / certificate photo with a vision model (Anthropic only). Image bytes are
        sent in the request and never stored."""
        if self.provider != "anthropic" or not self.available:
            return None
        try:
            r = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": settings.llm_api_key, "anthropic-version": "2023-06-01"},
                json={"model": settings.llm_model, "max_tokens": 500, "messages": [{"role": "user", "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": mime,
                                                 "data": base64.b64encode(image).decode()}},
                    {"type": "text", "text": prompt}]}]},
                timeout=max(settings.llm_timeout_s, 30))
            r.raise_for_status()
            txt = "".join(b.get("text", "") for b in r.json().get("content", []))
            m = re.search(r"\{.*\}", txt, re.S)
            return json.loads(m.group(0)) if m else None
        except Exception as e:
            log.warning("vision LLM failed (%s)", type(e).__name__)
            return None


llm = LLM()
