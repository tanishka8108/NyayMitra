# NyayMitra — AI Court Assistant

NyayMitra helps three people who usually struggle to talk to each other: a
citizen who does not know what their case's next hearing date is, an advocate
carrying more matters than they can hold in their head, and the court staff and
administrators who keep the record straight. The frontend serves all of them
from one login — the door you choose decides which dashboard you get.

---

## Roles

| Role | Sign in through | Gets |
|------|-----------------|------|
| **Citizen (USER)** | "I am a citizen" | My Cases (new case, documents, chat with the assigned lawyer), Court Orders in plain language, Case Timeline, Delay Analysis, Voice NyayMitra, Find a Lawyer, Translation |
| **Lawyer (LAWYER)** | "I am an advocate" | Active Cases with documents, next hearings and court orders, Messages, an editable profile |
| **Administrator (ADMIN)** | "Administrator / staff" | Every dashboard section, staff account issuance and work assignment, Access & Roles authority grants, user deactivation, lawyer verification |
| **Staff (STAFF)** | **through the Admin door** | Case files, hearings, document processing, **lawyer verification**, task queue, reports — each gated on what the admin granted |

Staff deliberately has no door of its own: an administrator issues the
credentials, and the staff member then signs in through the administrator's
login. The same administrator can grant and revoke each staff authority later
under **Access & Roles**.

---

## Architecture

```text
  Browser
     │  Vite/React (5173 dev, 8080 in Docker)
     ▼
  ┌───────────────────────────────────────────┐
  │  frontend/        React 19 + TypeScript   │  ← talks ONLY to FastAPI
  └───────────────────────────────────────────┘
        │ HTTP + JSON                  │ HTTP + JSON
        ▼                             ▼
  ┌──────────────────┐        ┌───────────────────────────┐
  │ Lawyer API :8000 │        │ NLP service :8001         │
  │ FastAPI + SQLAlchemy       │ FastAPI + IndicTrans2     │
  └──────────────────┘        └───────────────────────────┘
        │                             │
        ▼                             │ local model cache
  ┌──────────────────┐        ┌───────────────────────────┐
  │ PostgreSQL :5432 │        │ HF gated checkpoints       │
  └──────────────────┘        └───────────────────────────┘
```

The frontend never talks to PostgreSQL directly — every read and write goes
through a FastAPI service.

---

## Repository layout

| Path | What it holds |
|------|---------------|
| `frontend/` | React + Vite + TypeScript client. No router: navigation is a state-based `Page` union in `src/App.tsx`. Dependencies are just `react`, `react-dom`, `lucide-react`. |
| `NyayMitra-feature-lawyer-api/` | Lawyer service — profile, listing, practice areas. `main.py`, `lawyer_database.sql`, `requirements.txt`. |
| `NyayMitra-feature-nlp-translation/` | Translation, indic-to-indic, voice, OCR/PDF pipelines. `translate_service.py` is the running app. |
| `docs/` | `auth-decision.md`, `pwa-strategy.md`, `postman/NyayMitra.postman_collection.json` |
| `docker-compose.yml` | Frontend + PostgreSQL only. The two FastAPI services run on the host. |
| `.github/workflows/ci.yml` | Frontend CI: `npm ci` → `npm audit --audit-level=high` → `npm run build`. |

> `translation_service.py` and `DEPRECATED_translation_api.py` are historical
> files. The service launched is `translate_service:app`.

---

## Running it locally

### 1. Database (Docker)

```bash
docker compose up -d database     # postgres:16-alpine on :5432
```

### 2. Lawyer API (:8000)

```powershell
cd NyayMitra-feature-lawyer-api
copy .env.example .env            # then fill in your real DB password
# load lawyer_database.sql into the database once
python -m database.seed_demo_accounts   # demo accounts (idempotent, see below)
uvicorn main:app --host 127.0.0.1 --port 8000
```

### 3. NLP service (:8001)

Python 3.14, CPU-only. Install torch from its own index first — see the
header of `NyayMitra-feature-nlp-translation/requirements.txt` for the
FFmpeg DLL step Windows needs.

```powershell
cd NyayMitra-feature-nlp-translation
pip install --index-url https://download.pytorch.org/whl/cpu torch==2.11.0+cpu torchaudio==2.11.0+cpu
pip install -r requirements.txt

$env:HF_TOKEN = '<your HuggingFace token>'   # all three models are gated
$env:HF_HUB_OFFLINE = '0'
python -m uvicorn translate_service:app --host 127.0.0.1 --port 8001
```

### 4. Frontend (:5173)

```powershell
cd frontend
copy .env.example .env            # or use the committed example values as-is
npm ci
npm run dev                       # http://localhost:5173
```

Then open **http://localhost:5173** — use `localhost`, not `127.0.0.1`.

---

### 5. Model API (:8000 — Tell Us What Happened + delay prediction)

This is `src/api.py`, the service behind **Tell Us What Happened** and
**Delay Analysis**. It needs its own virtualenv.

