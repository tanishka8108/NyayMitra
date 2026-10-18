"""
Guidance lookup module - reads next_steps_guidance_v2.json and cross-
references glossary_v2.json to surface related legal-term explanations
alongside each guidance result.
"""

import json
import os

GUIDANCE_FILE = os.path.join(os.path.dirname(__file__), "next_steps_guidance_v2.json")
GLOSSARY_FILE = os.path.join(os.path.dirname(__file__), "glossary_v2.json")


def load_guidance_data():
    with open(GUIDANCE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_glossary_data():
    with open(GLOSSARY_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def find_related_glossary_terms(text: str) -> list:
    """
    Scans a piece of text for any known glossary term appearing as a
    substring (case-insensitive). Returns matched glossary entries.
    """
    glossary = load_glossary_data()
    text_lower = text.lower()
    matches = []

    for entry in glossary["glossary_v1"]:
        term = entry["formal_term"].lower()
        if term in text_lower:
            matches.append({
                "term_id": entry["term_id"],
                "formal_term": entry["formal_term"],
                "plain_explanation_en": entry["plain_explanation_en"],
                "plain_explanation_hi": entry.get("plain_explanation_hi"),
                "plain_explanation_mr": entry.get("plain_explanation_mr"),
            })

    return matches


def get_next_steps(case_stage: str) -> dict:
    """
    Looks up guidance for a given case stage, and attaches any glossary
    terms found in the case stage text or its description.
    """
    data = load_guidance_data()
    normalized_input = " ".join(case_stage.strip().split()).lower()

    for rule in data["guidance_v2"]:
        normalized_rule = " ".join(rule["case_stage"].strip().split()).lower()
        if normalized_rule == normalized_input:
            combined_text = f"{rule['case_stage']} {rule['description']}"
            related_terms = find_related_glossary_terms(combined_text)

            return {
                "matched": True,
                "guidance_id": rule["guidance_id"],
                "case_stage": rule["case_stage"],
                "description": rule["description"],
                "suggested_action": rule["suggested_action"],
                "urgency": rule["urgency"],
                "language": data["language"],
                "disclaimer": data["disclaimer"],
                "related_glossary_terms": related_terms,
            }

    return {
        "matched": False,
        "case_stage": case_stage,
        "disclaimer": data["disclaimer"],
    }
