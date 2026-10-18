# -*- coding: utf-8 -*-
"""
Tests for the "What Happened?" case and incident companion.

Everything here runs without torch, FastAPI or a single checkpoint:
the orchestration in `what_happened_service.py` takes its model work
(translation, ASR output, guidance) as plain inputs, so the reasoning
itself can be tested on any machine. The live endpoints are exercised
separately by e2e_check.py when the service is running.

    python -u test_what_happened.py
    pytest -q test_what_happened.py

Covers, per the feature brief:

  INCIDENT  english / hindi / marathi / ambiguous / empty / very long /
            missing information / no guidance match
  CASE      status / last hearing / next hearing / latest order /
            next steps / missing record / follow-up
  VOICE     en / hi / mr transcripts, transcript editing,
            voice -> response, speakable answer
  LANGUAGE  en->en, en->hi, en->mr, hi->en, hi->mr, mr->en, mr->hi,
            and names / dates / CNRs / case numbers never changing
"""

import os
import re
import sys
from datetime import date, timedelta

from guidance_match import load_guidance_data, match_guidance
from next_steps_guidance_lookup import get_next_steps
from what_happened_service import (
    ConversationStore,
    FactPreservationError,
    WhatHappenedError,
    analyse_incident,
    answer_case_question,
    detect_case_intent,
    detect_incident_category,
    extract_protected_spans,
    glossary_terms_for,
    handle_request,
    mask_protected_spans,
    translate_preserving_facts,
    unmask_protected_spans,
)

HERE = os.path.dirname(os.path.abspath(__file__))

# The prose every reply carries. Numeric sections must never appear in
# it: which section applies is a lawyer's call on real facts.
SECTION_RE = re.compile(r"\bSection\s+\d+|\bSection[s]?\s+\d+")

ENGLISH_INCIDENT = (
    "Someone called me pretending to be from my bank and asked for "
    "my OTP. I gave it and money was deducted."
)

HINDI_INCIDENT = (
    "किसी ने बैंक का अधिकारी बनकर ओटीपी मांगा और मेरे खाते से पैसे कट गए।"
)

MARATHI_INCIDENT = (
    "कोणीतरी बँकेचे अधिकारी सांगून ओटीपी मागला आणि खात्यातून पैसे कापले गेले."
)

# Deterministic stand-in for IndicTrans2. It scrambles words the way a
# model might, but leaves the NM<i>X fact tokens alone — which is what
# a real model does with digits.
def fake_translate(text, language):
    scrambled = " ".join(
        word[::-1] if word.isalpha() else word
        for word in str(text).split()
    )
    return f"[{language}] {scrambled}"


def ask(**kwargs):
    """One request, one private conversation store."""
    payload = {"mode": "incident", "text": "", "language": "en"}
    payload.update(kwargs)
    return handle_request(
        payload,
        translator=kwargs.pop("translator", None)
        if "translator" in kwargs
        else None,
        guidance_fn=kwargs.pop("guidance_fn", None)
        if "guidance_fn" in kwargs
        else None,
        case_guidance_fn=kwargs.pop("case_guidance_fn", None)
        if "case_guidance_fn" in kwargs
        else None,
        store=kwargs.pop("store", None) or ConversationStore(),
    )