```powershell
py -3.12 -m venv .venv          # once, from the repository root
.\.venv\Scripts\pip install -r requirements.txt

cd src
..\.venv\Scripts\python -m uvicorn api:app --port 8000
```

Endpoints, both rate-limited to 30 requests/minute:

| Endpoint | Request | Returns |
|---|---|---|
| `POST /understand-situation` | `{"text": "..."}` | `intent`, `incident_category`, `category_id`, `confidence`, `facts`, `missing_information`, `message` |
| `POST /predict-delay` | `{"case_type", "court", "district", "state"}` | `predicted_next_hearing_days` **and** `predicted_disposal_days` in one response |
| `GET /health` | — | `{"status": "ok"}` |

> **First run downloads ~480 MB.** Startup loads
> `paraphrase-multilingual-MiniLM-L12-v2` from the HuggingFace hub the
> first time (about 480,000,000 bytes: the weights plus tokenizer) and
> caches it, so every later start is fast. The models, the JSON data and
> the embedding matrices are loaded in the FastAPI lifespan hook, before
> the first request, not during it. Hindi, Marathi and Hinglish input
> works because that encoder is multilingual — see "Encoder and
> embeddings" below.

> ⚠️ **Port clash — read before running two services.** The README above
> puts the **Lawyer API on :8000**, and this service also uses **:8000**.
> They cannot run at the same time. During model development the model
> API owns :8000 (that is what `VITE_MODEL_API_URL` points at); start the
> Lawyer API on `:8002` with an **uncommitted** `.env.local` override if
> you need it alongside. Committed defaults are deliberately left
> unchanged.

CORS on this service allows **only** the exact Vite dev origin
(`http://localhost:5173`) — a specific list, never `*`. Add your origin to
`ALLOWED_ORIGINS` in `src/api.py` if you serve the frontend from
somewhere else.

---

## Demo credentials (development & testing only)

These are **seeded demo/test accounts — never real user data.** Creating them
is repeatable and idempotent (re-running never duplicates an account):

```powershell
cd NyayMitra-feature-lawyer-api
python -m database.seed_demo_accounts
```

| Role | Email | Password | Profile |
|------|-------|----------|---------|
| USER (citizen) | `asha@example.com` | `user123` | Asha Verma (`is_demo = 1`) |
| LAWYER | `rohan@example.com` | `lawyer123` | Adv. Rohan Deshmukh — `lawyer_id LAWYER_0003`, verification **APPROVED** |
| ADMIN | `admin@nyaymitra.in` | `admin123` | Site Administrator — for Admin Dashboard integration testing only; ADMIN has **no** self-registration path |

- Passwords live in the database only as PBKDF2-HMAC-SHA256 hashes; the
  plaintext above exists in this README and in the seeder's console output
  only. `users.is_demo = 1` marks every seeded account.
- **Production frontend builds never contain these credentials** — they are
  dev-gated (`import.meta.env.DEV`), so a `vite build` bundle has none of
  them; the login page's demo panel appears only in dev builds running
  `VITE_AUTH_MODE=mock`.
- Mock-mode only (never seeded into the database): Staff
  `kavya@nyaymitra.in` / `staff123` — STAFF accounts are issued by ADMIN in
  the offline demo and have no database role.
- In dev mock mode the login page still prints the demo credentials under
  each door.

---

## Environment variables

The frontend reads its own `frontend/.env` — Vite inlines `VITE_*` values at
build time. Everything is documented in `frontend/.env.example`; nothing has to
be set for the app to run.

| Variable | Default | Meaning |
|----------|---------|---------|
| `VITE_API_BASE_URL` | `http://127.0.0.1:8000` | Lawyer service |
| `VITE_MODEL_API_URL` | `http://127.0.0.1:8000` | Model API (`src/api.py`) — `/understand-situation` and `/predict-delay`. A **separate** variable from `VITE_API_BASE_URL` even though both default to port 8000: they are different processes, so only one can hold the port at a time (see the port-clash note above) |
| `VITE_TRANSLATION_API_URL` | `http://127.0.0.1:8001` | NLP service |
| `VITE_TRANSLATION_API_KEY` | `nyaymitra-local-test-2026` | Bearer key the NLP service expects |
| `NYAYMITRA_NLP_KEY` | `nyaymitra-local-test-2026` | The service-side half of that key — the NLP service reads it, so the two must be set together |
| `VITE_LAWYER_ID` | `LAWYER_0003` | Profile opened during development; the session overrides it after login |
| `VITE_AUTH_MODE` | `api` | `api` talks to the FastAPI auth endpoints (`/api/auth/register`, `/api/auth/login`); `mock` uses the offline demo accounts (dev builds only — production bundles contain no credentials) |
| `VITE_CHAT_MODE` | `api` | `api` talks to the FastAPI chat endpoints (`/api/chat/...` — conversations persist server-side); `mock` keeps threads in `localStorage` for offline demos |
| `VITE_AUTHORITY_MODE` | *(not read)* | Reserved for `/authorities`. Grants are always kept in `localStorage` today — the flag is documented in `.env.example` but nothing consumes it yet |

