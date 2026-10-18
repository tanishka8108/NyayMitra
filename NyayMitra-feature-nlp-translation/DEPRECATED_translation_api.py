import os
import secrets

from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from translation_service import translate_with_glossary


# --------------------------------------------------
# Configuration
# --------------------------------------------------

API_KEY = os.getenv("NYAYMITRA_API_KEY")

if not API_KEY:
    raise RuntimeError("NYAYMITRA_API_KEY is not configured.")


# --------------------------------------------------
# FastAPI
# --------------------------------------------------

app = FastAPI(
    title="NyayMitra Translation API",
    description="Authenticated translation service for NyayMitra",
    version="1.0.0"
)


# --------------------------------------------------
# Request model
# --------------------------------------------------

class TranslationRequest(BaseModel):
    case_id: str = Field(
        ...,
        min_length=1
    )

    text: str = Field(
        ...,
        min_length=1
    )

    source_language: str = "eng_Latn"

    target_language: str = "hin_Deva"


# --------------------------------------------------
# Authentication
# --------------------------------------------------

def authenticate(
    authorization: Optional[str]
):

    if not authorization:

        raise HTTPException(
            status_code=401,
            detail="Authentication required."
        )

    if not authorization.startswith("Bearer "):

        raise HTTPException(
            status_code=401,
            detail="Invalid authentication format."
        )

    provided_key = authorization[
        len("Bearer "):
    ]

    if not secrets.compare_digest(provided_key, API_KEY):

        raise HTTPException(
            status_code=401,
            detail="Invalid API key."
        )


# --------------------------------------------------
# Root endpoint
# --------------------------------------------------

@app.get("/")
def root():

    return {
        "service": "NyayMitra Translation API",
        "status": "running",
        "authentication": "required"
    }


# --------------------------------------------------
# Translation endpoint
# --------------------------------------------------

@app.post("/translate")
def translate_endpoint(
    request: TranslationRequest,
    authorization: Optional[str] = Header(default=None)
):

    # Authentication is checked BEFORE translation.
    authenticate(authorization)

    result = translate_with_glossary(
        text=request.text,
        source_language=request.source_language,
        target_language=request.target_language
    )

    return {
        "case_id": request.case_id,
        "source_language": request.source_language,
        "target_language": request.target_language,
        "original_text": request.text,
        "translated_text": result["translated_text"],
        "glossary_matches": result["glossary_matches"]
    }
