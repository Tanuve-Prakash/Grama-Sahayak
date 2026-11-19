from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class SessionIn(BaseModel):
    lang: str = Field("kn", pattern="^(kn|en|tcy)$")


class AskIn(BaseModel):
    session_id: str
    text: str = Field(..., max_length=2000)
    lang: Optional[str] = Field(None, pattern="^(kn|en|tcy)$")


class ConfirmIn(BaseModel):
    session_id: str
    accept: bool
    corrections: Optional[Dict[str, Any]] = None


class SessionRef(BaseModel):
    session_id: str


class TtsIn(BaseModel):
    text: str = Field(..., max_length=800)
    lang: str = Field("kn", pattern="^(kn|en|tcy)$")
