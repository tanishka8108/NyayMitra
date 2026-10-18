import gc
import json
import os
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import torch
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ValidationError
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
from IndicTransToolkit.processor import IndicProcessor
from test_asr import transcribe_and_discard, release_idle_model
from upload_validation import (
    PDF_MAX_SIZE_BYTES,
    UploadValidationError,
    validate_audio_upload,
    validate_pdf_upload,
)
from pdf_security_scan import PDFSecurityError, secure_validate_pdf
from court_order_explainer import explain_text
from court_order_explain_pipeline import (
    CourtOrderUploadError,
    extract_document_text,
    process_upload,
    safe_filename,
)
from court_order_simple_english import build_layers, plain_summary
from functools import lru_cache
from legal_simplification import (
    MAX_INPUT_CHARS,
    SUPPORTED_TARGET_LANGS,
    UNPRESERVED_WARNING,
    cut_after_marker,
    cut_before_marker,
    mask_for_translation,
    restore_translation,
    simplify_legal_text,
    unpreserved_references,
    with_lead_in,
    with_trail_in,
)
from fastapi.responses import JSONResponse
from glossary_matcher import find_glossary_matches
# The guidance set itself (load_guidance_data, find_related_glossary_terms)
# is now reached through guidance_matching, which does the scoring and
# the shaping; nothing here reads it directly any more.
from guidance_matching import match_guidance
from incident_analysis import analyze_incident
from case_companion import answer_case_question
from conversation_context import CONVERSATIONS
import what_happened_service as what_happened
import juris_ai_live
import what_happened_interpretation
from juris_ai_agent import interpret_with_adk
import logging

# The access-audit block below used to be pasted twice (identical
# second copy); one copy remains — `datetime` itself is already
# imported at the top of the file.
logging.basicConfig(
    filename="access_audit.log",
    level=logging.INFO,
    format="%(asctime)s | %(message)s",
)

def log_access(endpoint: str, detail: str = ""):
    logging.info(f"ACCESS endpoint={endpoint} {detail}")

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
EN_INDIC_MODEL = "ai4bharat/indictrans2-en-indic-dist-200M"
INDIC_INDIC_MODEL = "ai4bharat/indictrans2-indic-indic-dist-320M"

LANG_CODE_MAP = {
    "hi": "hin_Deva",
    "mr": "mar_Deva",
}
SOURCE_LANG = "eng_Latn"

# A local development key, read from the environment so nothing has to
# be edited to change it. The default is not a secret — the same string
# ships in the frontend config and in this service's own tests.
API_KEY = os.environ.get("NYAYMITRA_NLP_KEY", "nyaymitra-local-test-2026")

ip = IndicProcessor(inference=True)
tokenizer = None
model = None
indic_indic_tokenizer = None
indic_indic_model = None

# --- lazy model cache -------------------------------------------------------
# The three checkpoints total ~4.7 GB. They used to be built at startup (and the
# ASR one at import), so the service held all of it for its whole life and left
# the machine ~3.5 GB short. Each model now loads on first use and is released
# again after MODEL_IDLE_SECONDS without a request, so an idle service costs only
# the interpreter. Load, inference and unload all run under that model's lock, so
# the reaper can never unload a checkpoint a request is still using.
MODEL_IDLE_SECONDS = float(os.environ.get("MODEL_IDLE_SECONDS", "600"))

_model_locks = {
    "en_indic": threading.Lock(),
    "indic_indic": threading.Lock(),
}
_last_used: dict[str, float] = {}


def verify_api_key(authorization: str = Header(None)):
    if authorization != f"Bearer {API_KEY}":
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def _use_legacy_cache(model):
    """Keep IndicTrans2 on its own tuple cache instead of transformers' Cache.

    transformers >= 4.36 pre-creates an *empty* EncoderDecoderCache before the
    first decode step. IndicTrans2's remote modelling code predates that and does
    `past_key_values[0][0].shape[2]`, which raises AttributeError while the cache
    layers are still None. Reporting that the model does not support the default
    dynamic cache makes transformers leave `past_key_values=None` on the first
    step, so the model manages the legacy tuple cache itself -- the format its own
    `_reorder_cache` expects. Without this every generate() call returns 500.
    """
    model.__class__._supports_default_dynamic_cache = classmethod(lambda cls: False)
    return model


def _ensure_model(name: str):
    """Build one checkpoint on first use. Caller must hold `_model_locks[name]`.

    `_use_legacy_cache` is applied here rather than at import so a model that has
    been released and reloaded gets the same transformers shim as a first load.
    """
    global tokenizer, model, indic_indic_tokenizer, indic_indic_model

    if name == "en_indic":
        if model is None:
            print("Loading en-indic model...", flush=True)
            tokenizer = AutoTokenizer.from_pretrained(
                EN_INDIC_MODEL, trust_remote_code=True
            )
            model = _use_legacy_cache(
                AutoModelForSeq2SeqLM.from_pretrained(
                    EN_INDIC_MODEL, trust_remote_code=True
                ).to(DEVICE)
            )
            model.eval()
            print("en-indic model ready.", flush=True)
        return

    if name == "indic_indic":
        if indic_indic_model is None:
            print("Loading indic-indic model...", flush=True)
            indic_indic_tokenizer = AutoTokenizer.from_pretrained(
                INDIC_INDIC_MODEL, trust_remote_code=True
            )
            indic_indic_model = _use_legacy_cache(
                AutoModelForSeq2SeqLM.from_pretrained(
                    INDIC_INDIC_MODEL, trust_remote_code=True
                ).to(DEVICE)
            )
            indic_indic_model.eval()
            print("indic-indic model ready.", flush=True)
        return

    raise KeyError(f"unknown model {name!r}")


def _release_model(name: str) -> bool:
    """Drop one translation checkpoint. Caller must hold `_model_locks[name]`."""
    global tokenizer, model, indic_indic_tokenizer, indic_indic_model

    if name == "en_indic":
        if model is None:
            return False
        model = None
        tokenizer = None
    elif name == "indic_indic":
        if indic_indic_model is None:
            return False
        indic_indic_model = None
        indic_indic_tokenizer = None
    else:
        raise KeyError(f"unknown model {name!r}")

    gc.collect()
    print(f"Released idle model {name} (~1.2 GB freed).", flush=True)
    return True