def make_case(**overrides):
    """A case snapshot with dates relative to today, so the assertions
    do not rot as the calendar moves."""
    today = date.today()
    past = (today - timedelta(days=30)).isoformat()
    upcoming = (today + timedelta(days=12)).isoformat()

    case = {
        "cnr_number": "PBASB00008022024",
        "case_type": "CS - CIVIL SUIT",
        "court_name": "Civil Judge Senior Division, Baba Bakala",
        "current_case_stage": "Arguments",
        "next_hearing_date": upcoming,
        "filing_date": (today - timedelta(days=400)).isoformat(),
        "filing_number": "790/2024",
        "registration_number": "476/2024",
        "presiding_judge": "5-Civil Judge (Junior Division)",
        "petitioner_name": "Asha Verma",
        "petitioner_advocate": "Vijay Kumar",
        "respondents_list": ["Prabhjot Kaur", "Hazara Singh"],
        "applied_act": "Code of Civil Procedure",
        "applied_section": "Order 21 Rule 11",
        "case_history_timeline": [
            {
                "judge_title": "Civil Judge (Junior Division)",
                "business_on_date": past,
                "hearing_date": upcoming,
                "purpose_of_hearing": "Arguments",
            },
            {
                "judge_title": "Civil Judge (Junior Division)",
                "business_on_date": (today - timedelta(days=60)).isoformat(),
                "hearing_date": past,
                "purpose_of_hearing": "Replication",
            },
        ],
    }
    case.update(overrides)
    return case


def prose(response):
    """Every human-readable string in a response, for one regex sweep."""
    parts = [
        response.get("acknowledgement", ""),
        response.get("summary", ""),
        response.get("possible_issue", ""),
        response.get("explanation", ""),
        response.get("time_sensitivity_note", ""),
    ]
    for field in (
        "case_facts",
        "record_gaps",
        "next_steps",
        "preserve_information",
        "follow_up_questions",
        "warnings",
    ):
        parts.extend(str(item) for item in response.get(field) or [])
    return "\n".join(parts)


# ===========================================================================
# INCIDENT MODE
# ===========================================================================


def test_incident_english():
    response = ask(text=ENGLISH_INCIDENT, language="en")

    assert response["mode"] == "incident"
    assert response["language"] == "en"
    assert response["conversation_id"].startswith("c_")

    assert response["summary"].strip()
    assert response["possible_issue"].strip()
    assert response["explanation"].strip()
    assert response["next_steps"]
    assert response["preserve_information"]
    assert response["follow_up_questions"]
    assert isinstance(response["warnings"], list)

    assert "may indicate" in response["possible_issue"]
    assert "not a substitute" in response["disclaimer"]
    assert not SECTION_RE.search(prose(response)), "no section invented"

    category, _ranked = detect_incident_category(ENGLISH_INCIDENT)
    assert category is not None and category["id"] == "otp_bank_fraud"
    print("PASS: english incident is structured, hedged and section-free.")


def test_incident_hindi():
    response = ask(text=HINDI_INCIDENT, language="hi")

    assert response["possible_issue"].strip()
    assert response["next_steps"]
    assert response["follow_up_questions"]
    # The Devanagari signals must reach the same category the English
    # ones do, even though the reply itself is written in English here
    # (no translator is injected in this test).
    assert "financial fraud" in response["possible_issue"]
    print("PASS: hindi incident reaches the same reading.")


def test_incident_marathi():
    response = ask(text=MARATHI_INCIDENT, language="mr")

    assert response["possible_issue"].strip()
    assert "financial fraud" in response["possible_issue"]
    assert response["preserve_information"]
    print("PASS: marathi incident reaches the same reading.")


def test_incident_ambiguous():
    response = ask(
        text="Something happened with the thing and the person.",
        language="en",
    )

    assert "does not contain enough detail" in response["summary"]
    assert "information given is insufficient" in response["possible_issue"]
    assert response["matched_stage"] is None
    assert any("too general" in item for item in response["warnings"])
    assert response["follow_up_questions"]
    print("PASS: ambiguous incident admits it cannot classify.")


def test_incident_empty_input():
    response = ask(text="", language="en")

    assert response["summary"] == "No description was provided."
    assert any("Nothing was written" in item for item in response["warnings"])
    assert response["follow_up_questions"]
    assert not response["next_steps"]
    print("PASS: empty input answers instead of crashing.")


def test_incident_very_long_input():
    response = ask(text="I was cheated. " * 900, language="en")

    assert any(
        "Only the first" in item for item in response["warnings"]
    ), "truncation is declared"
    assert len(response["summary"]) < 700, "reply does not echo the paste"
    print("PASS: very long input is read, capped and declared.")


