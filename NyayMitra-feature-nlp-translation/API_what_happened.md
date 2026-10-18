# "What Happened?" — API contract (Member 3, NLP)

Two endpoints on the existing NLP service (`translate_service:app`,
port 8001), implementing the **two clearly separated workflows** of
"What Happened?". They are **additive**: nothing that already existed
was replaced, and both reuse the service's existing engines rather
than growing parallel ones.

| Endpoint | Workflow | Reuses |
|---|---|---|
| `POST /api/incident/analyze` | 1 — "Tell us an incident" | `legal_simplification`, `incident_knowledge` (loader for Member 1's files), `incident_classification` (Member 2's adapter), `urgency_adapter`, IndicTrans2 via `_translate_simple_layer` |
| `POST /api/case-companion/ask` | 2 — "Ask about your case" | `guidance_matching` (the `/api/guidance` scorer), `legal_simplification`, `next_steps_guidance_lookup` |

> **Note (newer flow):** the current frontend's *Tell Us What
> Happened* page calls **`POST /api/what-happened`**, whose envelope
> and — more importantly — **Member 2's interpretation-model contract**
> are documented in [`API_member2_interpretation.md`](API_member2_interpretation.md).
> Both endpoints above remain live alongside it.

**The workflows are not mixed.** The incident endpoint never matches a
court case stage — an incident is not a stage, and a description of
something that happened must not come back as *"Notice issued to
respondent"*. Case-stage guidance stays where it belongs: `/api/guidance`
and the case companion.

Auth is identical to every other endpoint on the service:

```
Authorization: Bearer <NYAYMITRA_NLP_KEY>
```

Default key (local dev): `nyaymitra-local-test-2026`. Missing or wrong
key ⇒ `401 {"detail": "Invalid or missing API key"}`.

---

## 1. `POST /api/incident/analyze`

Workflow 1. Reads a description of what happened and reads it back
**hedged**, structured as the eight on-screen sections.

### Request

```jsonc
{
  "description": "Someone called me pretending to be from my bank and asked for my OTP. After I gave it, money was deducted from my account.",
  "conversation_id": "c_ab12cd34ef56",   // optional; minted if absent
  "known_facts": { "place": "Pune" },     // optional, merged into the conversation
  "language": "en",                       // optional; message language, handed to Member 2's classifier
  "target_lang": "eng_Latn"               // eng_Latn (default) | hin_Deva | mar_Deva
}
```

- `description` empty/whitespace ⇒ `400 "Nothing to analyze."`
- longer than `MAX_INPUT_CHARS` (20 000) ⇒ `400`
- unknown `target_lang` ⇒ `400 "Unsupported target_lang. Supported: mar_Deva, hin_Deva, eng_Latn."`

### Response (all keys always present)

```jsonc
{
  "mode": "incident",                     // always — this is workflow 1
  "original_input": "…",                  // the message exactly as sent
  "what_user_described": "…",             // everything said in this conversation (normalised whitespace only)
  "possible_issue": "Based on what you described, this may involve … The exact legal classification depends on the circumstances.",
  "simple_explanation": "Based on what you described: …",
  "facts": [
    {"type": "date", "value": "15.10.2026", "source": "detected"},
    {"type": "amount", "value": "Rs. 25,000", "source": "detected"},
    {"type": "provided", "label": "place", "value": "Pune", "source": "provided"}
  ],
  "missing_information": ["When did this happen? …", "Who else was involved …"],
  "next_steps": ["You may consider: …"],
  "evidence_to_preserve": ["You may consider keeping copies of …"],
  "urgency": {                             // the urgency adapter's answer — see §4.2
    "status": "not_available",
    "message": "Incident urgency analysis will be provided when the incident model is connected."
  },
  "warnings": ["…", "More information is needed to understand this situation accurately."],
  "confidence": {"level": "low|medium|high", "score": 0.45, "basis": "12 words of description; …"},
  "incident_category": {"id": "…", "label": "…"} | null,
  "classification": {                      // where the category came from — said out loud
    "source": "none|keyword_matching|member2_model",
    "member2_connected": false,
    "confidence": null,                    // Member 2's score when it classified this, else null
    "note": "The incident classification model is not connected yet; …"
  },
  "knowledge": {"source": "none|files|dev-example",
                "files": {"categories": false, "next_steps": false,
                          "questions": false, "facts": false},
                "notes": ["incident_categories.json not found"]},
  "disclaimer": "This guidance is informational only …",
  "conversation_id": "c_ab12cd34ef56",
  "language": "eng_Latn",
  "translated_response": "WHAT YOU TOLD US\n…\n\nWHAT THIS MAY INVOLVE\n…"   // whole analysis, one sectioned string, in `language`
}
```

