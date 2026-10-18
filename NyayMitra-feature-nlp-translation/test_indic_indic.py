import torch
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
from IndicTransToolkit.processor import IndicProcessor


def use_legacy_cache(model):
    """Keep IndicTrans2 on the tuple cache its own code expects.

    Same shim translate_service applies: transformers >= 4.36 hands
    generate() a pre-created dynamic cache whose layers are still None,
    and IndicTrans2's remote modelling code does `past_key_values[0][0]`
    on the first decode step. Reporting the model as not supporting the
    default cache leaves `past_key_values=None` and the model manages
    the legacy tuple cache itself. Without this, generate() raises
    AttributeError.
    """
    model.__class__._supports_default_dynamic_cache = classmethod(
        lambda cls: False
    )
    return model


DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

src_lang, tgt_lang = "mar_Deva", "hin_Deva"
model_name = "ai4bharat/indictrans2-indic-indic-dist-320M"

print(f"Loading {model_name} on {DEVICE}...")
tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
model = use_legacy_cache(
    AutoModelForSeq2SeqLM.from_pretrained(
        model_name, trust_remote_code=True
    ).to(DEVICE)
)
model.eval()
print("Model loaded.\n")

ip = IndicProcessor(inference=True)

input_sentences = [
    "माझा खटला जिल्हा न्यायालयात सुरू आहे",
    "पुढील सुनावणी पंधरा सप्टेंबर रोजी आहे",
]

batch = ip.preprocess_batch(input_sentences, src_lang=src_lang, tgt_lang=tgt_lang)
inputs = tokenizer(batch, truncation=True, padding="longest", return_tensors="pt").to(DEVICE)

with torch.no_grad():
    generated_tokens = model.generate(**inputs, max_length=256, num_beams=5)

decoded = tokenizer.batch_decode(generated_tokens, skip_special_tokens=True, clean_up_tokenization_spaces=True)
translations = ip.postprocess_batch(decoded, lang=tgt_lang)

print("----- RESULTS -----")
for src, tgt in zip(input_sentences, translations):
    print(f"MR: {src}")
    print(f"HI: {tgt}")
    print()