`VITE_AUTH_MODE` and `VITE_CHAT_MODE` both default to `api` (the real
FastAPI endpoints), so a missing `.env` is not an error; setting either
to `mock` switches that module to its offline demo store.
On the service side,
`MODEL_IDLE_SECONDS` (default `600`) controls how long a loaded NLP checkpoint
is held before it is released. On the lawyer service, `CASE_DATA_PROVIDER`
(default `development`) picks the case provider behind `/api/cases`,
`CASE_DATASET_PATH` optionally points the development provider at another
dataset file, and `CASE_EXTERNAL_DSN` stays unset until an authorised external
source exists. See [`docs/my-cases.md`](docs/my-cases.md).

---

## What each role can do

**Citizen**
- **My Cases** — only the signed-in user's own matters, filtered by
  `owner_user_id`. From one place: file a **new case** with its first
  documents, open an **ongoing case** to see that case's documents, add
  more to it, and **chat with the lawyer assigned to it**. A **CNR
  search** at the top opens any case by its 16-character CNR — full
  dashboard with status, parties, court, chronological timeline, orders
  and next-steps guidance ([`docs/my-cases.md`](docs/my-cases.md)).
- **Find a Lawyer** — live directory from `GET /api/lawyers`, with a
  **Chat** button per profile.
- **Messages** — the shared inbox against **APPROVED lawyers only**:
  open a thread from a Find-a-Lawyer card or the inbox's New chat
  picker (the picker lists the verified-lawyer directory from
  `GET /api/chat/lawyers`), with full history that survives refresh
  and re-login, and an optional link to a saved case's CNR.
- **Court Order** — upload an image or PDF and the NLP service explains
  it in simple words; orders are listed per ongoing case.
- **Case Timeline** and **Delay Analysis** — pick an ongoing case, then
  read its timeline, or ask for a predicted delay and the reason behind
  it.
- **Voice NyayMitra** — speak, the audio becomes text, and the answer
  comes back as **What to do next** plus an **Urgency of your incident**
  panel.
- **Translation** — translate case documents through the NLP service.

**Lawyer**
- **Active Cases** sits above the profile block, with each matter's
  documents on file, its next court hearing and its court orders.
- **Messages** — one click into the shared inbox, categories for
  clients, staff and other advocates, plus "Message client" buttons on
  each matter.
- **View your profile** opens the full record, where an **Edit profile**
  toggle lets the advocate change their own fields. Verification status
  is deliberately not one of them.

**Administrator**
- **Staff Management** — issue credentials through the Admin door and
  **assign each member the work they do** (case records, hearings,
  document processing, lawyer verification, communications, reports).
- **Manage Users** — switch a citizen account **active or deactivated**;
  a deactivated account is refused at the login door with a plain
  explanation rather than a wrong-password error.
- **Manage Lawyers** — **verify or reject** an advocate's registration
  on the row it belongs to.
- **Messages** — two categories, **from lawyers** and **from staff**.
- **Access & Roles** — staff grouped **by their assigned work**,
  authorities grouped **into categories**, with grant and revoke per
  category and per authority.
- Lawyer Records and Platform Data are unchanged.

**Staff**
- Case Files, Hearings, Document Processing, **Lawyer Verification**,
  Task Queue, Reports — each section opens only if its authority is
  granted, and otherwise reads **Not granted** rather than failing when
  clicked.
- Their own **work assignment** at the top of the dashboard, and a live
  **Your authorities** panel grouped by the same categories Access &
  Roles uses.
- Verification runs on the same store the admin writes to, so a ruling
  made as staff shows up on the admin's screens and vice versa.

### Communication matrix

Who may start a chat with whom:

| | Citizen | Lawyer | Staff | Admin |
|---|---|---|---|---|
| **Citizen** | — | ✅ | ✅ | ❌ |
| **Lawyer** | ✅ | — | ✅ | ✅ |
| **Staff** | ✅ | ✅ | — | ✅ |
| **Admin** | ❌ | ✅ | ✅ | — |

Citizen ↔ Admin is deliberately absent: a citizen reaches the administration
through staff. The matrix is enforced in `src/api/chatApi.ts`, not by hiding
buttons.

Two lists are derived from that one matrix:

- **`allowedPartners`** — who a role may exchange messages with.
- **`visiblePartners`** — who becomes a sidebar category and a "new
  conversation" entry point. It differs in exactly one place: an advocate
  browses **Clients / Lawyers / Staff** (the three the brief asks for)
  and does not navigate by an Admin channel, while the administrator
  still opens threads with advocates — which is what puts its
  **From lawyers** category to work.

---

## Service APIs

**Lawyer service — `:8000`**