def test_incident_missing_information():
    response = ask(
        text="Someone took something from me and I do not know what to do.",
        language="en",
    )

    assert response["follow_up_questions"], "asks for what is missing"
    assert any(
        "Tell a little more" in step for step in response["next_steps"]
    ), "says plainly that more is needed"
    assert response["possible_issue"].strip()
    print("PASS: missing information produces follow-up questions.")


def test_incident_no_guidance_match():
    response = ask(text=ENGLISH_INCIDENT, language="en")

    if response["guidance"] is not None:
        stages = {
            rule["case_stage"] for rule in load_guidance_data()["guidance_v2"]
        }
        assert response["matched_stage"] in stages, "stage must be real"
    else:
        assert response["matched_stage"] is None

    # Either way the category's own practical steps are present.
    assert len(response["next_steps"]) >= 2
    print("PASS: no guidance match invents no stage.")


def test_incident_guidance_match_reused():
    response = ask(
        text="My bail application was rejected yesterday and I do not "
        "know what to do next.",
        language="en",
    )

    assert response["guidance"] is not None
    assert response["guidance"]["matched"] is True
    assert "bail" in response["matched_stage"].lower()
    assert response["guidance"]["what_to_do_next"] in response["next_steps"]
    assert any(
        "guidance stage" in item for item in response["warnings"]
    ), "the match is labelled as a word match, not a finding"
    print("PASS: existing guidance set drives the next step.")


def test_incident_legal_language_is_explained():
    response = ask(
        text="The matter is adjourned sine die and I want to know what "
        "that means.",
        language="en",
    )

    assert response["matched_stage"] == "Matter adjourned sine die"
    terms = {item["term"] for item in response["legal_terms"]}
    assert "adjourned" in terms or "sine die" in terms
    print("PASS: legal language is answered through the glossary.")


# ===========================================================================
# CASE MODE
# ===========================================================================


def test_case_current_status():
    response = ask(
        mode="case",
        text="What is the current status of my case?",
        language="en",
        case_context=make_case(),
    )

    assert response["mode"] == "case"
    assert "Arguments" in response["explanation"]
    assert "available case record" in response["explanation"]
    assert response["case_facts"]
    assert not SECTION_RE.search(prose(response))
    print("PASS: status comes from the record.")


def test_case_last_hearing():
    context = make_case()
    past = context["case_history_timeline"][1]["hearing_date"]

    response = ask(
        mode="case",
        text="What happened in my last hearing?",
        language="en",
        case_context=context,
    )

    assert past in response["explanation"]
    assert "Replication" in response["explanation"]
    print("PASS: last hearing is the record's last completed entry.")


def test_case_next_hearing():
    context = make_case()
    upcoming = context["next_hearing_date"]

    response = ask(
        mode="case",
        text="When is my next hearing?",
        language="en",
        case_context=context,
    )

    assert upcoming in response["explanation"]
    assert "Arguments" in response["explanation"]
    assert response["time_sensitivity_note"]
    print("PASS: next hearing quotes the record's own date.")


def test_case_latest_order():
    response = ask(
        mode="case",
        text="What did the latest order say?",
        language="en",
        case_context=make_case(),
    )

    assert "does not include any court order" in response["explanation"]
    assert any(
        "No orders" in gap for gap in response["record_gaps"]
    )
    print("PASS: an absent order is reported, never invented.")


def test_case_why_postponed_never_invents_a_reason():
    response = ask(
        mode="case",
        text="Why was my hearing postponed?",
        language="en",
        case_context=make_case(),
    )

    assert "does not state the reason" in response["explanation"]
    lowered = response["explanation"].lower()
    for banned in ("because", "since the judge", "due to illness"):
        assert banned not in lowered, f"reason invented: {banned}"
    assert any("does not state why" in gap for gap in response["record_gaps"])
    print("PASS: a postponed hearing gets no invented reason.")