@contextmanager
def _loaded(name: str):
    """Lock a model, load it if needed, run the body, then stamp it as used."""
    with _model_locks[name]:
        _ensure_model(name)
        try:
            yield
        finally:
            _last_used[name] = time.time()


def _reaper():
    """Release checkpoints that have gone idle so their memory returns to the OS."""
    while True:
        time.sleep(30)

        for name, lock in _model_locks.items():
            if time.time() - _last_used.get(name, 0.0) < MODEL_IDLE_SECONDS:
                continue
            if not lock.acquire(blocking=False):
                continue  # a request is loading or running with it
            try:
                _release_model(name)
            finally:
                lock.release()

        # The ASR model keeps its own lock inside test_asr, so it self-guards.
        try:
            release_idle_model(MODEL_IDLE_SECONDS)
        except Exception as exc:  # noqa: BLE001 - the reaper must never die
            print(f"reaper: ASR release skipped ({exc!r})", flush=True)

app = FastAPI(title="NyayMitra Translation Service")

app.include_router(juris_ai_live.router)

# Register Gemini + Google ADK with the existing incident pipeline.
what_happened_interpretation.register_interpreter(interpret_with_adk)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_event():
    print(
        f"Models load on first use and are released after "
        f"{MODEL_IDLE_SECONDS:.0f}s idle; nothing is held at startup.",
        flush=True,
    )
    threading.Thread(target=_reaper, name="model-reaper", daemon=True).start()

class TranslateRequest(BaseModel):
    case_id: str
    source_text: str
    source_lang: str
    target_lang: str


class TranslateResponse(BaseModel):
    translation_id: str
    case_id: str
    source_text: str
    translated_text: str
    language: str
    translated_at: datetime
    glossary_matches: list


@app.post("/api/translate", response_model=TranslateResponse)
def translate_endpoint(req: TranslateRequest, auth=Depends(verify_api_key)):
    if req.source_lang not in {"en", "hi", "mr"}:
        raise HTTPException(
            status_code=400,
            detail="Unsupported source_lang. Supported: en, hi, mr."
        )

    if req.target_lang not in LANG_CODE_MAP:
        raise HTTPException(
            status_code=400,
            detail="Unsupported target_lang. Supported: hi, mr."
        )

    glossary_matches = find_glossary_matches(req.source_text)

    try:
        if req.source_lang == "en":
            internal_target_lang = LANG_CODE_MAP[req.target_lang]
            with _loaded("en_indic"):
                translated_text = translate(
                    req.source_text,
                    internal_target_lang,
                )
        else:
            if req.source_lang == req.target_lang:
                translated_text = req.source_text
            else:
                with _loaded("indic_indic"):
                    translated_text = translate_indic_to_indic(
                        req.source_text,
                        LANG_CODE_MAP[req.source_lang],
                        LANG_CODE_MAP[req.target_lang],
                    )
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Translation failed. Please try again."
        )

    return TranslateResponse(
        translation_id=f"t_{uuid.uuid4().hex[:8]}",
        case_id=req.case_id,
        source_text=req.source_text,
        translated_text=translated_text,
        language=req.target_lang,
        translated_at=datetime.now(timezone.utc),
        glossary_matches=glossary_matches,
    )

def translate(text: str, target_lang_code: str) -> str:
    # Translate long legal text in small word-boundary chunks.
    # This avoids truncation while preserving legal abbreviations,
    # case numbers, party names, and dates.
    words = text.strip().split()
    chunks = []
    current = ""
    max_chars = 450

    for word in words:
        if current and len(current) + 1 + len(word) > max_chars:
            chunks.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()

    if current:
        chunks.append(current)

    translated_chunks = []

    for chunk in chunks:
        batch = ip.preprocess_batch(
            [chunk],
            src_lang=SOURCE_LANG,
            tgt_lang=target_lang_code,
        )

        inputs = tokenizer(
            batch,
            padding=True,
            truncation=True,
            return_tensors="pt",
        ).to(DEVICE)

        with torch.no_grad():
            generated = model.generate(
                **inputs,
                max_length=256,
                num_beams=5,
            )

        decoded = tokenizer.batch_decode(
            generated,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=True,
        )

        result = ip.postprocess_batch(
            decoded,
            lang=target_lang_code,
        )

        translated_chunks.append(result[0])

    translated_text = " ".join(translated_chunks)

    return translated_text
def translate_indic_to_indic(text: str, src_lang_code: str, tgt_lang_code: str) -> str:
    batch = ip.preprocess_batch([text], src_lang=src_lang_code, tgt_lang=tgt_lang_code)
    inputs = indic_indic_tokenizer(batch, truncation=True, padding="longest", return_tensors="pt").to(DEVICE)
    with torch.no_grad():
        generated = indic_indic_model.generate(**inputs, max_length=256, num_beams=5)
    decoded = indic_indic_tokenizer.batch_decode(generated, skip_special_tokens=True, clean_up_tokenization_spaces=True)
    result = ip.postprocess_batch(decoded, lang=tgt_lang_code)
    return result[0]


class IndicToIndicRequest(BaseModel):
    case_id: str
    source_text: str
    source_lang: str  # 'hi' or 'mr'
    target_lang: str  # 'hi' or 'mr'


@app.post("/api/translate/indic-to-indic")
def translate_indic_to_indic_endpoint(req: IndicToIndicRequest, auth=Depends(verify_api_key)):
    if req.source_lang not in LANG_CODE_MAP or req.target_lang not in LANG_CODE_MAP:
        raise HTTPException(status_code=400, detail="source_lang and target_lang must be 'hi' or 'mr'.")

    if req.source_lang == req.target_lang:
        return {"translated_text": req.source_text, "note": "source and target language are the same"}

    with _loaded("indic_indic"):
        translated_text = translate_indic_to_indic(
            req.source_text, LANG_CODE_MAP[req.source_lang], LANG_CODE_MAP[req.target_lang]
        )

    return {
        "case_id": req.case_id,
        "source_text": req.source_text,
        "translated_text": translated_text,
        "source_lang": req.source_lang,
        "target_lang": req.target_lang,
    }