| Method | Path | Used by |
|--------|------|---------|
| GET | `/api/lawyers` | Find a Lawyer, admin Manage Lawyers / Platform Data |
| GET | `/api/lawyers/{lawyer_id}` | Lawyer profile, admin Lawyer Records |
| GET | `/api/practice-areas` | Practice-area filtering |
| GET | `/api/cases` | My Cases list (`q`, `status`, `state`, `page`, `limit`) |
| GET | `/api/cases/cnr/{cnr}` | My Cases detail — 400 malformed / 404 unknown |
| GET | `/api/cases/meta` | Status and court filters for My Cases |

> The **list** response is a summary: `enrollment_number`, `bar_council`,
> `practice_areas` and `profile_status` are blank there. They are only present
> on the **detail** endpoint, which is why Lawyer Records resolves each row
> through it.

**NLP service — `:8001`**

| Method | Path |
|--------|------|
| POST | `/api/translate` |
| POST | `/api/translate/indic-to-indic` |
| POST | `/api/voice` |
| POST | `/api/guidance` |
| POST | `/api/explain-order` |
| POST | `/api/court-order/explain` |
| POST | `/api/court-order/extract` |
| GET | `/health` |

All three model checkpoints are gated on HuggingFace. They are loaded lazily
on first use and released after `MODEL_IDLE_SECONDS`, which brings the idle
footprint from roughly 4.5 GB down to about 370 MB.

`/api/explain-order` turns an uploaded court order into plain language;
`/api/court-order/explain` is the newer pipeline: it accepts a multipart
PDF upload (or the old pasted-text body) and returns a stable shape of
`summary` plus the five document sections — Case Details, Proceedings,
Order, Signatures, Document Certification — with `metadata.ocr_used`,
`page_count` and the security scan result. Uploaded files are validated
(PDF only, size cap), scanned for active content, extracted to a temp
file that is always deleted, and never executed; sections the document
does not contain come back as `"Not available in the document."` rather
than as invented text.

Every answer — the document and each of its sections — arrives in three
layers:

```text
layers.legal       the order exactly as the court wrote it
layers.simple      the same words, in everyday English
layers.translated  that plain English in हिंदी / मराठी
```

The middle layer is a deterministic rewrite of *wording* only
(`court_order_simple_english.py`): "the matter is adjourned" becomes
"the hearing has been postponed", while names, dates, case numbers and
citations pass through untouched, and a passage with no plain
equivalent is left exactly as written. The translation model is given
that layer rather than the legalese, so step three reads the way a
person would say it. Ask for `language=hi` or `language=mr` (form field
on an upload, `language` in a JSON body for pasted text) to get step
three; English answers with two layers.

`/api/guidance` is the rule scorer behind **Voice NyayMitra**. A rule
matches on *coverage* — how much of the rule's own phrasing the question
actually covers — rather than on the raw score, because a near-miss can
out-score a genuine match.

---

## Testing and CI

```powershell
cd NyayMitra-feature-lawyer-api
python -m pytest              # 37 checks: CNR validation, timeline, orders,
                              # provider failures — no server, no network
python tests/smoke_cases_api.py http://127.0.0.1:8000   # against a live server
```

```powershell
cd NyayMitra-feature-nlp-translation
$env:TRANSLATION_API_URL = 'http://127.0.0.1:8001'
$env:PYTHONUTF8 = '1'
python -u e2e_check.py          # 6 checks across translate / indic-to-indic / voice
```

```powershell
cd frontend
npm test                       # 34 checks: CNR lookup, case dashboard, Tell Us What Happened
npx tsc -b                      # types
npx eslint .                    # lint — note the react-hooks rules are on
npm run build                   # tsc + vite build
```

CI (`.github/workflows/ci.yml`) runs on pushes to `main` and `feature/**` and
on pull requests to `main`.

---

## Known gaps

These are real and deliberately left visible rather than papered over:

- **Case data is development data, not eCourts.** `GET /api/cases` and
  `GET /api/cases/cnr/{cnr}` now exist and serve 109 CNR records through
  `cases/provider.py`, but the default `DevelopmentCaseProvider` reads a
  file built from the project's own captures — every response says so in
  `data_source.live_ecourts_data: false`. `AuthorizedExternalCaseProvider`
  is the stub for a real authorised source and refuses to answer until
  `CASE_EXTERNAL_DSN` is set; nothing is scraped from eCourts.
- **Authority grants, account status and chat *deletion* are
  `localStorage` mocks.** `authorityApi.ts` (work assignment lives
  here too) and `accountApi.ts` mirror the real shapes so each swap
  is a one-file change when the endpoints arrive. `chatApi.ts` now
  runs against the live `/api/chat` endpoints by default (its
  localStorage store is kept behind `VITE_CHAT_MODE=mock`), and the
  inbox hides its delete control in API mode because the server
  keeps message history by design — there is no delete endpoint.
  The verification overlay in `lawyerApi.ts` is
  still a local mock as well — its backend (`/api/admin/lawyers`)
  is live now and documented in the Postman collection, waiting for
  the Admin Dashboard to be pointed at it.
