import torch
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
from IndicTransToolkit.processor import IndicProcessor

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
EN_INDIC_MODEL = "ai4bharat/indictrans2-en-indic-dist-200M"
ip = IndicProcessor(inference=True)


def use_legacy_cache(model):
    """The shim translate_service applies — see _use_legacy_cache there.

    IndicTrans2's remote modelling code predates transformers' dynamic
    cache and reads `past_key_values[0][0]` on the first decode step,
    when the layers are still None. Reporting the model as not
    supporting the default cache leaves `past_key_values=None` so the
    model manages the legacy tuple cache itself. Without it generate()
    raises AttributeError.
    """
    model.__class__._supports_default_dynamic_cache = classmethod(
        lambda cls: False
    )
    return model


def load(model_name):
    tok = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    model = use_legacy_cache(
        AutoModelForSeq2SeqLM.from_pretrained(
            model_name, trust_remote_code=True
        ).to(DEVICE)
    )
    model.eval()
    return tok, model

def translate(sentences, src_lang, tgt_lang, tok, model):
    batch = ip.preprocess_batch(sentences, src_lang=src_lang, tgt_lang=tgt_lang)
    inputs = tok(batch, padding=True, truncation=True, return_tensors="pt").to(DEVICE)
    with torch.no_grad():
        generated = model.generate(**inputs, max_length=256, num_beams=5)
    decoded = tok.batch_decode(generated, skip_special_tokens=True, clean_up_tokenization_spaces=True)
    return ip.postprocess_batch(decoded, lang=tgt_lang)

PHRASE_CATEGORIES = {
    "Adjournment / Postponement": [
        "Matter adjourned sine die",
        "Case adjourned for want of time",
        "Matter adjourned at the request of counsel",
        "Case adjourned due to non-availability of judge",
    ],
    "Hearing / Listing": [
        "Case listed for arguments",
        "Matter listed for admission",
        "Case listed for final disposal",
        "Matter part-heard",
        "Case coming up for final hearing on 15.09.2026",
        "Matter listed under miscellaneous",
        "Case listed before the Registrar",
        "Matter fixed for hearing on merits",
    ],
    "Orders / Judgments": [
        "Interim order granted, next date for compliance",
        "Order reserved",
        "Judgment reserved",
        "Case disposed of",
        "Matter dismissed for default",
        "Matter dismissed in default of appearance",
        "Order passed, matter closed",
        "Case decided ex parte",
        "Application for stay rejected",
        "Stay granted till next date of hearing",
        "Interim relief declined",
    ],
    "Notice / Service": [
        "Notice issued to respondent",
        "Notice returned unserved",
        "Service of summons awaited",
        "Notice issued, returnable in four weeks",
        "Fresh notice ordered to be issued",
    ],
    "Transfer / Bench": [
        "Matter transferred to another bench",
        "Case transferred for want of jurisdiction",
        "Matter withdrawn and re-filed",
        "Case transferred to district court",
    ],
    "Filing / Procedural": [
        "Application for condonation of delay pending",
        "Vakalatnama not filed",
        "Written statement not filed",
        "Rejoinder to be filed within two weeks",
        "Matter awaiting counter affidavit",
        "Case remanded for fresh consideration",
        "Case restored to file",
    ],
    "Appeal / Review": [
        "Appeal admitted",
        "Appeal dismissed as withdrawn",
        "Review petition pending",
        "Revision petition disposed of",
        "Second appeal not maintainable",
    ],
    "Bail / Custody": [
        "Bail application allowed",
        "Anticipatory bail rejected",
        "Accused released on bail with conditions",
        "Custody remand extended",
    ],
    "Execution / Compliance": [
        "Execution petition pending",
        "Compliance report to be filed within thirty days",
    ],
}

LANG_TARGETS = [("hin_Deva", "Hindi"), ("mar_Deva", "Marathi")]

if __name__ == "__main__":
    print("Device:", DEVICE)
    tok, model = load(EN_INDIC_MODEL)
    output_lines = []
    for category, phrases in PHRASE_CATEGORIES.items():
        header = f"\n===== {category} ====="
        print(header)
        output_lines.append(header)
        for tgt_lang, lang_name in LANG_TARGETS:
            translations = translate(phrases, "eng_Latn", tgt_lang, tok, model)
            for eng, trans in zip(phrases, translations):
                line = f"[{lang_name}] EN: {eng}\n        -> {trans}"
                print(line)
                output_lines.append(line)
    with open("translation_output.txt", "w", encoding="utf-8") as f:
        f.write("\n\n".join(output_lines))
    print("\nSaved all translations to translation_output.txt")
    print(f"Total phrases tested: {sum(len(v) for v in PHRASE_CATEGORIES.values())}")