@app.post("/api/voice")
async def voice_endpoint(
    target_lang: str = "mr",
    audio: UploadFile = File(...),
    auth=Depends(verify_api_key),
):
    if target_lang not in {"hi", "mr"}:
        raise HTTPException(
            status_code=400,
            detail="Unsupported target_lang. Supported: hi, mr."
        )

    try:
        audio_bytes = await audio.read()
        validate_audio_upload(audio_bytes)

        transcribed_text = transcribe_and_discard(
            audio_bytes,
            target_lang,
        )

        log_access(
            "/api/voice",
            f"target_lang={target_lang} filename={audio.filename}"
        )

        return {
            "transcribed_text": transcribed_text,
            "language": target_lang,
        }

    except UploadValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    except HTTPException:
        raise

    except Exception as exc:
        # Never swallow the reason: a bare 500 with no log line makes this
        # service undebuggable (it hid the transformers cache bug above).
        logging.getLogger("nyaymitra.voice").exception(
            "voice transcription failed: %r", exc
        )
        raise HTTPException(
            status_code=500,
            detail="Voice transcription failed. Please try again."
        )


# ---------------------------------------------------------------------------
# COURT ORDERS — read the file, then explain it in plain language.
#
# Neither of these loads a model. Explaining an order should not cost
# 370 MB and ten seconds of model load, and it does not need one: an
# order is written in standing language, and restating that language
# plainly is fast, deterministic, and honest about what it actually saw.
#
# Extraction is best effort. A PDF with a text layer is easy; a
# photograph of a paper order needs OCR this host does not have. When
# extraction fails the caller is told exactly why, so the UI can ask
# for the text rather than inventing an explanation of a file it
# never read.
# ---------------------------------------------------------------------------


def _extract_image_text(data: bytes) -> tuple[str, str]:
    """OCR a photograph or scan of an order. Returns (text, reason).

    `reason` is set only when the text came back empty, and words it
    for the person who uploaded — never for whoever is debugging.
    """
    try:
        import io as _io

        import pytesseract
        from PIL import Image
    except ImportError:
        return "", (
            "Reading images needs OCR, which is not installed on this "
            "host. Paste the text of the order and it will be explained."
        )

    try:
        with Image.open(_io.BytesIO(data)) as image:
            text = pytesseract.image_to_string(image, lang="eng+hin+mar")
    except Exception as exc:  # noqa: BLE001
        logging.getLogger("nyaymitra.court_order").exception(
            "image OCR failed: %r", exc
        )
        return "", (
            "This image could not be read. Try a clearer scan, or paste "
            "the text of the order."
        )

    text = (text or "").strip()

    if not text:
        return "", (
            "No text could be recognised in this image. Try a clearer "
            "scan, or paste the text of the order."
        )

    return text, ""


@app.post("/api/court-order/extract")
async def court_order_extract(
    file: UploadFile = File(...),
    auth=Depends(verify_api_key),
):
    """Best-effort text out of an uploaded court order.

    The same checks the explain upload runs — size, type, readability,
    then the malicious-content scan before any parser touches the
    bytes — and the same extraction, including OCR for pages that are a
    scan. Failures that mean "this file is not something we will read"
    are 400s; a document we simply cannot get words out of is a normal
    answer with a reason, because that was never an error.
    """
    data = await file.read(PDF_MAX_SIZE_BYTES + 1)
    filename = safe_filename(file.filename)

    if len(data) > PDF_MAX_SIZE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"File too large. Maximum allowed size is "
                f"{PDF_MAX_SIZE_BYTES // (1024 * 1024)} MB."
            ),
        )

    looks_like_pdf = (
        (file.filename or "").lower().endswith(".pdf")
        or (file.content_type or "").lower() == "application/pdf"
        or data[:5] == b"%PDF-"
    )

    ocr_used = False
    page_count = None

    if looks_like_pdf:
        try:
            validate_pdf_upload(data)
            secure_validate_pdf(data)
        except (UploadValidationError, PDFSecurityError) as exc:
            log_access(
                "/api/court-order/extract",
                f"filename={filename} bytes={len(data)} rejected=yes",
            )
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        extracted = extract_document_text(data)
        text = "\n\n".join(
            page for page in extracted["texts"] if page
        ).strip()
        ocr_used = extracted["ocr_used"]
        page_count = extracted["page_count"]

        if not text:
            reason = (
                "No readable text could be found in this PDF, even with "
                "OCR. Upload a clearer scan, or paste the text of the "
                "order."
            )
        else:
            reason = ""
    else:
        text, reason = _extract_image_text(data)
        ocr_used = bool(text)

    log_access(
        "/api/court-order/extract",
        f"filename={filename} bytes={len(data)} read_chars={len(text)} "
        f"ocr={ocr_used} pages={page_count if page_count is not None else '-'}",
    )

    if not text:
        return {
            "ok": False,
            "text": "",
            "needs_text": True,
            "reason": reason,
            "ocr_used": ocr_used,
            "page_count": page_count,
        }

    return {
        "ok": True,
        "text": text,
        "needs_text": False,
        "reason": "",
        "ocr_used": ocr_used,
        "page_count": page_count,
    }


# The order-reading rules (standing wording, dates, glossary terms)
# live in court_order_explainer.py, so the pasted-text path below and
# the uploaded-PDF path read a document through exactly the same rules.


class CourtOrderExplainRequest(BaseModel):
    text: str = Field(..., min_length=1)
    filename: str = ""
    # Optional: which language the third layer should be in. English
    # by default, so a client that only ever sends {text, filename}
    # gets the response it has always got.
    language: str = "en"


def _translator_for(language: str):
    """A translator bound to one target language.

    The checkpoint loads on first use rather than at import, so a
    request that never asks for a translation never costs a model
    load, and the service's reaper releases it when it goes idle.
    """
    target = LANG_CODE_MAP[language]

    def _translate(text: str) -> str:
        if not text or not text.strip():
            return text

        with _loaded("en_indic"):
            return translate(text, target)

    return _translate