- **Auth now runs on the lawyer service** (it used to be frontend-mock
  only): `POST /api/auth/register`, `POST /api/auth/register/lawyer`,
  `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`
  and `GET /api/auth/lawyer/profile`, plus the ADMIN-only lawyer
  verification API (`GET/PATCH /api/admin/lawyers[/{lawyer_id}]`),
  backed by one SQLite file (`data/nyaymitra.db`,
  schema `database/auth_schema.sql`). Lawyer registration lands
  `PENDING`; only an ADMIN can move it to `APPROVED`/`REJECTED`
  (self-approval is refused server-side). The register page offers
  **Create User Account** or **Create Lawyer Account**; the lawyer
  form adds optional profile fields (bar council, experience, phone,
  bio) and uploads the licence document in the same submission:
  `POST /api/auth/lawyer/verification-document` (multipart, PDF/JPG/
  PNG, max 10 MB, magic-byte checked, one replaceable copy per
  lawyer under the gitignored `data/uploads/verification/`, never
  served statically). Bytes leave the server only through the
  lawyer's own `GET /api/auth/lawyer/verification-document` or the
  ADMIN-only `GET /api/admin/lawyers/{lawyer_id}/document`, and the
  registration/list/detail responses carry the document *metadata*
  (`document: {filename, mime_type, size_bytes, sha256, uploaded_at}`
  or `null`) for the admin dashboard to display. Until an admin
  approves, the register page and the lawyer dashboard say
  "Your lawyer registration is pending admin verification." The
  schema is portable SQL reserved for a later PostgreSQL migration;
  the legacy Postgres tables are untouched. Account deactivation is
  still a frontend-only mock.
- **Chat runs on the lawyer service** (Phase 3): `GET /api/chat/lawyers`
  lists APPROVED lawyers only (PENDING/REJECTED never appear; no email,
  licence id or phone leaves the server), `GET/POST
  /api/chat/conversations` is the citizen side, `GET/POST
  /api/chat/lawyer/conversations` the verified-lawyer side, and
  `GET /api/chat/conversations/{id}[/messages]` plus
  `POST .../messages` read and append history — plain HTTP, no
  WebSockets, one thread per (citizen, lawyer) pair that is reused
  rather than duplicated, with an optional `case_cnr` link (4 letters
  + 12 digits, same format `cases/routes.py` enforces) to My Cases.
  Identity always comes from the bearer session: payloads cannot name
  a sender or an owner (extra identity fields are 422), threads are
  visible only to their two participants (anyone else gets 404, so
  ids cannot be probed), PENDING/REJECTED lawyers get 403 with their
  own status, and signed-out requests get 401. Messages persist in the
  same `data/nyaymitra.db` (`conversations`/`messages` already in
  `database/auth_schema.sql` — no new tables, no schema change). The
  shared inbox (`ChatPage`) uses the API by default
  (`VITE_CHAT_MODE=api`); its New chat picker shows the verified
  directory, and the ✕ delete control appears only in mock mode.
  Covered by `tests/test_chat_api.py`, `chatApi.test.ts`,
  `ChatPage.test.tsx` and the `Chat (User ↔ Lawyer)` folder of the
  Postman collection.
- **Newly issued staff fall back to default authorities and no work
  assignment.** Staff issued during a session do not appear in the seeded
  account list until reload.
- **Urgency has no model.** Voice NyayMitra's *Urgency of your incident*
  panel says so plainly rather than inventing a number; the endpoint is
  awaited.
- **Delay prediction has no model.** Delay Analysis shows the ongoing
  cases and the **Predict Delay** control with its reasoning, but the
  result panel is a placeholder until the model API lands.
- **`LAWYER_0003` differs between mock and API.** The mock session calls it
  Adv. Rohan Deshmukh; the database has another advocate at that ID.
- **React Compiler is not enabled.** `react()` is called without `compiler: true`
  and `oxc-transform-react` is not installed — only its lint rules arrive via
  `eslint-plugin-react-hooks`. Do not rely on automatic memoization.

---

## Further reading

- [`frontend/README.md`](frontend/README.md) — Vite template notes, ESLint setup
- [`NyayMitra-feature-lawyer-api/README.md`](NyayMitra-feature-lawyer-api/README.md) — lawyer API integration guide
- [`docs/auth-decision.md`](docs/auth-decision.md) — how sign-in decides the role
- [`docs/my-cases.md`](docs/my-cases.md) — My Cases: CNR lookup, case dashboard, the development dataset and its provider
- [`docs/pwa-strategy.md`](docs/pwa-strategy.md) — offline strategy
- [`docs/postman/NyayMitra.postman_collection.json`](docs/postman/NyayMitra.postman_collection.json) — API collection

---

# NyayMitra - Delay Prediction Models

Machine-learning service that predicts two time intervals for Indian court cases:

1. **Days to next hearing** - the original model, trained in `notebooks/04_model_building.ipynb`.
2. **Days to disposal** - the newer model, trained by `src/train_disposal_model.py`.

`src/api.py` returns both in a single response
(`predicted_next_hearing_days` and `predicted_disposal_days`).

## Layout

| Path | Description |
|------|-------------|
| `src/api.py` | FastAPI service exposing `/predict-delay` and `/health` |
| `src/delay_predictor.py` | Inference code for **both** models |
| `src/train_disposal_model.py` | Training script for the disposal model |
| `notebooks/04_model_building.ipynb` | Training notebook for the next-hearing model |
| `models/` | Trained artifacts for **both** models (keep together) |
| `requirements.txt` | Pinned Python dependencies |

## Model artifacts

`models/` holds both sets - they must stay together:

- **Next hearing:** `delay_next_hearing_model.pkl`, `feature_columns.pkl`,
  `model_type.pkl`, `court_pace_lookup.pkl`, `case_type_pace_lookup.pkl`,
  `overall_mean_pace.pkl`, `resid_std.pkl`
- **Disposal:** `delay_disposal_model.json`, `feature_columns_disposal.pkl`,
  `case_type_pace_lookup_disposal.pkl`, `court_pace_lookup_disposal.pkl`,
  `overall_mean_pace_disposal.pkl`, `resid_std_disposal.pkl`,
  `model_type_disposal.pkl`, `numeric_defaults_disposal.pkl`,
  `target_cap_disposal.pkl`, `target_report_disposal.pkl`,
  `disposal_model_status.pkl`

## Usage

```bash
pip install -r requirements.txt
cd src
uvicorn api:app --host 0.0.0.0 --port 8000
```

```bash
curl -X POST http://localhost:8000/predict-delay \
  -H "Content-Type: application/json" \
  -d '{"case_type": "Cri.Appeal", "court": "...", "district": "...", "state": "..."}'
```

## Data

Training data (`data/raw/`, `data/processed/`, `data/disposedata/`, `*.csv`) is
**not** shipped with this repository. See `.gitignore`.

One narrow exception: the three JSON files the intent + incident pipeline
needs at runtime (`data/raw/incident_examples.json`,
`data/raw/incident_categories.json`, `data/raw/incident_facts.json`) are
un-ignored by exact path. Every other file under `data/` stays ignored.

---

# NyayMitra - Tell Us What Happened (intent + incident pipeline)

The ML layer that turns one free-text message into structured JSON for the
NLP / legal-explanation layer: intent (INCIDENT | CASE_QUESTION | FOLLOW_UP),
incident category (INC001..INC025), extracted facts and the list of missing
information. It is a separate feature from the delay-prediction models above;
`/predict-delay` is untouched by it.

## Layout

| Path | Description |
|------|-------------|
| `src/incident_pipeline.py` | `process_user_input(text)` - the single entry point |
| `src/intent_classifier.py` | 3-way intent classifier (nearest neighbour over multilingual MiniLM embeddings) |
| `src/incident_classifier.py` | 25-class incident category classifier, `resolve_category()` |
| `src/fact_extractor.py` | `extract_facts(text, category_id, language="en")` - regex/keyword fact extraction, Devanagari + Hinglish aware (no trained model) |
| `src/missing_info.py` | Expected facts minus found facts |
| `src/text_validation.py` | Shared input validation (HTML strip, empty reject, 1000-char cap) |
| `src/sentence_encoder.py` | Lazy `paraphrase-multilingual-MiniLM-L12-v2` singleton + embedding cache |
| `src/incident_data.py` | JSON lookup: `resources/` -> `data/raw/` -> `TellUsWhatHappened/data/` |
| `src/evaluate_intent.py` | Held-out evaluation: per-class accuracy, per-input confidence/margin table, guard grid |
| `src/test_incident_pipeline.py` | 12-case end-to-end test |
| `resources/intent_examples.json` | Training examples (65: 25 / 20 / 20) |
| `resources/intent_test_examples.json` | Held-out test set (60: English 10/10/10 + 10 Hindi + 10 Marathi + 10 Hinglish), never used in training |
| `resources/intent_ood_examples.json` | 15 out-of-scope inputs (en / hi / mr / hinglish) used only for guard calibration, never in training or in the 60-row test set |
| `data/raw/incident_*.json` | Team incident data needed at runtime (see `.gitignore` exceptions) |
| `models/intent_embeddings.npz`, `models/incident_category_embeddings.npz` | Cached training embeddings |

## Synthetic-data warning (read before trusting any number here)

**The 20 CASE_QUESTION and the 20 FOLLOW_UP examples in
`resources/intent_examples.json` are synthetic and have NOT been reviewed by
the team member who owns the incident data.** The 25 INCIDENT examples are
copied from the team file `data/raw/incident_examples.json` (that file is
itself flagged `is_synthetic=true` by its owner). All 60 held-out test
questions are hand-written synthetic text as well, and the 30 non-English
ones - 10 Hindi (Devanagari), 10 Marathi (Devanagari) and 10 Hinglish
(Roman script), 4/3/3 across the three intents - are **synthetic and
unreviewed by a native speaker** of those languages. The 15 out-of-scope
inputs in `resources/intent_ood_examples.json` are synthetic too, and were
written by the same process, so the guard cut-offs derived from them are
indicative only.

