"""
Missing-information detector (pure logic, no ML).

Takes the full expected fact list for a category from
data/raw/incident_facts.json and subtracts the facts that
src/fact_extractor.py actually found, so the caller can prompt the user for
the rest. Anything the extractor could not verify stays on this list - we
never assume a fact is present.
"""

from __future__ import annotations

from incident_data import expected_facts


def get_missing_info(category_id: str, extracted_facts: dict | None) -> list:
    """Facts still missing for `category_id`.

    Args:
        category_id: e.g. "INC001" (unknown categories yield []).
        extracted_facts: output of fact_extractor.extract_facts(), or None.

    Returns:
        Ordered list of fact_or_entity names that were expected but not found.
    """
    if not category_id:
        return []

    expected = expected_facts(category_id)
    if not expected:
        return []

    found = extracted_facts or {}
    return [fact for fact in expected if fact not in found]
