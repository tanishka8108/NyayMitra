# My Cases — CNR lookup and the case dashboard

My Cases is the screen a citizen opens to answer one question: *where does my
case stand?* It has two halves —

1. **the account's own list** — matters filed from this browser, kept in
   `localStorage` (`frontend/src/api/caseApi.ts`), and
2. **a CNR lookup** — a number typed in from a notice or an order sheet, answered
   by the case service and opened as a full dashboard.

The second half is what this document covers.

---

## User flow

```
My Cases
  └── CNR search box
        │  frontend checks the shape (4 letters + 12 digits)
        ▼
      GET /api/cases/cnr/{cnr}          ← NyayMitra-feature-lawyer-api
        │  route validates the CNR again (400 / 404 / 500)
        ▼
      CaseDataProvider                  ← cases/provider.py
        ├── DevelopmentCaseProvider     ← the team's own captures (default)
        └── AuthorizedExternalCaseProvider   (interface, refuses until configured)
        │
        ▼
      normalised record + metrics + chronological timeline
        │
        ▼
      Case dashboard: status · parties · court · schedule ·
      timeline · orders · next-steps guidance
```

Nothing about eCourts is scraped, and no CAPTCHA is bypassed anywhere in this
path. The default provider reads a file that ships with the repository.

---

## API endpoints

| Method | Route | Purpose |
|--------|-------|---------|
| `GET` | `/api/cases/cnr/{cnr}` | One case, normalised, for the dashboard |
| `GET` | `/api/cases` | Browsable list — `q`, `status`, `state`, `page`, `limit` |
| `GET` | `/api/cases/meta` | Provider provenance: which provider, how many records |

### Response of `GET /api/cases/cnr/{cnr}`

```jsonc
{
  "success": true,
  "case": {
    "cnr_number": "MHPU210000042026",
    "case_type": "Civil M.A. - Civil Misc. Application",
    "case_title": "…",
    "case_status": "Case pending",           // or "Case disposed"
    "filing_number": "1/2026",  "filing_date": "2026-01-02",
    "registration_number": "1/2026", "registration_date": "2026-01-02",
    "first_hearing_date": "2026-01-07",
    "next_hearing_date": "2026-10-07",
    "disposal_date": "",
    "current_case_stage": "Awaiting Notice",
    "presiding_judge": "DISTRICT JUDGE - 1 AND ADDL. SESSIONS JUDGE, …",
    "court_name": "Additional District Court",
    "court_state": "Maharashtra",
    "court_district": "Khed",                // "" when the source had none
    "petitioner_name": "…", "petitioner_advocate": "…",
    "respondents_list": ["…"],
    "parties": [ { "party_type": "PETITIONER", "party_name": "…",
                   "advocate_name": "…" } ],
    "case_history_timeline": [ /* hearing rows, oldest first */ ],
    "timeline":        [ /* the whole journey, oldest first */ ],
    "orders":          [ /* docket entries; [] when none */ ],
    "calculated_metrics": { "respondent_count": 1,
                            "total_case_age_days": 269,
                            "total_hearings_scheduled": 5,
                            "current_stage_duration_days": 12 }
  },
  "data_source": {
    "provider": "development",
    "label": "Offline development dataset",
    "live_ecourts_data": false,
    "disclaimer": "…"
  }
}
```

Only fields the source actually carries are returned. A value the capture did
not have comes back as `""` or `"Not available in the record."` — never filled
in from anywhere else.

### Status codes

| Status | When |
|--------|------|
| `200` | The CNR is well formed and the dataset holds it |
| `400` | Malformed CNR — the message says what a CNR looks like |
| `404` | Well formed CNR the dataset does not hold |
| `500` | The provider failed — a short message, **no traceback**, details in the server log |
| `503` | The selected provider is unavailable (e.g. `external` with no source configured) |

---

## CNR format

A CNR (Case Number Regular) is **16 characters: four letters then twelve
digits** — `MHPU210000042026` (Maharashtra / Pune, filed 2026).

Both sides enforce it:

- **Frontend** (`frontend/src/components/CnrLookup.tsx`) — the input is
  upper-cased as it is typed, separators (` `, `-`, `_`) are stripped, and the
  box shows what is still missing ("*4 more to go*"). The submit button stays
  disabled until the value matches `^[A-Z]{4}[0-9]{12}$`.
- **Backend** (`cases/cnr.py`) — the same normalisation, then the pattern, then
  a `400` with a message safe to show. A browser's say-so is not a say-so.

---

## Development data

### Where it comes from

The team collected case-status pages from the eCourts site **manually**, one at a
time, and kept them as normalised JSON captures:

- `MHPU210000042026_normalized (2).zip` in the repository root — extracted to
  `dev_data/` (132 capture files, 109 distinct CNRs, duplicates resolved by
  keeping the fullest record).

> **These are development / test / reference data.** They are not a live
> eCourts feed, they are not guaranteed current, and every API response says so
> in `data_source.live_ecourts_data: false`. Do not present them as live court
> data.

### How they become the API's dataset

```powershell
cd NyayMitra-feature-lawyer-api
.venv/bin/python -m cases.build_dev_dataset
```

`cases/build_dev_dataset.py` reads `dev_data/` and writes one JSON record per
line to `cases/data/development_cases.jsonl`, keeping only the fields the API
returns. The raw captures carry page text, table dumps and the court site's own
javascript — none of which belongs in an API response — so the build step strips
it and the finished file is asserted to contain no `displayPdf` and no session
token.

Current contents: **109 records — 73 pending, 36 disposed, 74 with orders,
23 without a district.**

### How they are used

`DevelopmentCaseProvider` loads that file once, in memory, and serves lookups
from it. Nothing is hard-coded into React: the frontend only ever sees the
HTTP response. To point the provider at a different set of captures, rebuild the
dataset or set `CASE_DATASET_PATH`.

---

## Provider abstraction

```
CaseDataProvider                     cases/provider.py
├── DevelopmentCaseProvider          the file above (default)
└── AuthorizedExternalCaseProvider   the seam for a real source
```

Select with an environment variable:

```powershell
$env:CASE_DATA_PROVIDER = 'development'   # default
$env:CASE_DATA_PROVIDER = 'external'      # refuses until a source exists
```

**Replacing the development provider with an authorised one** means:

1. Implement `AuthorizedExternalCaseProvider.get_case(cnr)` and
   `.list_cases(...)` against whatever the project is entitled to read —
   a database, an official API with credentials.
2. Return the *same* normalised record shape (`cases/build_dev_dataset.py` is
   the reference for the mapping).
3. Set `CASE_DATA_PROVIDER=external` (and `CASE_EXTERNAL_DSN`, or whatever the
   implementation reads).

The route handler, the frontend, the dashboard and the tests do not change.
Nothing in this repository implements CAPTCHA handling or browser scraping; an
authorised provider is expected to be an official interface the project has
permission to use.

---

## Database

The project's database technology is **PostgreSQL** (the lawyer service already
uses it via `database/connection.py`). No case tables existed, so
`case_database.sql` adds them, following the `lawyer_database.sql` convention:

| Table | Holds |
|-------|-------|
| `cases` | One row per CNR — identity, dates, status, court, primary parties, `data_origin` |
| `case_parties` | Petitioner and respondent rows with their advocates |
| `case_timeline` | Hearing rows in source order |
| `case_orders` | Docket entries |

Nothing is applied automatically — the service runs file-backed today:

```powershell
psql -U nyaymitra -d nyaymitra -f case_database.sql     # schema, once
python -m cases.load_dev_dataset                        # then the 109 records
$env:CASE_DATA_PROVIDER = 'external'; uvicorn main:app   # read from it
```

`cases/load_dev_dataset.py` uses the service's own connection settings (no
credentials of its own), writes inside one transaction, and is idempotent —
loading twice leaves the same rows. Every row it writes carries
`data_origin = 'development_dataset'`.

---

## Timeline rules