There is deliberately **no `guidance` key** on this endpoint: stage
matching does not happen in workflow 1.

### Rules this endpoint is held to

1. **Nothing invented.** A `fact` is a substring of what the person
   wrote (or a value supplied earlier, tagged `provided`). No dates,
   sections, statuses, hearing dates, reasons, crime conclusions or
   urgency bands are added.
2. **Conditional language.** "Based on what you described…",
   "may involve", "not sufficient to determine", "You may consider".
   At low confidence the response always carries
   `"More information is needed to understand this situation accurately."`
   When a category is claimed, the sentence
   `"The exact legal classification depends on the circumstances."`
   follows it.
3. **Not a court-stage lookup.** The pipeline is: incident
   description → Member 2 classification (when connected; keyword
   matching over Member 1's knowledge otherwise, and `classification.source`
   says which) → interpretation → incident knowledge → possible issue →
   simple explanation → next steps → evidence → urgency → translation.

### Conversation follow-ups

Earlier user messages in the same conversation are analyzed **with**
the new message, so a short follow-up is read next to the account it
refers to:

- turn 1: `"Someone called me pretending to be from my bank…"`
- turn 2: `"It happened yesterday."` ⇒ `what_user_described` carries
  **both**, `original_input` is only the new message, and
  `"When did this happen?"` disappears from `missing_information`.

A re-send of the identical message (e.g. to change `target_lang`) is
not counted twice.

### `target_lang` other than `eng_Latn`

Every prose field (`possible_issue`, `simple_explanation`,
`next_steps`, `missing_information`, `evidence_to_preserve`,
`warnings`, the urgency `message`/indicators) is passed through the
same entity-preserving layer `/api/legal-simplify` uses: dates,
amounts, CNR/case/section numbers, names and court headings are
masked before the model sees them and restored afterwards. Anything
that cannot be confirmed after translation is reported in `warnings`
(`"These references could not be confirmed in the translated text: …"`),
never silently dropped. A field that fails to translate comes back in
English with a warning rather than being omitted.
`translated_response` is composed from those (already translated)
fields plus headings translated the same way, so it can never
contradict them.

---

## 2. `POST /api/case-companion/ask`

Workflow 2. Answers a question about a case **only from the case
information sent with the question**.

### Request

```jsonc
{
  "question": "Why was the case adjourned?",
  "case_context": { /* Member 4's case record, see below */ },
  "conversation_id": "c_ab12cd34ef56",   // optional
  "target_lang": "eng_Latn"               // optional
}
```

- `question` empty ⇒ `400 "Nothing to answer."`
- `case_context` larger than 200 000 characters (serialised) ⇒ `400`

### Accepted `case_context` keys (tolerant — aliases included)

| Field | Aliases | Notes |
|---|---|---|
| case number | `case_number`, `case_no`, `caseNo`, `filing_number` | |
| CNR | `cnr`, `cnr_number` | |
| court | `court_name`, `court`, `courtName` | |
| current stage | `current_case_stage`, `case_stage`, `stage`, `present_stage` | drives guidance reuse |
| status | `case_status`, `status` | |
| next hearing date | `next_hearing_date`, `next_date`, `next_date_of_hearing`, `hearing_date` | |
| parties | `petitioner`, `petitioner_name`, `respondent`, `respondent_name`, `parties` | |
| timeline | `timeline`, `case_history_timeline`, `events`, `history`, `proceedings` | list of dicts or strings; entry dates accept `date`/`order_date`/`hearing_date`/`business_on_date`, entry text accepts `event`/`title`/`description`/`order_text`/`order_details`/`purpose_of_hearing`/… |
| orders | `orders`, `court_orders`, `order_history` | list of dicts/strings; per entry `order_text`/`order_details`/`text`/`summary`/`description` read as the order's text, `order_date` as its date |
| one order's text | `order_text`, `latest_order_text`, `document_text` | string |

Unknown keys are ignored. A wrongly-typed or blank value is treated as
absent — which means the answer says the information is absent. The
aliases above are chosen so a raw record from Member 4's My Cases / CNR
store can be passed through unmodified.

### Response