async def _explain_uploaded_document(request: Request) -> dict:
    """Validate, scan, read and explain an uploaded court order PDF."""
    try:
        form = await request.form()
    except Exception as exc:  # noqa: BLE001
        logging.getLogger("nyaymitra.court_order").exception(
            "explain upload could not be read: %r", exc
        )
        raise HTTPException(
            status_code=400, detail="The uploaded file could not be read."
        ) from exc

    upload = form.get("file")

    if upload is None or not hasattr(upload, "read"):
        raise HTTPException(
            status_code=400,
            detail=(
                "No file was uploaded. Send the court order as a PDF "
                "in the `file` field."
            ),
        )

    # One byte past the limit: an oversized upload is refused while it
    # is being read rather than after it is all in memory.
    data = await upload.read(PDF_MAX_SIZE_BYTES + 1)
    filename = safe_filename(upload.filename)

    if len(data) > PDF_MAX_SIZE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"File too large. Maximum allowed size is "
                f"{PDF_MAX_SIZE_BYTES // (1024 * 1024)} MB."
            ),
        )

    language = str(
        request.query_params.get("language") or form.get("language") or "en"
    ).strip().lower()

    translator = _translator_for(language) if language in {"hi", "mr"} else None

    try:
        result = process_upload(
            data, filename, language=language, translate=translator
        )
    except CourtOrderUploadError as exc:
        # The message is the pipeline's: validation and security
        # wording written for the person uploading, never the
        # scanner's internal findings.
        log_access(
            "/api/court-order/explain",
            f"mode=upload filename={filename} bytes={len(data)} rejected=yes",
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logging.getLogger("nyaymitra.court_order").exception(
            "court order upload failed: %r", exc
        )
        raise HTTPException(
            status_code=500,
            detail="The court order could not be processed. Please try again.",
        ) from exc

    metadata = result.get("metadata", {})
    log_access(
        "/api/court-order/explain",
        f"mode=upload filename={filename} bytes={len(data)} "
        f"pages={metadata.get('page_count')} ocr={metadata.get('ocr_used')} "
        f"sections={metadata.get('sections_found')} lang={language}",
    )

    return result


async def _explain_pasted_text(request: Request) -> dict:
    """Explain text somebody pasted — the body this endpoint always had."""
    try:
        raw = await request.json()
    except Exception:  # noqa: BLE001
        raise HTTPException(
            status_code=400,
            detail=(
                "Expected JSON with a non-empty `text` field, or a PDF "
                "sent as multipart/form-data."
            ),
        ) from None

    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail="Expected a JSON object body.")

    try:
        payload = CourtOrderExplainRequest.model_validate(raw)
    except ValidationError:
        raise HTTPException(
            status_code=400,
            detail="Expected JSON with a non-empty `text` field.",
        ) from None

    text = payload.text.strip()

    if not text:
        raise HTTPException(status_code=400, detail="No text to explain.")

    language = (payload.language or "en").strip().lower()
    if language not in {"en", "hi", "mr"}:
        language = "en"

    explained = explain_text(text)

    # The same three layers the uploaded-PDF path returns: what the
    # court wrote, what it says in plain words, and — when asked for —
    # that plain English in Hindi or Marathi.
    layers = build_layers(
        explained["summary"], plain=plain_summary(explained["points"])
    )

    if language != "en":
        translator = _translator_for(language)
        translated = None
        headline = None

        try:
            translated = translator(layers["simple"] or "") or None
            headline = translator(explained["summary"]) or None
        except Exception as exc:  # noqa: BLE001 - English stays complete
            logging.getLogger("nyaymitra.court_order").warning(
                "pasted-text translation failed: %r", exc
            )
            translated = None
            headline = None

        layers["translated"] = translated

        if translated:
            explained["summary"] = headline or explained["summary"]
            explained["translation"] = {
                "requested": language,
                "applied": True,
                "reason": "",
                "layer": "simple",
            }
        else:
            explained["translation"] = {
                "requested": language,
                "applied": False,
                "reason": (
                    "Translation could not be completed. "
                    "The English text above is complete."
                ),
            }

    explained["layers"] = layers
    explained["language"] = language

    log_access(
        "/api/court-order/explain",
        f"mode=text filename={payload.filename or '-'} chars={len(text)} "
        f"points={len(explained['points'])} terms={len(explained['terms'])} "
        f"lang={language}",
    )

    return {"filename": payload.filename, **explained}


@app.post("/api/court-order/explain")
async def court_order_explain(request: Request, auth=Depends(verify_api_key)):
    """Explain a court order in plain English.

    Two bodies, one set of fields that matter:

    * ``multipart/form-data`` with the order as a PDF — validated,
      security scanned, text extracted (OCR for pages that are a scan),
      split into Case Details / Proceedings / Order / Signatures /
      Document Certification, every section explained, and optionally
      translated to Hindi or Marathi;
    * ``application/json`` with ``{text, filename, language?}`` — the
      pasted-text path, English-only unless a language is named.

    Both answer with the same three layers, on the document and on
    every section it contains::

        layers.legal       the order as the court wrote it
        layers.simple      the same words, in everyday English
        layers.translated  that plain English in Hindi or Marathi

    The model is given the middle layer, never the legalese, so the
    last step reads the way a person would say it.

    Nothing is asserted that was not in the document: if the order does
    not use recognisable wording, the response says so instead of
    summarising a file it did not understand.
    """
    content_type = (request.headers.get("content-type") or "").lower()

    if content_type.startswith("multipart/form-data"):
        return await _explain_uploaded_document(request)

    return await _explain_pasted_text(request)


# ---------------------------------------------------------------------------
# NEXT STEPS - what should I do now, from whatever the person said.
#
# The scoring itself lives in guidance_matching.py, shared with the
# case companion in case_companion.py: one scorer, two callers, so
# /api/guidance and a case question about a stated stage cannot
# disagree about which case stage a description belongs to. The
# vocabulary weights and the coverage bar are documented over there.
#
# The incident workflow (/api/incident/analyze) deliberately does not
# call this: an incident is not a court stage.
# ---------------------------------------------------------------------------



class GuidanceRequest(BaseModel):
    text: str = Field(..., min_length=1)


@app.post("/api/guidance")
def guidance_endpoint(
    req: GuidanceRequest,
    auth=Depends(verify_api_key),
):
    """Match what someone described to the closest case stage, and say
    what that stage calls for."""
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Nothing to read.")

    # One scorer, one shaper (guidance_matching.match_guidance): this
    # endpoint and /api/incident/analyze must never disagree about
    # which case stage a description belongs to.
    match = match_guidance(text)

    if not match.matched:
        log_access(
            "/api/guidance",
            f"chars={len(text)} matched=no "
            f"best={match.coverage:.2f}",
        )
        return match.response

    log_access(
        "/api/guidance",
        f"chars={len(text)} matched={match.guidance_id} "
        f"score={match.score:.2f} coverage={match.coverage:.2f}",
    )

    return match.response