`cases/timeline.py` builds `timeline` from values already on the record —
nothing is invented:

| Event | Built from |
|-------|-----------|
| *Case filed* | `filing_date` (+ filing number) |
| *Case registered* | `registration_date`, skipped when it equals the filing date |
| *…purpose of hearing…* | every `case_history_timeline` row, described with its judge |
| *…order passed…* | every `orders` row |
| *Next hearing* | `next_hearing_date` — **only while the case is not disposed** |

- **Sorted oldest first**, stable, so a filing and a registration on the same
  day stay filing-then-registration.
- **Duplicate dates** keep their source order; nothing is dropped.
- **Missing dates** keep the event and place it last (`date: ""`), which the UI
  renders as *"Date not recorded"*.
- **Pending** cases end on *Next hearing*; **disposed** cases never show one,
  whatever listing date the capture happened to carry.
- `case_history_timeline` is sorted into the same order but is *not* given
  filing or next-hearing rows — several screens count it as hearings held.

---

## Frontend

| File | Role |
|------|------|
| `components/CnrLookup.tsx` | Search box, client-side validation, loading and error states, result card |
| `components/CaseDetail.tsx` | The dashboard: status, parties, court, schedule, guidance, orders, timeline |
| `pages/user/CaseSearchPage.tsx` | Wires the lookup to the detail view |
| `api/caseApi.ts` | `lookupCaseByCnr()` — the one HTTP call |
| `types/case.ts` | `Case`, `CaseOrder`, `CaseTimelineEvent`, `CaseDataSource` |

Empty states covered: no CNR entered (the box says so, the button is disabled),
CNR not found (the service's own 404 message), no timeline, no orders, and
missing optional fields (`—` / *"Not available in the record."*).

**Reuse, not duplication:** *What should I do next?* calls the existing
guidance service (`api/guidanceApi.ts`, `POST /api/guidance`) with a sentence
built only from this record's status, stage and listing. *Explain this order*
hands the reader to the Court Orders screen, where the existing extraction and
explanation pipeline (`api/courtOrderApi.ts`) reads a pasted or uploaded copy —
the docket entry alone has no document text to explain. Translation and voice
are untouched.

---

## Running the tests

```bash
# Backend — 37 checks, no server and no network needed
cd NyayMitra-feature-lawyer-api
.venv/bin/python -m pytest

# Backend against a running server
.venv/bin/uvicorn main:app --port 8000 &
python tests/smoke_cases_api.py http://127.0.0.1:8000
```

```bash
# Frontend — 25 checks, then the same gates CI runs
cd frontend
npm test                    # vitest: CNR lookup + case dashboard states
npx tsc -b                  # types
npx eslint .                # lint — the react-hooks rules are on
npm run build               # tsc + vite build
```

On Windows PowerShell the interpreter path is `.\.venv\Scripts\python.exe`
instead; everything else is the same.

`tests/test_cases_api.py` covers: a valid CNR, CNR normalisation, malformed
CNRs, unknown CNR, a complete timeline, chronological ordering, incomplete
data, a pending case, a disposed case, a case with orders, a case without
orders, an unexpected provider failure (500 with no traceback), provider
selection, listing filters and dataset integrity.

`frontend/src/components/CnrLookup.test.tsx` and
`frontend/src/components/CaseDetail.test.tsx` cover the screen: the empty
state, character validation and normalisation, the loading state, the
service's own refusal versus an unreachable service, the case summary and
status, the timeline in order (and its empty state), the orders list and
its empty state, the hand-off to Court Orders, and the next-steps panel's
answer and failure. The NLP features those screens reuse are covered by
`NyayMitra-feature-nlp-translation/e2e_check.py` (6 checks) — nothing in
My Cases touches them.

---

## Limitations

- The dataset is development data, not a live court feed.
- Order documents are not in the dataset — only the docket entries — so orders
  offer a hand-off to Court Orders rather than a download link.
- The PostgreSQL tables and loader are ready but unexercised here; this machine
  has no PostgreSQL instance to load them into.
