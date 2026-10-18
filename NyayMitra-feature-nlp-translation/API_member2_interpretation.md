# "What May Have Happened" — Member 2's model: API contract

**Status: the final ML model for "Tell Us What Happened" has not been
delivered yet.** This document specifies exactly what that model must
accept and return so that connecting it later replaces *only the
placeholder inference layer* — no frontend rebuild, no endpoint change,
no touching voice/ASR.

Audience: Member 2 (model), and anyone wiring the model in.

Related documents:

| Document | Covers |
|---|---|
| `API_what_happened.md` | the older `POST /api/incident/analyze` and `POST /api/case-companion/ask` endpoints (WSL variant, still live) |
| **this file** | the inference contract between the platform and Member 2's model, plus the `POST /api/what-happened` envelope it feeds |

---

## 1. The two contracts — do not confuse them

```
 browser ──(1)──► POST /api/what-happened ──(2)──► what_happened_service
   voice/UI        platform HTTP contract             │
                                                      ▼
                                        what_happened_interpretation
                                        (the seam — THIS DOCUMENT)
                                                      │
                                                      ▼
                                          Member 2's model (contract §4–§5)
```

1. **Platform HTTP contract** — `POST /api/what-happened` between the
   frontend and the NLP service (§6). The frontend is built against it
   and it is **stable**: the model swap does not change it beyond what
   already ships today.
2. **Inference contract** — what the platform sends to Member 2's
   model and what the model must send back (§4–§5). This is the only
   piece that is replaced when the final model arrives.

Voice recording and ASR are **upstream** of both contracts: the mic
audio is transcribed by `POST /api/voice`, and the transcript becomes
the `text` field of the request in §4/§6. Nothing about voice, ASR or
the UI changes when the model is connected.

---

## 2. Current state: a clearly isolated placeholder

While no model is connected, the three reading fields
(`summary`, `possible_issue`, `explanation`) are produced by
rule-based templates in
`what_happened_service.analyse_incident`. **That output is a
placeholder, not the final model output.** It — including any
degenerate, repeated-token output seen from unfinished prototypes —
must never be documented, demoed, or presented as a trained model's
verdict.

The placeholder is isolated in two places:

* **Code seam** — `what_happened_interpretation.py` is the only place
  that talks to a model. It returns `None` today; the template reading
  then stands. No template logic lives in the adapter, and no model
  logic lives anywhere else.
* **Response markers** — every incident response carries, machine- and
  human-readably:

  ```jsonc
  "interpretation_source": "placeholder_template",
  "warnings": [
    "The “what may have happened” reading is a placeholder, not the final
    model output: the trained interpretation model is not connected yet,
    so this reading was produced by rule-based logic only."
  ]
  ```

  The moment a valid model reading is used, the response flips to
  `"interpretation_source": "member2_model"` and the hedge disappears
  from the warnings. `case` mode answers are
  `"interpretation_source": "record_grounded"` (read off the case
  record; no interpretation model is ever consulted there).

The boundary is pinned by `test_what_happened_interpretation.py`.

---

## 3. What "the model" means here

The model reads one incident description — in any mix of languages,
typically the current conversation turn plus recent turns — and
returns a structured interpretation of *what may have happened*: the
lead reading, the possible legal issue, and a plain-words explanation.
Everything else in the product answer (next steps, evidence to
preserve, follow-up questions, time-sensitivity, glossary terms,
disclaimer) is platform-owned and is **not** part of this contract
(§7).

---

## 4. Inference request (platform → model)

Exactly the JSON object the platform POSTs — and the exact argument
triple a registered in-process function receives:

```jsonc
{
  "text": "Someone called me pretending to be from my bank and asked for my OTP. "
          "After I gave it, money was deducted from my account.",
  "language": "en",           // "en" | "hi" | "mr" — the language the USER will read
  "history": [                // earlier USER turns of this conversation,
    "Someone called me...",   //   oldest first
    "yes yesterday evening"   //   • max 6 entries (MAX_HISTORY_TURNS)
  ]                           //   • empty entries dropped
}
```