def test_case_next_steps():
    response = ask(
        mode="case",
        text="What should I do next?",
        language="en",
        case_context=make_case(),
    )

    assert response["matched_stage"], "stage drives the guidance"
    assert len(response["next_steps"]) >= 2
    stages = {rule["case_stage"] for rule in load_guidance_data()["guidance_v2"]}
    assert response["matched_stage"] in stages
    print("PASS: case next steps come from the guidance set.")


def test_case_missing_case_information():
    response = ask(
        mode="case",
        text="What is the status?",
        language="en",
    )

    assert any(
        "No case record was shared" in item for item in response["warnings"]
    )
    assert "Select your case" in response["explanation"]
    assert not response["case_facts"]
    assert any("No case record" in gap for gap in response["record_gaps"])
    print("PASS: no record means no case facts.")


def test_case_no_hearing_date_in_record():
    context = make_case(next_hearing_date="", case_history_timeline=[])

    response = ask(
        mode="case",
        text="When is my next hearing?",
        language="en",
        case_context=context,
    )

    assert "does not list a next hearing date" in response["explanation"]
    assert any("No next hearing date" in gap for gap in response["record_gaps"])
    print("PASS: an absent hearing date is not guessed.")


def test_case_follow_up_keeps_context():
    store = ConversationStore()

    first = ask(
        mode="case",
        text="What is the current status?",
        language="en",
        case_context=make_case(),
        store=store,
    )
    second = ask(
        mode="case",
        text="Yes.",
        language="en",
        case_context=make_case(),
        store=store,
        conversation_id=first["conversation_id"],
    )

    assert second["conversation_id"] == first["conversation_id"]
    assert second["acknowledgement"].strip()
    assert "When is my next hearing?" in second["follow_up_questions"]
    print("PASS: a short follow-up keeps the thread and repeats the ask.")


def test_case_intent_detection():
    assert detect_case_intent("When is my next hearing?") == "next_hearing"
    assert detect_case_intent("Why was it adjourned?") == "why_postponed"
    assert detect_case_intent("What documents do I need?") == "documents"
    assert detect_case_intent("What is the current status?") == "status"
    assert detect_case_intent("Hello there") == "overview"
    print("PASS: case questions are routed to the right answer.")


# ===========================================================================
# VOICE (transcripts arriving from the existing ASR pipeline)
# ===========================================================================


def test_voice_transcript_english():
    response = ask(
        text="Someone sent me a link and I clicked it and my money went.",
        language="en",
    )
    assert response["summary"].strip()
    assert response["next_steps"]
    print("PASS: english transcript becomes a response.")


def test_voice_transcript_hindi():
    response = ask(text=HINDI_INCIDENT, language="hi")
    assert response["possible_issue"].strip()
    print("PASS: hindi transcript becomes a response.")


def test_voice_transcript_marathi():
    response = ask(text=MARATHI_INCIDENT, language="mr")
    assert response["possible_issue"].strip()
    print("PASS: marathi transcript becomes a response.")


def test_voice_transcript_editing():
    """What is sent is what is read: the editable transcript is the
    input, so correcting an ASR mistake changes the answer."""
    raw = "Some one threatend me and demanded moneyy yesterday."
    edited = "Someone threatened me and demanded money yesterday."

    raw_response = ask(text=raw, language="en")
    edited_response = ask(text=edited, language="en")

    assert raw_response["summary"] != edited_response["summary"]
    assert "threat" in edited_response["possible_issue"].lower()
    print("PASS: an edited transcript is what gets analysed.")


def test_voice_to_response_turn():
    store = ConversationStore()
    first = ask(
        text=ENGLISH_INCIDENT,
        language="en",
        store=store,
    )
    follow_up = ask(
        text="It happened yesterday.",
        language="en",
        store=store,
        conversation_id=first["conversation_id"],
    )

    assert follow_up["acknowledgement"].startswith("Noted:")
    assert "yesterday" in follow_up["summary"].lower()
    print("PASS: voice turns continue in one conversation.")