# ---------------------------------------------------------------------------
# LEGAL LANGUAGE -> SIMPLE LANGUAGE -> MARATHI / HINDI
#
# One request, three layers back:
#
#     original_text      the words exactly as they were filed
#     simple_english     the same words, in everyday English
#     translated_text    that plain English, in the target
#
# Layers one and two are pure Python -- the phrase rules in
# legal_simplification_rules.json, no model, no network -- so a request
# for English alone costs nothing but the rules. Only layer three reaches
# IndicTrans2, and it is the *same* en->indic checkpoint that /api/translate
# and /api/court-order/explain already load, guarded by the same lock and
# released by the same reaper. This endpoint therefore adds no model to
# the service's memory and no second FastAPI app to the process.
#
# The answer is deliberately six keys and no more. The frontend renders
# those six and shows the legal-aid disclaimer itself; a seventh field
# here would become a seventh thing to maintain on both sides.
# ---------------------------------------------------------------------------

# IndicTrans2 may hand `2026` back as `२०२६`. A date written that way is
# preserved, and a check that only knew ASCII digits would report a loss
# that never happened.
_DIGIT_TRANSLATION = str.maketrans("०१२३४५६७८९", "0123456789")


def _value_survives(text: str, value: str) -> bool:
    """Is `value` still findable in `text`, in whichever script it arrived?"""
    if value in text:
        return True

    if not any(char.isdigit() for char in value):
        return False  # a name or a court heading has to appear literally

    return value.translate(_DIGIT_TRANSLATION) in text.translate(
        _DIGIT_TRANSLATION
    )


@lru_cache(maxsize=128)
def _translate_simple_layer(
    simple_english: str,
    target_lang: str,
) -> tuple[str, tuple[str, ...]]:
    """Plain English in, that same text in `target_lang` out.

    Everything a translation must not be allowed to alter -- CNR and case
    numbers, sums of money, section numbers, dates, the court's own
    heading and the names of the people in it -- is lifted out first and
    put back byte for byte afterwards.

    IndicTrans2 does not keep every placeholder it is given, so the first
    pass is followed by two *shaped* retries: one puts a short sentence in
    front of the text, one puts it after, and each is cut back off at a
    marker before the result is accepted. A placeholder run that opens the
    input is dropped by the model unless something real precedes it; a
    placeholder that closes it is dropped unless something follows. A
    shaped attempt is only taken when it brings back something the pass
    before it lost.

    If that still leaves a value missing, the text is translated once more
    with no mask at all, and the retry is accepted only when it
    demonstrably carries every dropped value. Otherwise the best masked
    answer stands and the caller is told which references could not be
    confirmed: a warning, never a page that quietly loses a deadline.

    Cached on (text, language), so asking for the same section twice --
    the document first, then one of its sections -- costs one model call
    rather than two. The cache is bounded, so a reader who opens fifty
    sections cannot grow it without end.
    """
    masked, slots = mask_for_translation(simple_english)

    with _loaded("en_indic"):
        translated = translate(masked, target_lang)

    restored, missing = restore_translation(translated, slots)
    pending = list(missing)

    for build, cut in (
        (with_lead_in, cut_after_marker),
        (with_trail_in, cut_before_marker),
    ):
        if not pending:
            break

        shaped = build(masked, slots)
        if shaped is None:
            continue

        payload, marker = shaped
        try:
            with _loaded("en_indic"):
                raw = translate(payload, target_lang)
        except Exception:  # noqa: BLE001 - the pass before it still stands
            continue

        body = cut(raw, marker)
        if body is None:
            continue  # the marker went the way of the placeholders

        candidate, still = restore_translation(body, slots)
        if len(still) < len(pending):
            restored, pending = candidate, list(still)

    if pending:
        # Last resort: no mask at all. A literal value sitting in free
        # text survives translation far more often than a `{0}` token
        # does -- but it also comes back transliterated more often, so
        # the retry has to be *proved* to carry every value before it is
        # allowed to replace an answer that kept them all verbatim.
        try:
            with _loaded("en_indic"):
                retry = translate(simple_english, target_lang)
        except Exception:  # noqa: BLE001 - the masked answer still stands
            retry = ""

        if retry and all(_value_survives(retry, value) for value in pending):
            restored, pending = retry, []

    if not (restored or "").strip():
        # The model produced nothing usable at any point. Saying so is
        # better than returning an empty layer three.
        raise RuntimeError("the model returned no text")

    return restored, tuple(pending)


class LegalSimplifyRequest(BaseModel):
    # Defaults mean a client that posts only `text` still gets Marathi,
    # which is what the frontend's language chooser starts on.
    text: str = ""
    # IndicTrans2's own codes rather than the frontend's "hi"/"mr": this
    # endpoint names the target the way the model names it, because that
    # is what it is being asked to produce.
    target_lang: str = "mar_Deva"


class LegalSimplifyResponse(BaseModel):
    original_text: str
    simple_english: str
    translated_text: str
    target_lang: str
    glossary_terms_used: list[str]
    warnings: list[str]


