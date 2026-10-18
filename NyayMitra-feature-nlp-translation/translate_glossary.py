"""
Reads glossary_v1.json and adds Hindi/Marathi translations for each
term's plain-English explanation, using the live /api/translate endpoint.
Saves the result as glossary_v2.json (v1 stays untouched as a backup).
"""
import json
import time
import requests

API_KEY = "nyaymitra-local-test-2026"
HEADERS = {"Authorization": f"Bearer {API_KEY}"}
TRANSLATE_URL = "http://localhost:8001/api/translate"


def translate_text(text: str, target_lang: str) -> str:
    response = requests.post(
        TRANSLATE_URL,
        headers=HEADERS,
        json={"case_id": "glossary-refine", "source_text": text, "target_lang": target_lang},
        timeout=30,
    )
    if response.status_code == 200:
        return response.json()["translated_text"]
    else:
        print(f"  WARNING: translation failed for '{text[:40]}...': {response.text}")
        return None


def main():
    with open("glossary_v1.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    terms = data["glossary_v1"]
    print(f"Translating {len(terms)} glossary terms into Hindi and Marathi...\n")

    for i, entry in enumerate(terms, start=1):
        explanation = entry["plain_explanation_en"]
        print(f"[{i}/{len(terms)}] {entry['formal_term']}")

        entry["plain_explanation_hi"] = translate_text(explanation, "hi")
        entry["plain_explanation_mr"] = translate_text(explanation, "mr")

        time.sleep(0.2)  # be gentle on the local model, avoid overload

    with open("glossary_v2.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\nDone. Saved to glossary_v2.json")


if __name__ == "__main__":
    main()