def test_response_is_speakable():
    """The read-aloud control feeds these strings to TTS, so each must
    be plain prose rather than markup or a structure."""
    response = ask(text=ENGLISH_INCIDENT, language="en")
    for field in ("summary", "possible_issue", "explanation"):
        value = response[field]
        assert isinstance(value, str) and value.strip()
        assert not value.lstrip().startswith("{")
    print("PASS: answers are plain strings the TTS layer can read.")


def test_english_asr_is_refused_by_the_endpoint():
    """The ASR checkpoint covers the 22 Indian languages, not English.

    /api/voice therefore refuses `en` rather than sending English audio
    to a model that cannot read it. The guard is the committed one --
    `{"hi", "mr"}` only -- so an English request comes back with the
    endpoint's own "Unsupported target_lang" message. Asserted against
    the source so this runs without torch or the checkpoint.
    """
    with open(
        os.path.join(HERE, "translate_service.py"), encoding="utf-8"
    ) as handle:
        source = handle.read()

    assert 'target_lang not in {"hi", "mr"}' in source
    assert "Unsupported target_lang. Supported: hi, mr." in source
    print("PASS: an English voice request is refused with a reason.")


# ===========================================================================
# LANGUAGE
# ===========================================================================


def test_language_english_never_translates():
    def explode(_text, _language):
        raise AssertionError("en must not call the translator")

    response = ask(text=ENGLISH_INCIDENT, language="en", translator=explode)
    assert response["language"] == "en"
    print("PASS: english replies skip translation entirely.")


def test_language_english_to_hindi():
    response = ask(
        text=ENGLISH_INCIDENT, language="hi", translator=fake_translate
    )
    assert response["language"] == "hi"
    assert response["summary"].startswith("[hi]")
    assert response["possible_issue"].startswith("[hi]")
    assert response["next_steps"][0].startswith("[hi]")
    print("PASS: english reply comes back in hindi.")


def test_language_english_to_marathi():
    response = ask(
        text=ENGLISH_INCIDENT, language="mr", translator=fake_translate
    )
    assert response["language"] == "mr"
    assert response["summary"].startswith("[mr]")
    print("PASS: english reply comes back in marathi.")


def test_language_hindi_to_english():
    response = ask(text=HINDI_INCIDENT, language="en")
    assert response["language"] == "en"
    assert "financial fraud" in response["possible_issue"]
    assert not response["summary"].startswith("[")
    print("PASS: hindi input answers in english.")


def test_language_hindi_to_marathi():
    response = ask(
        text=HINDI_INCIDENT, language="mr", translator=fake_translate
    )
    assert response["language"] == "mr"
    assert response["possible_issue"].startswith("[mr]")
    print("PASS: hindi input answers in marathi.")


def test_language_marathi_to_english():
    response = ask(text=MARATHI_INCIDENT, language="en")
    assert "financial fraud" in response["possible_issue"]
    print("PASS: marathi input answers in english.")


def test_language_marathi_to_hindi():
    response = ask(
        text=MARATHI_INCIDENT, language="hi", translator=fake_translate
    )
    assert response["language"] == "hi"
    assert response["summary"].startswith("[hi]")
    print("PASS: marathi input answers in hindi.")


def test_names_dates_cnr_and_case_numbers_survive_translation():
    context = make_case()
    response = ask(
        mode="case",
        text="What is the current status?",
        language="mr",
        case_context=context,
        translator=fake_translate,
    )

    everything = prose(response)
    for value in (
        context["cnr_number"],
        context["next_hearing_date"],
        context["presiding_judge"],
        "Arguments",
    ):
        assert value in everything, f"{value} changed in translation"

    assert not SECTION_RE.search(everything)
    print("PASS: CNR, dates, names and stage survive translation.")