| Field | Type | Guaranteed by the platform |
|---|---|---|
| `text` | string | trimmed; at most 6000 chars (`MAX_TEXT_CHARS`) |
| `language` | string | one of `en`, `hi`, `mr` |
| `history` | array of strings | ≤ 6 entries, non-empty, oldest first; `[]` on a first turn |

**Transport options** (both give the same JSON):

```python
# (a) in-process, at service startup
from what_happened_interpretation import register_interpreter
register_interpreter(fn)   # fn(text: str, language: str, history: list[str]) -> dict
```

```bash
# (b) over HTTP — no redeploy needed
NYAYMITRA_WHAT_HAPPENED_MODEL_URL=http://127.0.0.1:5000/interpret
#   POST that URL with the JSON above, Content-Type: application/json
#   timeout: 10 s (HTTP_TIMEOUT_SECONDS)
```

Notes:

* `history` is supplied so follow-ups like *"yes"* or *"it happened
  yesterday"* can be read against earlier turns; the model may ignore
  it without violating the contract.
* The model is stateless between calls — the platform owns the
  conversation memory.

---

## 5. Inference response (model → platform)

```jsonc
{
  "summary": "...",           // REQUIRED — lead of "what may have happened"
  "possible_issue": "...",    // REQUIRED — the possible legal issue, hedged
  "explanation": "..."        // REQUIRED — plain-words explanation of the reading
}
```

| Rule | Detail |
|---|---|
| **All three fields required** | each must be a non-empty string |
| **Length** | each field is capped at **4000 chars** (`MAX_FIELD_CHARS`) by the adapter — longer text is truncated, not rejected |
| **Language** | write them **in `language`**. The platform passes these three fields through **verbatim** — they are never machine-translated again. (All *other* prose in the API response is English, translated by the platform.) |
| **Extra keys** | ignored |
| **Invalid shape** | a partial payload (missing/empty/non-string field) **rejects the whole payload** → the platform falls back to the placeholder and marks the response `placeholder_template` |
| **Failure** | any exception, timeout or HTTP error → same graceful fallback. A broken model never produces an HTTP error; the user still gets an answer (§2) |

**Wording rules** (enforced by the platform's test suite —
`test_what_happened.py` sweeps every response field):

* **Hedged only**: "may", "appears to", "based on what you described".
  The reading is a possibility, never a finding.
* **Nothing invented**: no legal sections (a `Section <number>` pattern
  anywhere fails the suite), no dates, no deadlines, no court outcomes,
  no reasons for adjournments, no remedies that the input did not
  support.
* **No degenerate output**: do not return repeated-token, looped or
  truncated mid-sentence text — a repeated-token response is treated
  as a *failed* generation, i.e. return a clean fallback or omit the
  payload rather than shipping the degeneration. The platform will
  happily use whatever it is given; quality control starts at the
  model.

### Example exchange (language `hi`)

Request:

```json
{
  "text": "Someone threatened me and demanded money from me.",
  "language": "hi",
  "history": []
}
```

Response:

```json
{
  "summary": "संभव धमकी या जबरन वसूली — केवल आपके वर्णन के आधार पर।",
  "possible_issue": "इसमें आपराधिक धमकी या वसूली शामिल हो सकती है; यह केवल एक संभावना है।",
  "explanation": "आपने जो बताया उसके आधार पर, किसी ने आपको धमकी देकर पैसे माँगे — कानूनी रूप से देखा जा सकता है।"
}
```

The platform then returns these three fields to the frontend exactly
as written, with `interpretation_source: "member2_model"` and no
placeholder hedge.

---

## 6. Platform HTTP contract (for context — stable)

