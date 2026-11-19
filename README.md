# ಗ್ರಾಮ ಸಹಾಯಕ · Grama Sahayak

**A voice-first, multimodal, multi-agent AI navigator for rural health and government schemes.**
Team TANVIA · S P Tanuve, Nivedha K

A person speaks in Kannada (or English; Tulu is a stretch goal), optionally photographs a document, and
hears a spoken answer, an **eligibility verdict with reasons**, and a **checklist of documents and next
steps**, every claim checked against the scheme guideline before it is spoken.

```
Voice / Photo / Text ─► Input guard ─► Intake ─► Vision ─► Retrieval ─► Eligibility ─► Composer ─► Verifier ─► Spoken answer
                                                              ▲                                      │
                                                              └──── rejected: re-retrieve (≤2×) ─────┘   or abstain + helpline
```

## Quick start (no API keys, no downloads, no GPU)

```bash
pip install -r requirements-dev.txt
python -m pytest -q            # 112 tests
python scripts/evaluate.py     # accuracy / safety metrics
uvicorn app.main:app --port 8000
# open http://localhost:8000  (Chrome on Android gives the best Kannada voice)
```
No browser? `python scripts/demo_cli.py --lang kn --trace`.
Docker: `docker compose up --build` (installs Tesseract with Kannada data).

## How this follows the presentation, slide by slide

| Slide | Promise in the deck | Where it lives |
|---|---|---|
| 1 | Grama Sahayak, multimodal multi-agent navigator | `app/orchestrator.py` |
| 2 | English-only PDFs, scattered portals, unclear document lists, repeated trips | `data/schemes/*.md` (bilingual guideline summaries), `data/rules/*.yaml`, document checklist on every verdict |
| 3 | Speak in Kannada / Tulu / English, photograph a document, hear verdict + checklist | `web/` PWA, `app/agents/intake.py`, `vision.py`, `composer.py` |
| 3 | vs. chatbots: **cited answers, a verifier agent, reads your document** | `agents/verifier.py`, `agents/vision.py`, citations on every card |
| 4 | **Five agents**: Intake, Vision, Retrieval, Eligibility, Verifier | `app/agents/{intake,vision,retrieval,eligibility,verifier}.py` |
| 4 | Scheme documents in a vector store (FAISS or Chroma) | `app/vectorstore.py` (FAISS if installed, else exact NumPy), `app/ingest.py` |
| 4 | Rejected answer goes back for re-retrieval (dashed arrow) | `orchestrator._run_pipeline`: 3 progressively wider retrieval attempts, visible as "↩" in the UI trace |
| 4 | Safety checks at **input, data, output** | `app/guards.py` (injection screen, PII masking), in-memory sessions, Verifier + disclaimer |
| 4 | Web app → FastAPI; documents in memory, not stored | `app/main.py`; Tesseract reads from stdin, image bytes are never written or kept |
| 5 | React/Streamlit PWA with mic and camera | `web/`: dependency-free installable PWA (mic, camera, offline shell) |
| 5 | Python + FastAPI; Whisper STT; open-source TTS | `app/main.py`, `app/speech.py` (faster-whisper, gTTS), browser Web Speech as fallback |
| 5 | EasyOCR or Tesseract + vision model | `agents/vision.py` (Tesseract, EasyOCR, optional vision-LLM) |
| 5 | Multilingual embeddings + FAISS/Chroma | `app/embeddings.py` (sentence-transformers or offline hashing embedder) |
| 5 | Open model with an API fallback | `app/llm.py`: `openai` (Ollama/vLLM) or `anthropic`, or none |
| 5 | Eligibility rules for 3 to 4 schemes | PM-JAY / Arogya Karnataka, PM-KISAN, Gruha Lakshmi, PM Matru Vandana |
| 5 | Testing, demo script, backup recording | `tests/` (112), `scripts/evaluate.py`, `scripts/demo_cli.py` |
| 6 | Tulu ASR is limited → Kannada + English first, typed backup | `tcy` mode listens/answers in Kannada with an on-screen note; text box always available |
| 6 | Low-quality photo → show fields, **confirm by voice** | `/api/vision` returns fields + confidence; nothing is used until the person says *yes* (or edits) |
| 6 | Missing document → ask by voice, continue with partial info | Three-valued rules engine asks **one** question at a time; "skip / ಗೊತ್ತಿಲ್ಲ" → verdict becomes *Likely* with items to confirm |
| 6 | Outside the knowledge base → verifier blocks, says unsure, points to helpline | Relevance gate + verifier abstention → "I am not sure" + office + verified helplines |
| 7 | Voice screen: *Likely eligible · Bring: ration card, ID, income certificate · Source* | Exactly this flow is test `test_slide7_demo_flow_english` |

## What makes it more than a chatbot

