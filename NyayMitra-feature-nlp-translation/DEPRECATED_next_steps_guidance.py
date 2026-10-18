import re


GUIDANCE_RULES = [
    {
        "rule_id": "NS001",
        "case_stage": "Adjourned",
        "keywords": ["adjourned", "postponed"],
        "meaning": "The hearing has been postponed to a later date.",
        "suggested_action": "Check the case record for the next hearing date and any instructions from the court.",
        "urgency": "medium",
    },
    {
        "rule_id": "NS002",
        "case_stage": "Part-heard",
        "keywords": ["part-heard", "part heard"],
        "meaning": "The court has started hearing the case but the hearing is not yet complete.",
        "suggested_action": "Check the next hearing date and prepare for the continuation of the hearing.",
        "urgency": "medium",
    },
    {
        "rule_id": "NS003",
        "case_stage": "Listed for arguments",
        "keywords": ["listed for arguments"],
        "meaning": "The case is scheduled for lawyers to present their arguments before the court.",
        "suggested_action": "Check the hearing date and ensure the required documents and legal representation are ready.",
        "urgency": "high",
    },
    {
        "rule_id": "NS004",
        "case_stage": "Disposed of",
        "keywords": ["disposed of", "disposed"],
        "meaning": "The court has concluded or disposed of the case.",
        "suggested_action": "Check the final order or judgment and verify whether any further action is required.",
        "urgency": "medium",
    },
    {
        "rule_id": "NS005",
        "case_stage": "Dismissed for default",
        "keywords": ["dismissed for default", "dismissed in default"],
        "meaning": "The case was dismissed because a required person did not appear or a required step was not completed.",
        "suggested_action": "Check the order for the reason for dismissal and promptly ask a lawyer about possible remedies or further steps.",
        "urgency": "high",
    },
    {
        "rule_id": "NS006",
        "case_stage": "Ex parte",
        "keywords": ["ex parte"],
        "meaning": "The matter was considered when the other side was not present.",
        "suggested_action": "Read the court order carefully and consult a lawyer if you believe the absence affected the case.",
        "urgency": "high",
    },
    {
        "rule_id": "NS007",
        "case_stage": "Interim order",
        "keywords": ["interim order"],
        "meaning": "The court has made a temporary order that applies until further orders or the final decision.",
        "suggested_action": "Read the conditions and duration of the interim order and make sure any required compliance is completed.",
        "urgency": "high",
    },
    {
        "rule_id": "NS008",
        "case_stage": "Stay",
        "keywords": ["stay granted", "stay"],
        "meaning": "The court has ordered that a particular action or proceeding be paused.",
        "suggested_action": "Check exactly what has been stayed and until when, and follow any conditions in the order.",
        "urgency": "high",
    },
    {
        "rule_id": "NS009",
        "case_stage": "Notice issued",
        "keywords": ["notice issued"],
        "meaning": "The court has formally issued notice to another party.",
        "suggested_action": "Check the case record for the notice status, response requirements, and next hearing date.",
        "urgency": "medium",
    },
    {
        "rule_id": "NS010",
        "case_stage": "Notice returned unserved",
        "keywords": ["returned unserved"],
        "meaning": "The attempt to officially deliver the notice was unsuccessful.",
        "suggested_action": "Check the order for the next direction regarding service of notice.",
        "urgency": "medium",
    },
    {
        "rule_id": "NS011",
        "case_stage": "Appeal admitted",
        "keywords": ["appeal admitted"],
        "meaning": "The higher court has agreed to formally consider the appeal.",
        "suggested_action": "Check the next hearing date and any documents or submissions required for the appeal.",
        "urgency": "medium",
    },
    {
        "rule_id": "NS012",
        "case_stage": "Not maintainable",
        "keywords": ["not maintainable"],
        "meaning": "The court has determined that the case or application cannot proceed in its current form.",
        "suggested_action": "Read the order to understand the reason and consult a lawyer about available options.",
        "urgency": "high",
    },
]


DISCLAIMER = (
    "This guidance is for general information only and is not legal advice. "
    "Check the court order and consult a qualified lawyer for case-specific advice."
)


def normalize_text(text: str) -> str:
    """Normalize text for reliable rule matching."""
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text


def find_matching_rule(status_text: str):
    """Return the first rule matching the supplied case-status text."""
    normalized = normalize_text(status_text)

    for rule in GUIDANCE_RULES:
        for keyword in rule["keywords"]:
            if keyword in normalized:
                return rule

    return None


def get_next_steps(status_text: str):
    """Generate next-step guidance from a case-status text."""
    rule = find_matching_rule(status_text)

    if rule is None:
        return {
            "matched": False,
            "rule_id": None,
            "case_stage": "Unknown",
            "meaning": "The case status could not be matched to a known guidance rule.",
            "suggested_action": "Check the original court record or order for more information.",
            "urgency": "unknown",
            "disclaimer": DISCLAIMER,
        }

    return {
        "matched": True,
        "rule_id": rule["rule_id"],
        "case_stage": rule["case_stage"],
        "meaning": rule["meaning"],
        "suggested_action": rule["suggested_action"],
        "urgency": rule["urgency"],
        "disclaimer": DISCLAIMER,
    }


def print_guidance(status_text: str):
    """Print guidance in a human-readable format."""
    result = get_next_steps(status_text)

    print("\n===== NyayMitra Next-Steps Guidance =====")
    print("Input:", status_text)
    print("Matched:", result["matched"])
    print("Rule ID:", result["rule_id"])
    print("Case Stage:", result["case_stage"])
    print("Meaning:", result["meaning"])
    print("Suggested Action:", result["suggested_action"])
    print("Urgency:", result["urgency"])
    print("Disclaimer:", result["disclaimer"])


if __name__ == "__main__":
    test_statuses = [
        "Case adjourned",
        "Case listed for arguments",
        "Case disposed of",
        "Matter dismissed for default",
        "Notice returned unserved",
        "Some unknown case status",
    ]

    for status in test_statuses:
        print_guidance(status)