`POST /api/what-happened` on the NLP service (port 8001), same auth as
every endpoint: `Authorization: Bearer <NYAYMITRA_NLP_KEY>` (local
default `nyaymitra-local-test-2026`).

Request:

```jsonc
{
  "mode": "incident",        // "incident" | "case"
  "text": "...",             // what the user typed or said (mic transcript)
  "language": "en",          // "en" | "hi" | "mr"
  "conversation_id": "c_…",  // optional; omit to start a new conversation
  "case_context": { ... }    // optional, case mode only
}
```

Response (both modes; the fields the model feeds are marked):

```jsonc
{
  "mode": "incident",
  "language": "en",
  "conversation_id": "c_…",
  "acknowledgement": "…",
  "interpretation_source": "member2_model",   // §2 — additive, machine-readable
  "summary": "…",                             // ▲ model-owned in incident mode
  "possible_issue": "…",                      // ▲ model-owned in incident mode
  "explanation": "…",                         // ▲ model-owned in incident mode
  "case_facts": [], "record_gaps": [],
  "next_steps": [...], "preserve_information": [...],
  "follow_up_questions": [...], "warnings": [...],
  "time_sensitive": false, "time_sensitivity_note": "…",
  "matched_stage": null, "guidance": null,
  "legal_terms": [...], "disclaimer": "…",
  "user_text": "…"
}
```

Errors: `401` bad key; `400 {"detail": …}` for invalid `mode`,
`language`, non-string or >20000-char `text`, non-object
`case_context`. Model failures are **not** an error case — see §5.

---

## 7. What the model does NOT own

These stay platform code, guidance data, or the case record — they are
not part of the model contract and are not expected to change when the
model is connected:

* `next_steps`, `preserve_information` — existing guidance sets
  (`guidance_match` / `next_steps_guidance_lookup`)
* `follow_up_questions`, `warnings`, `acknowledgement` — platform
  conversation scaffolding (the placeholder hedge simply stops being
  appended)
* `time_sensitive`, `time_sensitivity_note` — rule-based
* `matched_stage`, `guidance`, `legal_terms`, `disclaimer` — existing
  guidance/glossary layers
* `case_facts`, `record_gaps`, and the whole `case` mode — read off
  the case record (`interpretation_source: "record_grounded"`)
* voice recording, ASR, TTS, the frontend UI and the HTTP envelope

---

## 8. Verification checklist for Member 2

Once the model exists, connecting it should require **only**:

1. **Wire it** — `register_interpreter(fn)` at startup, *or* set
   `NYAYMITRA_WHAT_HAPPENED_MODEL_URL` (§4). Nothing else in the repo
   changes.
2. **Unit proof** — `pytest test_what_happened_interpretation.py`
   (11 tests) already covers connected/broken/unconnected behaviour;
   run it against your registered model for an end-to-end sanity pass.
3. **Live proof** — with the service up, `POST /api/what-happened`
   with a real description and check:
   * `"interpretation_source": "member2_model"`
   * the placeholder hedge is **absent** from `warnings`
   * `summary` / `possible_issue` / `explanation` are your model's
     text, byte-for-byte (also for `language: "hi"` / `"mr"` — they
     pass through untranslated)
   * all other fields still behave exactly as before
4. **Failure drill** — point the URL at a dead port: the response must
   still be HTTP 200, fall back to the placeholder, and re-mark the
   response `placeholder_template` with the hedge restored.

---

## 9. The swap — in one paragraph

Today `what_happened_interpretation.interpret()` returns `None`, so
`analyse_incident` keeps its template reading and appends the
placeholder hedge. When Member 2's model answers §4 with a valid §5
payload, the same call returns that payload, the three reading fields
become the model's, `interpretation_source` flips to `member2_model`,
the hedge disappears, and — because the model's fields are already in
the user's language — they reach the frontend verbatim. The frontend,
the endpoint, voice/ASR, and every platform-owned field are untouched.
That is the whole swap.