def test_translation_preserves_sections_amounts_and_numbers():
    text = (
        "The filing 790/2024 is listed under Order 21 Rule 11 for "
        "Rs. 5,000 on 2026-10-06 with Section 148 applied."
    )

    translated = translate_preserving_facts(text, fake_translate, "hi")

    for value in (
        "790/2024",
        "Order 21 Rule 11",
        "Rs. 5,000",
        "2026-10-06",
        "Section 148",
    ):
        assert value in translated, f"{value} changed in translation"

    assert translated.startswith("[hi]")
    print("PASS: filing numbers, sections, amounts and dates survive.")


def test_case_record_values_are_protected_end_to_end():
    """Even a translator that shuffles every word must not touch the
    facts the case record carries."""
    context = make_case()
    response = ask(
        mode="case",
        text="When is my next hearing?",
        language="hi",
        case_context=context,
        translator=fake_translate,
    )

    assert context["next_hearing_date"] in prose(response)
    assert context["cnr_number"] in prose(response)
    assert not any(
        "left in English" in item for item in response["warnings"]
    ), "nothing had to fall back"
    print("PASS: record values are carried through untranslated.")


def test_fact_preservation_falls_back_when_a_token_is_lost():
    def eats_tokens(text, _language):
        return re.sub(r"NM\d+X", "", str(text))

    text = "Your case PBASB00008022024 is listed on 2026-10-06."
    try:
        translate_preserving_facts(text, eats_tokens, "hi")
    except FactPreservationError as exc:
        assert "PBASB00008022024" in exc.missing
    else:
        raise AssertionError("a swallowed token must raise")

    response = ask(
        mode="case",
        text="When is my next hearing?",
        language="hi",
        case_context=make_case(),
        translator=eats_tokens,
    )
    # The field falls back to English rather than losing the date.
    assert response["summary"].strip()
    assert any(
        "left in English" in item for item in response["warnings"]
    ), "the fallback is declared"
    print("PASS: a lost token falls back to English with a warning.")


def test_protected_span_round_trip():
    text = (
        "CNR PBASB00008022024, filing 790/2024, hearing 2026-10-06, "
        "Section 148, Rs. 5,000, Order 21 Rule 11"
    )
    spans = extract_protected_spans(text)

    assert "PBASB00008022024" in spans
    assert "790/2024" in spans
    assert "2026-10-06" in spans
    assert any("Section 148" == span for span in spans)
    assert any(span.startswith("Rs") for span in spans)
    assert any(span == "Order 21 Rule 11" for span in spans)

    masked = mask_protected_spans(text, spans)
    assert "PBASB00008022024" not in masked
    assert "NM0X" in masked

    restored, missing = unmask_protected_spans(masked, spans)
    assert not missing
    assert restored == text, "masking must round-trip exactly"

    spaced, missing = unmask_protected_spans(
        "value N M 0 X and N M 1 X", spans[:2]
    )
    assert not missing
    assert spans[0] in spaced and spans[1] in spaced
    print("PASS: fact masking round-trips, even when re-spaced.")


def test_bad_requests_are_refused():
    for payload in (
        {"mode": "whatever", "text": "hi"},
        {"mode": "incident", "text": "hi", "language": "fr"},
        {"mode": "case", "text": "hi", "case_context": "not an object"},
        {"mode": "incident", "text": 42},
    ):
        try:
            handle_request(payload)
        except WhatHappenedError:
            continue
        raise AssertionError(f"accepted a bad request: {payload}")

    print("PASS: bad modes, languages and types are refused.")


def test_glossary_explanations_switch_language_without_a_model():
    terms = glossary_terms_for("The matter is adjourned sine die.")
    assert any(item["term"] == "adjourned" for item in terms)

    response = ask(
        text="The matter is adjourned sine die.",
        language="mr",
        translator=fake_translate,
    )
    localised = {
        item["term"]: item["plain"] for item in response["legal_terms"]
    }
    assert localised.get("adjourned") == (
        "सुनावणी पुढील तारखेपर्यंत पुढे ढकलण्यात आली आहे."
    )
    print("PASS: glossary explanations arrive in the chosen language.")


