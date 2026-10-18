import json
import re
from pathlib import Path

import torch
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
from IndicTransToolkit.processor import IndicProcessor


# --------------------------------------------------
# Configuration
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

GLOSSARY_PATH = BASE_DIR / "glossary_v1.json"

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

MODEL_NAME = "ai4bharat/indictrans2-en-indic-dist-200M"


# --------------------------------------------------
# IndicTrans2 setup
# --------------------------------------------------

ip = IndicProcessor(inference=True)

_tokenizer = None
_model = None


def load_model():
    """
    Load IndicTrans2 model only when first required.
    """

    global _tokenizer
    global _model

    if _tokenizer is None or _model is None:

        print(f"Loading IndicTrans2 on {DEVICE}...")

        _tokenizer = AutoTokenizer.from_pretrained(
            MODEL_NAME,
            trust_remote_code=True
        )

        _model = AutoModelForSeq2SeqLM.from_pretrained(
            MODEL_NAME,
            trust_remote_code=True
        ).to(DEVICE)

        _model.eval()

        print("IndicTrans2 model loaded.")


# --------------------------------------------------
# Glossary
# --------------------------------------------------

def load_glossary():

    with open(
        GLOSSARY_PATH,
        "r",
        encoding="utf-8"
    ) as f:

        data = json.load(f)

    return data.get("glossary_v1", [])


GLOSSARY = load_glossary()


# --------------------------------------------------
# Translation
# --------------------------------------------------

def translate(
    text: str,
    source_language: str,
    target_language: str
) -> str:

    load_model()

    batch = ip.preprocess_batch(
        [text],
        src_lang=source_language,
        tgt_lang=target_language
    )

    inputs = _tokenizer(
        batch,
        padding=True,
        truncation=True,
        return_tensors="pt"
    ).to(DEVICE)

    with torch.no_grad():

        generated = _model.generate(
            **inputs,
            max_length=256,
            num_beams=5
        )

    decoded = _tokenizer.batch_decode(
        generated,
        skip_special_tokens=True,
        clean_up_tokenization_spaces=True
    )

    result = ip.postprocess_batch(
        decoded,
        lang=target_language
    )

    return result[0]


# --------------------------------------------------
# Glossary matching
# --------------------------------------------------

def find_glossary_matches(text: str):

    matches = []

    text_lower = text.lower()

    for entry in GLOSSARY:

        term = entry["formal_term"]

        if term.lower() in text_lower:

            matches.append(entry)

    return matches


# --------------------------------------------------
# Get translated glossary explanation
# --------------------------------------------------

def get_glossary_explanation(
    entry,
    target_language: str
):

    if target_language == "hin_Deva":

        return entry.get(
            "plain_explanation_hi",
            entry.get("plain_explanation_en")
        )

    if target_language == "mar_Deva":

        return entry.get(
            "plain_explanation_mr",
            entry.get("plain_explanation_en")
        )

    return entry.get("plain_explanation_en")


# --------------------------------------------------
# Complete translation operation
# --------------------------------------------------

def translate_with_glossary(
    text: str,
    source_language: str,
    target_language: str
):

    translated_text = translate(
        text,
        source_language,
        target_language
    )

    matches = find_glossary_matches(text)

    glossary_results = []

    for entry in matches:

        glossary_results.append({
            "term_id": entry["term_id"],
            "formal_term": entry["formal_term"],
            "category": entry["category"],
            "explanation": get_glossary_explanation(
                entry,
                target_language
            )
        })

    return {
        "translated_text": translated_text,
        "glossary_matches": glossary_results
    }
