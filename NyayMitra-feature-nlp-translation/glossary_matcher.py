import json
import re
from pathlib import Path

GLOSSARY_PATH = Path(__file__).with_name("glossary_v1.json")


def load_glossary():
    with open(GLOSSARY_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["glossary_v1"]


def find_glossary_matches(text: str):
    if not text or not text.strip():
        return []

    matches = []
    text_lower = text.lower()

    for entry in load_glossary():
        term = entry["formal_term"]
        pattern = r"(?<!\w)" + re.escape(term.lower()) + r"(?!\w)"

        if re.search(pattern, text_lower):
            matches.append({
                "term_id": entry["term_id"],
                "formal_term": entry["formal_term"],
                "category": entry["category"],
                "plain_explanation_en": entry["plain_explanation_en"],
                "plain_explanation_hi": entry["plain_explanation_hi"],
                "plain_explanation_mr": entry["plain_explanation_mr"],
            })

    return matches