**Accuracy on the synthetic classes, and on Hindi / Marathi / Hinglish as a
whole, is not real-world performance.** It is indicative only, until the
incident-data owner (and a native speaker for the non-English rows) has
reviewed the examples.

## Held-out evaluation (`resources/intent_test_examples.json`)

60 questions, none of them used in training, run through
`src/evaluate_intent.py` on 2026-10-04 with the multilingual encoder
(`paraphrase-multilingual-MiniLM-L12-v2`, guards at `CONFIDENCE_THRESHOLD =
0.35` **and** `MARGIN_THRESHOLD = 0.16`):

| Language | Rows | INCIDENT | CASE_QUESTION | FOLLOW_UP | Overall | Incident-category | Guarded* |
|---|---|---|---|---|---|---|---|
| English | 30 | 10/10 (100%) | 10/10 (100%) | 8/10 (80%) | **93.3%** | 9/10 (90%) | 60.0% |
| Hindi (Devanagari) † | 10 | 4/4 (100%) | 1/3 (33%) | 3/3 (100%) | **80.0%** | 4/4 (100%) | 70.0% |
| Marathi (Devanagari) † | 10 | 4/4 (100%) | 2/3 (67%) | 3/3 (100%) | **90.0%** | 3/4 (75%) | 70.0% |
| Hinglish (Roman script) † | 10 | 3/4 (75%) | 2/3 (67%) | 3/3 (100%) | **80.0%** | 1/4 (25%) | 20.0% |

\* "Guarded" = accuracy once **both** guards are applied (confidence below
0.35 **or** class gap below 0.16 -> the pipeline answers `unclear`, which
counts as a wrong answer). Pooled: **34/60 = 56.7%**, with 0 wrong answers
and 0 out-of-scope inputs leaked through.
† **Hindi, Marathi and Hinglish rows are synthetic and unreviewed by a
native speaker - indicative only, not real-world performance.** CASE_QUESTION
and FOLLOW_UP are synthetic in every language.

Notable misses: English categorised the Instagram-takeover row as INC005
(fake profile) instead of INC003 and lost two short follow-ups; two Hindi
case questions came back as INCIDENT / FOLLOW_UP with *high* confidence
(0.81 / 0.74) - no confidence cut-off can catch those (0.814 is the highest
wrong confidence in the whole scan), but the class gap does (0.064 / 0.067,
both below 0.16); most correct Hinglish answers score below 0.35, which is
why its guarded accuracy is 20%.

### Out-of-scope guard calibration (`resources/intent_ood_examples.json`)

15 out-of-scope inputs (4 English, 4 Hindi, 4 Marathi, 3 Hinglish -
greetings, small talk, unrelated questions) were scored alongside the 60
test rows. Per input, `src/evaluate_intent.py` prints the confidence, the
raw top-1 minus top-2 margin, and the **class gap** (score of the winning
label's nearest neighbour minus the best neighbour of any *other* label -
raw top1-top2 is misleading when the two top neighbours belong to the same
class):

| group | n | confidence min / mean / max | raw margin min / mean / max | class gap min / mean / max |
|---|---|---|---|---|
| correct | 53 | 0.208 / 0.481 / 0.738 | 0.001 / 0.120 / 0.336 | 0.009 / 0.225 / 0.455 |
| wrong | 7 | 0.171 / 0.485 / **0.814** | 0.011 / 0.047 / 0.077 | 0.011 / 0.060 / **0.116** |
| out-of-scope | 15 | 0.104 / 0.226 / **0.341** | 0.004 / 0.047 / 0.132 | 0.011 / 0.072 / **0.157** |

The three numbers the cut-offs are built from:

* minimum correct confidence **0.208**, maximum out-of-scope confidence
  **0.341**, maximum wrong confidence **0.814**
* maximum out-of-scope class gap **0.157**, maximum wrong class gap
  **0.116**, minimum correct class gap 0.009

Guard grid (answer only when `confidence >= thr AND class gap >= m`,
`correct lost` = correct answers the guard turns into `unclear`):

| thr | gap | correct kept | correct lost | wrong leaked | OOD leaked |
|---|---|---|---|---|---|
| 0.35 | 0.00 | 42 | 11 | 4 | 0 |
| 0.35 | 0.12 | 36 | 17 | 0 | 0 |
| **0.35** | **0.16** | **34** | **19** | **0** | **0** |
| 0.30 | 0.16 | 36 | 17 | 0 | 0 |
| 0.25 | 0.16 | 38 | 15 | 0 | 0 |
| 0.45 | 0.00 (previous state) | 33 | 20 | 3 | 0 |