# ===========================================================================
# GUIDANCE — the scorer moved files, so it gets its own regression run
# ===========================================================================


def test_guidance_still_matches_all_fifty_stages():
    stages = [rule["case_stage"] for rule in load_guidance_data()["guidance_v2"]]
    assert len(stages) == 50

    failures = [stage for stage in stages if not match_guidance(stage)["matched"]]
    assert not failures, f"stages that stopped matching: {failures}"
    print("PASS: all 50 guidance stages still match.")


def test_guidance_still_refuses_to_guess():
    result = match_guidance("I bought groceries and went home.")
    assert result["matched"] is False
    assert result["stage"] is None
    print("PASS: guidance still refuses a stage it cannot justify.")


def test_case_stage_lookup_still_works():
    assert get_next_steps("Case disposed of")["matched"] is True
    assert get_next_steps("Completely unknown status")["matched"] is False
    print("PASS: exact stage lookup unchanged.")


def test_analyse_and_answer_are_usable_directly():
    """The two entry points stay importable on their own — the backend
    wiring and any future screen both rely on them."""
    incident = analyse_incident("Someone stole my bicycle.", "en")
    assert incident["mode"] == "incident"
    assert incident["preserve_information"]

    case = answer_case_question("What is the status?", make_case(), "en")
    assert case["mode"] == "case"
    assert case["case_facts"]
    print("PASS: both modes answer when called directly.")


ALL_TESTS = [
    test_incident_english,
    test_incident_hindi,
    test_incident_marathi,
    test_incident_ambiguous,
    test_incident_empty_input,
    test_incident_very_long_input,
    test_incident_missing_information,
    test_incident_no_guidance_match,
    test_incident_guidance_match_reused,
    test_incident_legal_language_is_explained,
    test_case_current_status,
    test_case_last_hearing,
    test_case_next_hearing,
    test_case_latest_order,
    test_case_why_postponed_never_invents_a_reason,
    test_case_next_steps,
    test_case_missing_case_information,
    test_case_no_hearing_date_in_record,
    test_case_follow_up_keeps_context,
    test_case_intent_detection,
    test_voice_transcript_english,
    test_voice_transcript_hindi,
    test_voice_transcript_marathi,
    test_voice_transcript_editing,
    test_voice_to_response_turn,
    test_response_is_speakable,
    test_english_asr_is_refused_by_the_endpoint,
    test_language_english_never_translates,
    test_language_english_to_hindi,
    test_language_english_to_marathi,
    test_language_hindi_to_english,
    test_language_hindi_to_marathi,
    test_language_marathi_to_english,
    test_language_marathi_to_hindi,
    test_names_dates_cnr_and_case_numbers_survive_translation,
    test_translation_preserves_sections_amounts_and_numbers,
    test_case_record_values_are_protected_end_to_end,
    test_fact_preservation_falls_back_when_a_token_is_lost,
    test_protected_span_round_trip,
    test_bad_requests_are_refused,
    test_glossary_explanations_switch_language_without_a_model,
    test_guidance_still_matches_all_fifty_stages,
    test_guidance_still_refuses_to_guess,
    test_case_stage_lookup_still_works,
    test_analyse_and_answer_are_usable_directly,
]


if __name__ == "__main__":
    failures = 0

    for test in ALL_TESTS:
        try:
            test()
        except AssertionError as exc:
            failures += 1
            print(f"FAIL: {test.__name__}: {exc}")

    print(
        f"\n{len(ALL_TESTS) - failures}/{len(ALL_TESTS)} passed"
        + ("" if not failures else f", {failures} FAILED")
    )
    sys.exit(1 if failures else 0)
