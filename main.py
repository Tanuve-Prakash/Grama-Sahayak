"""FastAPI backend. A web app sends audio / images / text here (slide 4: "Interaction").
Documents are processed in memory and are not stored."""
from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from typing import Deque, Dict

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import speech
from .agents.vision import available_engine
from .config import settings
from .i18n import out_lang, t
from .llm import llm
from .orchestrator import Orchestrator
from .schemas import AskIn, ConfirmIn, SessionIn, SessionRef, TtsIn
from .session import SessionStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("grama")

state: Dict[str, object] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    state["orch"] = Orchestrator()
    state["sessions"] = SessionStore()
    log.info("ready: %d schemes, embedder=%s, store=%s, llm=%s, ocr=%s",
             len(state["orch"].kb.schemes), state["orch"].embedder.name,
             state["orch"].retrieval.store.backend, llm.name, available_engine())
    yield


app = FastAPI(title="Grama Sahayak", version="1.0.0", lifespan=lifespan,
              description="Voice-first multi-agent AI navigator for rural health and government schemes.")

if settings.cors_origins:
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins.split(","),
                       allow_methods=["GET", "POST", "DELETE"], allow_headers=["*"])

_hits: Dict[str, Deque[float]] = defaultdict(deque)


@app.middleware("http")
async def security_and_limits(request: Request, call_next):
    if request.url.path.startswith("/api/"):
        ip = request.client.host if request.client else "?"
        now, q = time.time(), _hits[ip]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= settings.rate_limit_per_min:
            return JSONResponse({"detail": "Too many requests. Please wait a moment."}, status_code=429)
        q.append(now)
    resp = await call_next(request)
    resp.headers.update({
        "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer",
        "Permissions-Policy": "microphone=(self), camera=(self), geolocation=()",
        "Content-Security-Policy": "default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob: data:; "
                                   "style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'",
    })
    if request.url.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


def _orch() -> Orchestrator:
    return state["orch"]  # type: ignore[return-value]


def _sess(sid: str):
    s = state["sessions"].get(sid)  # type: ignore[attr-defined]
    if s is None:
        raise HTTPException(404, "Session expired. Please start again.")
    return s


async def _read_limited(f: UploadFile, limit: int) -> bytes:
    data = await f.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, "File too large")
    if not data:
        raise HTTPException(400, "Empty file")
    return data


def _sniff_image(b: bytes) -> str:
    if b[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "image/webp"
    raise HTTPException(415, "Please upload a JPEG, PNG or WebP photo")


# ------------------------------------------------------------------ API
@app.get("/api/health")
def health():
    o = _orch()
    return {
        "status": "ok", "version": app.version,
        "languages": ["kn", "en", "tcy"],
        "capabilities": {
            "server_stt": speech.stt_available(), "server_tts": speech.tts_available(),
            "ocr": available_engine(), "llm": llm.name,
            "embedder": o.embedder.name, "vector_store": o.retrieval.store.backend,
        },
        "schemes": [{"id": s.id, "name": s.name, "source_url": s.source_url} for s in o.kb.schemes.values()],
    }


@app.post("/api/session")
def new_session(body: SessionIn):
    s = state["sessions"].create(body.lang)  # type: ignore[attr-defined]
    greeting = t("greeting", body.lang)
    note = t("tulu_note", body.lang) if body.lang == "tcy" else None
    return {"session_id": s.id, "lang": s.lang, "greeting": greeting, "note": note, "ttl_s": settings.session_ttl_s}


@app.post("/api/ask")
def ask(body: AskIn):
    return _orch().handle_text(_sess(body.session_id), body.text, body.lang)


@app.post("/api/transcribe")
async def transcribe(audio: UploadFile = File(...), lang: str = Form("kn")):
    if not speech.stt_available():
        raise HTTPException(501, "Server speech recognition is not installed; the browser's speech API is used instead.")
    data = await _read_limited(audio, settings.max_audio_bytes)
    import anyio
    text, conf = await anyio.to_thread.run_sync(speech.transcribe, data, lang)
    return {"text": text, "confidence": conf}


@app.post("/api/vision")
async def vision(image: UploadFile = File(...), session_id: str = Form(...), lang: str = Form(None)):
    s = _sess(session_id)
    data = await _read_limited(image, settings.max_image_bytes)
    mime = _sniff_image(data)
    import anyio
    return await anyio.to_thread.run_sync(_orch().handle_image, s, data, mime, lang)


@app.post("/api/confirm")
def confirm(body: ConfirmIn):
    return _orch().confirm_document(_sess(body.session_id), body.accept, body.corrections)


@app.post("/api/forget")
def forget(body: SessionRef):
    return _orch().forget(_sess(body.session_id))


@app.delete("/api/session/{sid}")
def delete_session(sid: str):
    state["sessions"].delete(sid)  # type: ignore[attr-defined]
    return {"deleted": True}


@app.post("/api/tts")
async def tts(body: TtsIn):
    if not speech.tts_available():
        raise HTTPException(501, "Server TTS not installed; the browser voice is used instead.")
    import anyio
    audio = await anyio.to_thread.run_sync(speech.synthesize, body.text, body.lang)
    return Response(audio, media_type="audio/mpeg")


# ------------------------------------------------------------------ static PWA (mounted last)
if settings.web_dir.exists():
    app.mount("/", StaticFiles(directory=str(settings.web_dir), html=True), name="web")