**Applied** (`src/incident_pipeline.py`, constants, commented with this
provenance): `CONFIDENCE_THRESHOLD = 0.35` - just above the highest
out-of-scope confidence (0.341); `MARGIN_THRESHOLD = 0.16` - just above the
highest class gap of a wrong answer (0.116) and of an out-of-scope input
(0.157). **Each guard on its own already excludes all 15 out-of-scope
inputs**; together they exclude all 15 OOD and all 7 wrong answers and keep
34 of 53 correct answers (19 correct answers are lost to `unclear`, against
20 lost by the previous 0.45-only guard, which leaked 3 wrong answers).

Alternatives shown for the record, **not applied**: `0.25 / 0.16` is the
zero-leak accuracy maximiser (38 kept, 15 lost, 0 wrong, 0 OOD); `0.35 /
0.00` keeps 42 correct but leaks 4 wrong answers; the old `0.45`-only guard
kept 33 correct and leaked 3 wrong. Confidence alone cannot separate the
two high-confidence wrong Hindi answers (0.81 / 0.74), so raising the
threshold is not the fix - those need training examples.


## API

`POST /understand-situation` (30 requests/minute) with `{"text": "..."}`:

```json
{
  "intent": "incident",
  "incident_category": "online_financial_fraud_unauthorized_digital_transaction",
  "category_id": "INC001",
  "confidence": 0.83,
  "facts": {"amount": "5000"},
  "missing_information": ["transaction_date"],
  "message": null
}
```

`incident_category` is a snake_case slug, `category_id` is the `INC001`-style
id, and fact keys are the exact `fact_or_entity` names from
`data/raw/incident_facts.json`. For CASE_QUESTION / FOLLOW_UP the
`incident_category`, `category_id`, `facts` and `missing_information` fields
are `null`. Empty input returns HTTP 400.

**Guards.** `incident_pipeline` has two constants that decide whether the
pipeline answers or asks again:

```python
CONFIDENCE_THRESHOLD = 0.35   # above max out-of-scope confidence (0.341)
MARGIN_THRESHOLD     = 0.16   # above max wrong class gap (0.116) and max OOD class gap (0.157)
```

If the score that produced the answer (the incident category score for
INCIDENT, the intent score otherwise) is below `CONFIDENCE_THRESHOLD`, **or**
the class gap to the runner-up intent is below `MARGIN_THRESHOLD`, the
response is `{"intent": "unclear", "confidence": <score>, "message":
"…Please rephrase… (gap 0.10 to the runner-up intent is below the 0.16
margin threshold)", "incident_category": null, "category_id": null, "facts":
null, "missing_information": null}`. Tune both cut-offs in that one place;
the end-to-end test asserts the contract (unclear iff below either
threshold, and a message set exactly when unclear). The numbers behind
0.35 / 0.16 are in "Out-of-scope guard calibration" above.

**Fact extraction** (`extract_facts(text, category_id, language="en")`) is
script-aware, not language-aware: Devanagari rules fire on Devanagari text
even when `language` defaults to `"en"`, so a Hindi sentence typed into the
English default still yields dates, amounts, payment method and reference
number (Devanagari digits are normalised, and the amount rule picks the
money cue closest to the number, so "20000 रुपये UPI से 14 सितंबर" extracts
`20000`, not `14`). `language` only selects the relative-date vocabulary
("kal"/"कल") and turns on the Hinglish roman terms. English text takes the
original code path unchanged - verified byte-for-byte against the
pre-change output for all 44 English probe inputs (SHA-256
`8875f4c8fe8b059651e06250dec671c1372309736dfb979fc9990bfcf5413dce`).

The models, the JSON data and the embedding matrices are loaded at **API
startup** (FastAPI lifespan hook), not on the first request, so the first
call does not pay the model-load cost. `/predict-delay` keeps its own
defensive import and is unaffected if this feature fails to load.

## Encoder and embeddings

Encoder: **`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`**
(384-dim, 50 languages incl. Hindi and Marathi), set in
`src/sentence_encoder.py::MODEL_NAME`. It replaced the English-only
`all-MiniLM-L6-v2` so Hindi / Marathi / Hinglish input is embedded in the
same space as the English training examples.

**First run downloads ~480 MB** (479,729,050 bytes in the HuggingFace cache:
`model.safetensors` 470,641,600 B plus the tokenizer files) from the
HuggingFace hub; every later start reuses that local cache. The old
`all-MiniLM-L6-v2` cache (~87 MB) is no longer used.

`models/intent_embeddings.npz` (93,034 bytes) and
`models/incident_category_embeddings.npz` (178,285 bytes) are the cached
training embeddings for that encoder - both far below any repo size limit, so
they are committed. If either file is deleted, `src/sentence_encoder.py`
regenerates it on the next startup: the cache is keyed by a SHA-256 of the
model name plus the exact texts, so editing a data file - or changing
`MODEL_NAME` - invalidates both files and rewrites them automatically.