@app.post("/api/legal-simplify", response_model=LegalSimplifyResponse)
def legal_simplify_endpoint(
    req: LegalSimplifyRequest,
    auth=Depends(verify_api_key),
):
    """Legal wording in; the original, the plain English and the
    translation back -- with everything the service could not promise
    said out loud in `warnings`."""
    text = (req.text or "").strip()

    if not text:
        raise HTTPException(status_code=400, detail="Nothing to simplify.")

    if len(req.text) > MAX_INPUT_CHARS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"That text is too long to simplify in one go "
                f"({len(req.text)} characters; the limit is "
                f"{MAX_INPUT_CHARS}). Send it one section at a time."
            ),
        )

    if req.target_lang not in SUPPORTED_TARGET_LANGS:
        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported target_lang. Supported: "
                + ", ".join(SUPPORTED_TARGET_LANGS)
                + "."
            ),
        )

    simplified = simplify_legal_text(req.text)
    warnings = list(simplified.warnings)

    # Glossary terms come from the existing matcher, so the terms
    # reported here are the same ones /api/translate reports. Both
    # layers are searched: the plain-English rewrite sometimes names a
    # formal term that the original phrased differently.
    glossary_terms_used: list[str] = []
    for source in (req.text, simplified.simple_english):
        for match in find_glossary_matches(source):
            term = match.get("formal_term", "")
            if term and term not in glossary_terms_used:
                glossary_terms_used.append(term)

    # English as the target asks for the plain layer and nothing else --
    # no model call at all, so `translated_text` is that same layer.
    if req.target_lang == "eng_Latn":
        translated_text = simplified.simple_english
        dropped: tuple[str, ...] = ()
    else:
        try:
            translated_text, dropped = _translate_simple_layer(
                simplified.simple_english,
                req.target_lang,
            )
        except Exception:  # noqa: BLE001
            logging.getLogger("nyaymitra.simplify").exception(
                "legal-simplify translation failed (%d chars -> %s)",
                len(simplified.simple_english),
                req.target_lang,
            )
            raise HTTPException(
                status_code=500,
                detail="Translation failed. Please try again.",
            ) from None

    # Two independent checks, one message. `dropped` covers the values
    # that were masked and came back without their token; the second
    # catches a date the model rewrote in passing. Either way the
    # reader is told which reference to go and look for, not left to
    # notice a missing date on their own.
    lost = list(dropped)
    for value in unpreserved_references(simplified.simple_english, translated_text):
        if value not in lost:
            lost.append(value)

    if lost:
        warnings.append(UNPRESERVED_WARNING.format(items=", ".join(lost)))

    seen: list[str] = []
    for warning in warnings:
        if warning not in seen:
            seen.append(warning)

    log_access(
        "/api/legal-simplify",
        f"chars={len(req.text)} target={req.target_lang} "
        f"rules={len(simplified.rules_applied)} "
        f"glossary={len(glossary_terms_used)} warnings={len(seen)}",
    )

    return LegalSimplifyResponse(
        original_text=simplified.original_text,
        simple_english=simplified.simple_english,
        translated_text=translated_text,
        target_lang=req.target_lang,
        glossary_terms_used=glossary_terms_used,
        warnings=seen,
    )


# ---------------------------------------------------------------------------
# WHAT HAPPENED? — two separate workflows, one service, no new model.
#
#   /api/incident/analyze   WORKFLOW 1, "Tell us an incident". Reads a
#                           description of something that happened to
#                           the person: Member 2's classification when
#                           its model is connected (keyword matching
#                           over Member 1's knowledge otherwise, and
#                           that source is reported), the incident
#                           interpretation layer, then the structured
#                           incident knowledge. It does *not* match a
#                           court stage — an incident is not a stage.
#                           Everything it cannot determine comes back
#                           in `warnings`, `missing_information`,
#                           `confidence` and `urgency` rather than
#                           being guessed at.
#
#   /api/case-companion/ask answers WORKFLOW 2, "Ask about your case":
#                           a question about a case from the case
#                           information supplied *with the question*
#                           (Member 4's My Cases data), reusing the
#                           existing guidance engine for the stage the
#                           record states — and saying so plainly when
#                           that information does not cover the
#                           question.
#
# Translation (layer three) reuses `_translate_simple_layer`, the same
# entity-preserving path /api/legal-simplify uses, so a date, a CNR,
# a section number or a sum of money survives into Marathi or Hindi
# unchanged. Conversation memory is the bounded in-store in
# conversation_context.py — no database, one interface.
#
# Both endpoints speak the same API-key convention as the rest of the
# service: `Authorization: Bearer <NYAYMITRA_NLP_KEY>`.
# ---------------------------------------------------------------------------

# How much case information one question may carry. Generous for any
# real case record, small enough that one request cannot pin the
# process.
CASE_CONTEXT_MAX_CHARS = 200_000


class IncidentAnalyzeRequest(BaseModel):
    description: str = ""
    # Optional. Sent by a client that is continuing a conversation;
    # omitted on a first, one-off question and minted by the service.
    conversation_id: str | None = None
    # Facts the client already established (e.g. from an earlier
    # turn). Merged with what this conversation has already seen.
    known_facts: dict = Field(default_factory=dict)
    # BCP-47-ish language of the message itself, handed to Member 2's
    # classifier when it is connected. Defaults to English; it never
    # changes how the text is analyzed here.
    language: str = "en"
    # IndicTrans2's own codes, like /api/legal-simplify. eng_Latn
    # means "no translation" and costs no model call.
    target_lang: str = "eng_Latn"


class CaseCompanionAskRequest(BaseModel):
    question: str = ""
    case_context: dict = Field(default_factory=dict)
    conversation_id: str | None = None
    target_lang: str = "eng_Latn"


def _translate_texts(texts: list[str], target_lang: str) -> tuple[list[str], list[str]]:
    """A list of prose fields into `target_lang`, plus warnings.

    Every value a translation must not touch is masked by
    `_translate_simple_layer` and put back afterwards. A field that
    cannot be translated comes back in English rather than being
    dropped — an untranslated sentence is better than a missing one.
    """
    translated: list[str] = []
    warnings: list[str] = []

    for text in texts:
        if not text:
            translated.append(text)
            continue
        try:
            value, dropped = _translate_simple_layer(text, target_lang)
        except Exception:  # noqa: BLE001 - keep the English and say so
            logging.getLogger("nyaymitra.what_happened").exception(
                "field translation failed (%d chars -> %s)",
                len(text),
                target_lang,
            )
            warnings.append(
                "Part of this answer could not be translated and is "
                "shown in English."
            )
            translated.append(text)
            continue
        if dropped:
            warnings.append(
                UNPRESERVED_WARNING.format(items=", ".join(dropped))
            )
        translated.append(value)

    return translated, warnings


def _dedupe(items: list[str]) -> list[str]:
    seen: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.append(item)
    return seen


def _translate_analysis(result: dict, target_lang: str) -> None:
    """Translate every prose field of an analysis result, in place."""
    extra: list[str] = []

    def one(text: str) -> str:
        values, warnings = _translate_texts([text], target_lang)
        extra.extend(warnings)
        return values[0]

    result["possible_issue"] = one(result["possible_issue"])
    result["simple_explanation"] = one(result["simple_explanation"])
    result["next_steps"] = [one(t) for t in result["next_steps"]]
    result["missing_information"] = [
        one(t) for t in result["missing_information"]
    ]
    result["evidence_to_preserve"] = [
        one(t) for t in result["evidence_to_preserve"]
    ]
    result["warnings"] = [one(t) for t in result["warnings"]]

    urgency = result.get("urgency") or {}
    if urgency.get("message"):
        urgency["message"] = one(urgency["message"])
    if urgency.get("knowledge_indicator_note"):
        urgency["knowledge_indicator_note"] = one(
            urgency["knowledge_indicator_note"]
        )
    if urgency.get("knowledge_indicators"):
        urgency["knowledge_indicators"] = [
            one(t) for t in urgency["knowledge_indicators"]
        ]

    result["warnings"] = _dedupe(result["warnings"] + extra)