* **The verdict is computed, not generated.** Eligibility is a deterministic rules engine with Kleene
  three-valued logic: *unknown ≠ no*. It reports exactly which unknown facts could change the outcome.
* **A real verifier.** It independently re-runs the rules and rejects any answer with a verdict mismatch, a number not
  found in the retrieved text, a scheme whose guideline wasn't retrieved, a missing citation, over-claiming
  ("guaranteed"), the wrong language, or no disclaimer. On failure it triggers re-retrieval, then abstains.
* **LLM optional and untrusted.** With `LLM_PROVIDER` set, the model may rephrase for natural speech or read photos,
  but the rephrasing is verified and discarded if it drifts; Aadhaar and phone numbers are masked before any LLM call.
* **Kannada-native understanding:** Kannada digits (೫೪), Kannada number words (ಐವತ್ತನಾಲ್ಕು → 54), negation
  ("ಜಮೀನು ಇಲ್ಲ"), lakh/thousand units, monthly→annual income, Karnataka card codes (PHH→BPL, NPHH→APL).
* **Privacy by design:** sessions live in memory with a 30-minute TTL; "Forget everything" button and voice command;
  Aadhaar reduced to last 4 digits; CSP, no-store, rate limiting, upload sniffing and size caps.
* **Observable:** every response carries an agent trace (timings, checks, the re-retrieval loop) shown in the UI.

## Evaluation (`python scripts/evaluate.py`)

Intake intent+scheme accuracy 1.00 · fact recall 1.00 · verdict accuracy 1.00 · retrieval hit@1 1.00 ·
out-of-scope abstention 1.00 · prompt-injection block 1.00 · verifier catches 4/4 corrupted answers · p50 latency ≈ 1 ms
(on the small bundled evaluation sets; these are regression floors, not field accuracy).

## Configuration

See `.env.example`. Everything is optional.

| Upgrade | Install | Effect |
|---|---|---|
| Server speech-to-text | `pip install faster-whisper` | Whisper transcription via `/api/transcribe` (else browser Web Speech API) |
| Better retrieval | `pip install sentence-transformers` | True multilingual embeddings (auto-detected) |
| FAISS | `pip install faiss-cpu` | FAISS index instead of NumPy |
| Kannada OCR | `apt install tesseract-ocr-kan` or `pip install easyocr` | Reads Kannada text on cards |
| Server TTS | `pip install gTTS` | Kannada voice when the phone has none |
| LLM | `LLM_PROVIDER=anthropic LLM_API_KEY=…` or `openai` + Ollama | Natural rephrasing, photo reading, free-form fact extraction |
| Official PDFs | `pip install pypdf; python -m app.ingest guideline.pdf --id x --name "X"` | Drafts a scheme document to review |

## API

`GET /api/health` · `POST /api/session` · `POST /api/ask` · `POST /api/vision` (multipart) ·
`POST /api/confirm` · `POST /api/transcribe` · `POST /api/tts` · `POST /api/forget` · `DELETE /api/session/{id}`.
Interactive docs at `/docs`.

## Adding a scheme (about 15 minutes)

1. `data/schemes/<id>.md`: sections `overview, benefits, eligibility, exclusions, documents, how-to-apply`, each with `EN:` and `KN:` lines.
2. `data/rules/<id>.yaml`: aliases, documents, and rules (`fact / op / value`, `all` / `any` / `not`), each citing a section.
3. Add helplines in `data/helplines.yaml`; if a rule needs a new fact, add it to `app/facts.py`.
4. `python -m pytest` : start-up validation fails fast if a rule cites a section that doesn't exist.

## Important limitations (please read)

* **The scheme texts are condensed prototype summaries, not official documents.** Rules are simplified (for example the
  PM-KISAN "government employee" exclusion exempts lower-grade staff; PMMVY's second-child rule is modelled in outline).
  Karnataka's BPL income ceiling (₹1,20,000 here) has been under review and may change: it is one number in
  `data/rules/pmjay.yaml`. **Verify every rule and amount against the official guideline before real use**; the
  answers always say they are guidance and that the office decides. Helpline numbers were checked against public
  sources in Nov 2026 and should be re-verified at deployment.
* **Tulu** speech recognition is not realistically available; Tulu mode listens and answers in Kannada.
* The default offline embedder is keyword-and-character based. It works well on this small bilingual corpus
  (see evaluation) but a multilingual model is recommended as the corpus grows.
* Whisper's Kannada accuracy varies with accent and noise. The UI therefore shows and lets people correct what was
  understood, and always offers typed input.
* Tested in a sandbox with Tesseract (English) and a headless browser. The optional Whisper, sentence-transformers,
  EasyOCR, gTTS and live-LLM paths are implemented behind the same interfaces and are covered by mocks, but were not run
  against the real packages/models here. Kannada OCR needs `tesseract-ocr-kan` or EasyOCR.