```jsonc
{
  "mode": "case",                          // always — this is workflow 2
  "question": "Why was the case adjourned?",
  "question_type": "adjournment_reason",
  "answer": "The available case information does not state the reason for the adjournment. …",
  "grounded": false,
  "source": {"field": "case_history_timeline[1]", "value": "…"} | null,
  "current_stage": "Case adjourned for want of time" | null,   // as the record states it; null when it does not
  "known_case_facts": [{"field": "case_number", "label": "case number", "value": "…"}],
  "supporting_case_facts": [ /* identical list — documented alias */ ],
  "next_steps": ["You may consider: …"],
  "simplified_order": {"source_field": "orders[0].order_text",
                       "original_text": "…", "simple_english": "…",
                       "warnings": []} | null,
  "missing_information": ["reason for the adjournment"],
  "warnings": ["This answer is drawn only from the case information supplied …"],
  "answered_at": "2026-09-29T09:15:00+00:00",
  "disclaimer": "This guidance is informational only …",
  "conversation_id": "c_ab12cd34ef56",
  "language": "eng_Latn"
}
```

`question_type` is one of: `next_hearing_date`, `adjournment_reason`,
`current_stage`, `case_status`, `order_explanation`,
`what_to_do_next`, `general`.

**The rule it is built around:** if the case information does not
contain the answer, `answer` says so (e.g. *"The available case
information does not state the reason for the adjournment."*),
`grounded` is `false`, and `missing_information` names the missing
field. No date, status, party, reason or order is ever inferred.

---

## 3. Conversation context

`ConversationContextStore` in `conversation_context.py` — in-memory,
thread-safe, bounded (200 conversations, 40 messages, 60 facts).

- First call without `conversation_id` gets one minted back; send it
  on later calls.
- Facts established in an analysis (`source: "detected"`) are
  remembered and reappear as `source: "provided"` on the next turn,
  so a short second message does not lose the first message's date.
- On the incident side, the earlier **messages** themselves are also
  carried forward (see "Conversation follow-ups" above). A
  conversation that has moved to the case intent contributes no prior
  incident text — the workflows stay separate even in one chat.
- Incident and case flows should use **separate** `conversation_id`s
  (the frontend does); nothing breaks if they don't, because prior
  incident text is only read while `current_intent` is
  `incident_analysis`.
- The interface is `get` / `ensure` / `record` / `known_facts`; adding
  persistence later means changing only that class's internals.

## 4. Interfaces for other members

### 4.1 Member 2 — incident classification (`incident_classification.py`)

Member 2's ML output is consumed through one adapter; nothing is
imitated or synthesised. Connect either in-process:

```python
from incident_classification import register_classifier
register_classifier(fn)        # fn(text, language) -> payload dict
```

or over HTTP without a redeploy, by setting
`NYAYMITRA_INCIDENT_CLASSIFIER_URL` (POST `{"text": …, "language": …}`).

Expected payload (all fields optional; extras ignored):

```jsonc
{
  "text": "...",
  "language": "en",
  "intent": "incident",
  "incident_category": "...",     // the model's category id/label
  "confidence": 0.0,              // 0..1
  "facts": { "when": "..." },     // facts the model extracted (shown as source "member2_model")
  "missing_information": ["..."]
}
```

Behaviour while unconnected (or when the model errors, times out, or
returns junk): `classify()` returns `None`, the analysis falls back to
keyword matching over Member 1's knowledge files, and the response
says so in `classification.source = "keyword_matching|none"` plus a
warning. Every payload field is validated and capped before use; an
invalid value becomes `None`/empty — never a plausible default.

### 4.2 Urgency (`urgency_adapter.py`)

```
incident input  ->  assess_urgency()  ->  urgency result
```

While no model is connected, every result is exactly:

```json
{"status": "not_available",
 "message": "Incident urgency analysis will be provided when the incident model is connected."}
```

Connect the model later with `register_urgency_model(fn)` where
`fn(text, classification) -> dict`, or set
`NYAYMITRA_URGENCY_MODEL_URL`. A model answer is accepted only in the
documented shape (`status: "available"`, `level: "low|medium|high"`,
optional `message`/`basis`); anything else — including a partial
answer — degrades back to `not_available`. **No endpoint or screen may
ever display a LOW/MEDIUM/HIGH band that a model did not produce.**

If Member 1's knowledge files carry `urgency_indicators` for the
matched category, they are listed under
`urgency.knowledge_indicators`, explicitly marked (via
`knowledge_indicator_note`) as general notes for the category — never
as an assessment of this situation, and `status` stays
`not_available`.

### 4.3 Member 1 — incident knowledge files

Drop these next to the service (`NyayMitra-feature-nlp-translation/`),
or point `NYAYMITRA_INCIDENT_KNOWLEDGE_DIR` at another directory.
Missing, malformed or wrong-shaped files are tolerated and reported in
`knowledge.notes` — the analysis runs without them and says so.

```jsonc
// incident_categories.json — category + per-category legal knowledge
{"categories": [{
  "id": "…", "label": "…", "keywords": ["…"],
  "description": "…",
  "possible_legal_issue": "Based on what you described, this may involve …",  // optional; used verbatim in "what this may involve"
  "urgency_indicators": ["…"],     // optional; general notes, NOT an urgency level
  "warnings": ["…"],               // optional; appended to the response warnings
  "related_case_stages": ["…"]     // optional
}]}

// incident_next_steps.json  → "what you can consider doing"
{"next_steps": {"<category_id>": ["…"]}}   // or [{"category_id": "…", "steps": ["…"]}]

// incident_questions.json   → "information we still need"
{"questions": {"<category_id>": ["…"]}}

// incident_facts.json       → "information / evidence to keep"
{"evidence": {"<category_id>": ["…"]}}     // "facts" accepted as a synonym
```

Per-category fields map straight onto the analysis response:

| File field | Response section |
|---|---|
| `label` / `keywords` | `incident_category` |
| `possible_legal_issue` | `possible_issue` (hedge appended) |
| `next_steps` | `next_steps` |
| `questions` | `missing_information` |
| `evidence` | `evidence_to_preserve` |
| `urgency_indicators` | `urgency.knowledge_indicators` (marked as general notes) |
| `warnings` | `warnings` |

Schemas are validated leniently by `incident_knowledge.py`; entries
without an `id`/`label` are skipped, wrong-typed optional fields
become empty, and nothing is ever invented from a malformed file.
Development examples are used only when
`NYAYMITRA_INCIDENT_DEV_EXAMPLE=1` and no real file is present, and
are labelled as placeholders.

### 4.4 Member 4 — case companion

Send the case record as `case_context` (shape above) — My Cases / CNR
records pass through as-is via the aliases. Render `answer`, show
`warnings` and `disclaimer`, and treat `grounded: false` as "the
record does not say" rather than an error.
`supporting_case_facts` (alias of `known_case_facts`) is a
pre-filtered summary of what the record did carry, handy for a
sidebar. This module only *reads* case data; it does not modify or
replace Member 4's case APIs.

### Frontend

- `frontend/src/api/whatHappenedApi.ts` — typed client
  (`analyzeIncident`, `askCaseCompanion`) following the existing
  `config.ts` + `apiRequest` pattern.
- `frontend/src/pages/user/VoiceNyayMitraPage.tsx` — the "What
  Happened?" screen itself: a two-choice entry (**Tell us an
  incident** / **Ask about your case**), then the incident flow
  (textarea + microphone, seven result cards, English/हिंदी/मराठी
  selector, follow-up box) or the case flow (question chips + the
  user's ongoing cases read from the existing case store). The
  urgency card renders the adapter's `not_available` state as-is.

## 5. Tests

```
cd NyayMitra-feature-nlp-translation
.venv/bin/pytest test_incident_analysis.py test_case_companion.py \
  test_member_interfaces.py test_what_happened_api.py -v
```

- `test_incident_analysis.py` — unit: hedging, no invented facts, the
  incident workflow never maps input to a court stage, urgency is
  never faked, conversation follow-ups, knowledge loader
  (present/absent/malformed), conversation store.
- `test_case_companion.py` — unit: every "does it say so?" case, no
  value from outside the supplied context, plus `mode` /
  `current_stage` / `supporting_case_facts`.
- `test_member_interfaces.py` — unit: Member 2's classifier adapter
  (connected/unconnected/invalid payloads), the urgency adapter
  (not-available/partial/garbage answers), and Member 1's full
  knowledge schema.
- `test_what_happened_api.py` — HTTP: auth, validation, both
  contracts, no-stage mapping, fake-urgency guard, follow-up
  conversation, no invented sections/dates, entity-preserving
  translation (हिंदी + मराठी), and `/api/guidance` regression after
  its scorer moved to `guidance_matching.py`.

Regression suites for existing behaviour:
`test_next_steps_guidance.py`, `test_legal_simplification.py`,
`test_court_order_upload.py`.