# The section headings of `translated_response` — the one-string
# rendering of the analysis, sectioned the same way the screen shows
# it. Headings travel through the same translation path as the prose.
ANALYSIS_HEADINGS = {
    "told": "WHAT YOU TOLD US",
    "involve": "WHAT THIS MAY INVOLVE",
    "simple": "IN SIMPLE WORDS",
    "next": "WHAT YOU CAN CONSIDER DOING",
    "evidence": "INFORMATION / EVIDENCE TO KEEP",
    "missing": "INFORMATION WE STILL NEED",
    "urgency": "URGENCY / IMPORTANT WARNING",
    "disclaimer": "DISCLAIMER",
}


def _headings_in(target_lang: str) -> dict[str, str]:
    if target_lang == "eng_Latn":
        return dict(ANALYSIS_HEADINGS)
    keys = list(ANALYSIS_HEADINGS)
    values, _warnings = _translate_texts(
        [ANALYSIS_HEADINGS[key] for key in keys], target_lang
    )
    return dict(zip(keys, values))


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items if item)


def _compose_analysis_summary(result: dict, target_lang: str) -> str:
    """The whole analysis as one sectioned string.

    Composed from the (possibly already translated) fields, so it can
    never contradict them, and carrying the same hedges and warnings —
    this is the text somebody forwards to a family member.
    """
    headings = _headings_in(target_lang)

    urgency = result.get("urgency") or {}
    urgency_lines: list[str] = []
    if urgency.get("status") == "available":
        urgency_lines.append(
            f"{str(urgency.get('level', '')).upper()}: "
            f"{urgency.get('message', '')}".strip(": ")
        )
    elif urgency.get("message"):
        urgency_lines.append(urgency["message"])
    if urgency.get("knowledge_indicators"):
        urgency_lines.extend(urgency["knowledge_indicators"])
    urgency_lines.extend(result.get("warnings") or [])

    sections: list[tuple[str, str]] = [
        (headings["told"], result.get("what_user_described", "")),
        (headings["involve"], result.get("possible_issue", "")),
        (headings["simple"], result.get("simple_explanation", "")),
        (headings["next"], _bullets(result.get("next_steps") or [])),
        (
            headings["evidence"],
            _bullets(result.get("evidence_to_preserve") or []),
        ),
        (
            headings["missing"],
            _bullets(result.get("missing_information") or []),
        ),
        (headings["urgency"], "\n".join(urgency_lines)),
        (headings["disclaimer"], result.get("disclaimer", "")),
    ]

    return "\n\n".join(
        f"{title}\n{body}".rstrip()
        for title, body in sections
        if body
    )


def _prior_incident_text(
    state: dict,
    this_turn: str,
    *,
    max_chars: int = 8000,
) -> str:
    """Earlier user messages of this incident conversation.

    A follow-up like "It happened yesterday" only makes sense next to
    the account it refers to, so the incident workflow analyzes the
    whole story — every user message since the conversation was on
    the incident intent. Repeats (a re-send of the same text to
    change the language) are not counted twice.
    """
    parts: list[str] = []
    for message in state.get("messages", []):
        if message.get("role") != "user":
            continue
        content = " ".join((message.get("content") or "").split())
        if not content or content == this_turn:
            continue
        parts.append(content)
    combined = " ".join(parts)
    return combined[-max_chars:]


def _translate_companion(result: dict, target_lang: str) -> None:
    """Translate every prose field of a companion answer, in place."""
    extra: list[str] = []

    def one(text: str) -> str:
        values, warnings = _translate_texts([text], target_lang)
        extra.extend(warnings)
        return values[0]

    result["answer"] = one(result["answer"])
    result["next_steps"] = [one(t) for t in result["next_steps"]]
    result["missing_information"] = [
        one(t) for t in result["missing_information"]
    ]
    result["warnings"] = [one(t) for t in result["warnings"]]

    simplified = result.get("simplified_order")
    if simplified:
        simplified["simple_english"] = one(simplified["simple_english"])

    result["warnings"] = _dedupe(result["warnings"] + extra)


def _remembered_facts(result: dict) -> dict:
    """What this analysis established, keyed so a later turn can reuse it."""
    counts: dict[str, int] = {}
    remembered: dict[str, str] = {}
    for fact in result.get("facts", []):
        kind = str(fact.get("type", "fact"))
        if fact.get("source") == "provided":
            key = str(fact.get("label") or kind)
        else:
            counts[kind] = counts.get(kind, 0) + 1
            key = f"{kind}_{counts[kind]}"
        value = fact.get("value")
        if value:
            remembered[key] = str(value)
    return remembered


@app.post("/api/incident/analyze")
def incident_analyze_endpoint(
    req: IncidentAnalyzeRequest,
    auth=Depends(verify_api_key),
):
    """WORKFLOW 1 — "Tell us an incident". What happened, read back
    hedged: what was described, what it may involve, the facts
    actually present, what is still missing, considered next steps
    and the urgency adapter's answer. No court stage is matched here;
    that question belongs to /api/case-companion/ask."""
    description = " ".join((req.description or "").split())
    if not description:
        raise HTTPException(status_code=400, detail="Nothing to analyze.")

    if len(req.description) > MAX_INPUT_CHARS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"That description is too long to analyze in one go "
                f"({len(req.description)} characters; the limit is "
                f"{MAX_INPUT_CHARS})."
            ),
        )

    if req.target_lang not in SUPPORTED_TARGET_LANGS:
        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported target_lang. Supported: "
                + ", ".join(SUPPORTED_TARGET_LANGS)
                + "."
            ),
        )

    state = CONVERSATIONS.ensure(req.conversation_id)
    conversation_id = state["conversation_id"]

    # Facts established earlier in this conversation still count — a
    # second, shorter message does not lose the date the first one gave.
    merged_facts = dict(CONVERSATIONS.known_facts(conversation_id))
    for key, value in (req.known_facts or {}).items():
        if value is None or not str(value).strip():
            continue
        merged_facts[str(key)[:120]] = str(value)[:500]

    # ...and so does the earlier *story*: "It happened yesterday" is
    # analyzed with the account it refers to, not on its own. Only a
    # conversation already on the incident intent contributes — a case
    # question asked in the same chat is not part of this incident.
    prior = (
        _prior_incident_text(state, description)
        if state.get("current_intent") == "incident_analysis"
        else ""
    )

    try:
        result = analyze_incident(
            req.description,
            known_facts=merged_facts,
            prior_description=prior,
            language=(req.language or "en")[:20],
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Nothing to analyze.")

    CONVERSATIONS.record(
        conversation_id,
        role="user",
        content=description,
        current_intent="incident_analysis",
    )
    CONVERSATIONS.record(
        conversation_id,
        role="assistant",
        content=result["possible_issue"],
        current_intent="incident_analysis",
        incident_category=(result.get("incident_category") or {}).get("id"),
        known_facts=_remembered_facts(result),
    )

    if req.target_lang != "eng_Latn":
        _translate_analysis(result, req.target_lang)

    result["translated_response"] = _compose_analysis_summary(
        result, req.target_lang
    )
    result["conversation_id"] = conversation_id
    result["language"] = req.target_lang

    log_access(
        "/api/incident/analyze",
        f"chars={len(description)} "
        f"category={(result.get('incident_category') or {}).get('id')} "
        f"classification={result['classification']['source']} "
        f"urgency={result['urgency'].get('status')} "
        f"confidence={result['confidence']['level']} "
        f"lang={req.target_lang} warnings={len(result['warnings'])}",
    )

    return result


@app.post("/api/case-companion/ask")
def case_companion_ask_endpoint(
    req: CaseCompanionAskRequest,
    auth=Depends(verify_api_key),
):
    """WORKFLOW 2 — "Ask about your case". A question about a case,
    answered only from the case information supplied with it — and,
    where that information does not cover the question, said to be
    absent rather than filled in. The existing guidance engine is
    reused for the stage the case record states."""
    question = " ".join((req.question or "").split())
    if not question:
        raise HTTPException(status_code=400, detail="Nothing to answer.")

    if len(req.question) > MAX_INPUT_CHARS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"That question is too long ({len(req.question)} "
                f"characters; the limit is {MAX_INPUT_CHARS})."
            ),
        )

    if req.target_lang not in SUPPORTED_TARGET_LANGS:
        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported target_lang. Supported: "
                + ", ".join(SUPPORTED_TARGET_LANGS)
                + "."
            ),
        )

    context = req.case_context if isinstance(req.case_context, dict) else {}
    try:
        context_size = len(json.dumps(context, default=str))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="case_context could not be read.")

    if context_size > CASE_CONTEXT_MAX_CHARS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"That case information is too large for one question "
                f"({context_size} characters; the limit is "
                f"{CASE_CONTEXT_MAX_CHARS}). Send the relevant sections."
            ),
        )

    state = CONVERSATIONS.ensure(req.conversation_id)
    conversation_id = state["conversation_id"]

    result = answer_case_question(question, context)

    CONVERSATIONS.record(
        conversation_id,
        role="user",
        content=question,
        current_intent="case_companion",
    )
    CONVERSATIONS.record(
        conversation_id,
        role="assistant",
        content=result["answer"],
        current_intent="case_companion",
    )

    if req.target_lang != "eng_Latn":
        _translate_companion(result, req.target_lang)

    result["conversation_id"] = conversation_id
    result["language"] = req.target_lang

    log_access(
        "/api/case-companion/ask",
        f"chars={len(question)} type={result['question_type']} "
        f"grounded={result['grounded']} context_keys={len(context)} "
        f"lang={req.target_lang}",
    )

    return result


# ---------------------------------------------------------------------------
# WHAT HAPPENED? - the case and incident companion.
#
# One endpoint for the whole feature: incident mode reads what somebody
# says happened to them, case mode answers a question from the case
# record the client sends with it. Both return the same envelope, hold
# their conversation state in memory, and only ever assert what the
# request actually carried - no sections, dates, outcomes or reasons
# are invented here. The reasoning lives in what_happened_service.py
# (pure Python, covered by test_what_happened.py); this function is the
# wiring, the API-key check and the translation.
# ---------------------------------------------------------------------------


class WhatHappenedRequest(BaseModel):
    mode: str
    text: str = ""
    language: str = "en"
    case_id: str | None = None
    conversation_id: str | None = None
    case_context: dict | None = None


def _what_happened_translate(text: str, language: str) -> str:
    """English response prose into the language the user picked, through
    the same IndicTrans2 checkpoint /api/translate already uses."""
    with _loaded("en_indic"):
        return translate(text, LANG_CODE_MAP[language])


@app.post("/api/what-happened")
def what_happened_endpoint(
    req: WhatHappenedRequest,
    auth=Depends(verify_api_key),
):
    """Answer one turn of the "What Happened?" conversation.

    Request:  mode ("incident" | "case"), text, language (en | hi | mr),
              optional case_id / conversation_id, and - for case mode -
              `case_context`, the frontend's snapshot of the Case record.

    Response: the structured envelope documented in
              what_happened_service.py, already in `language`.
    """
    try:
        result = what_happened.handle_request(
            {
                "mode": req.mode,
                "text": req.text,
                "language": req.language,
                "case_id": req.case_id,
                "conversation_id": req.conversation_id,
                "case_context": req.case_context,
            },
            translator=_what_happened_translate,
        )
    except what_happened.WhatHappenedError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    log_access(
        "/api/what-happened",
        f"mode={req.mode} language={req.language} "
        f"chars={len(req.text or '')} "
        f"conversation={result.get('conversation_id', '-')} "
        f"stage={result.get('matched_stage') or '-'}",
    )

    return result


@app.get("/health")
def health_check():
    return {"status": "ok", "model_loaded": model is not None}


# ---------------------------------------------------------------------------
# Nothing that escapes a route reaches the caller as a traceback. The
# traceback is logged here, where it is useful; the client gets one
# stable sentence. (Route-level handlers above still answer with their
# own specific, safe messages — this only catches what they do not.)
# ---------------------------------------------------------------------------

@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):  # noqa: ANN001
    logging.getLogger("nyaymitra").exception(
        "unhandled error on %s %s: %r",
        request.method,
        request.url.path,
        exc,
    )

    return JSONResponse(
        status_code=500,
        content={
            "detail": "Something went wrong on the server. Please try again."
        },
    )
