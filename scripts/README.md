# NyayMitra — startup

Repeatable Ubuntu/WSL procedure. Every script here is read-only about your
data: nothing is dropped, truncated, re-seeded or committed.

```bash
cd /home/tanishka/NyayMitra-capstone
./scripts/health.sh        # what is up right now?
./scripts/start_all.sh     # start anything that is down (safe to re-run)
./scripts/stop_all.sh      # stop only what start_all.sh started
```

`start_all.sh` never starts a second process on a port that is already
serving, so re-running it while something is up is harmless. Pass `--force`
to restart what is already running.

## Entry points and ports

| Service | Directory | Entry point | Port | Needs |
|---|---|---|---|---|
| Lawyer API (core) | `NyayMitra-feature-lawyer-api` | `main:app` | `8000` | Python `.venv` (present) |
| NLP / translation (core) | `NyayMitra-feature-nlp-translation` | `translate_service:app` | `8001` | Python `.venv` (present), cached HF models |
| Model API (core) | repo root, code in `src/` | `api:app` (`--app-dir src`) | `8002` | repo `.venv` |
| Frontend (core) | `frontend` | `npm run dev` | `5173` | Node 22 via nvm |
| PostgreSQL | — | — | `5432` | **optional** — see below |

PostgreSQL is only read by the lawyer directory. Authentication, chat and
My Cases run on SQLite (`NyayMitra-feature-lawyer-api/data/nyaymitra.db`),
so the app works without Postgres except for **Find a Lawyer** and
**Practice areas**, which answer `500` until the role and schema exist.

## Stop safely

```bash
./scripts/stop_all.sh          # services started by start_all.sh
./scripts/stop_all.sh --web    # just the frontend
sudo systemctl stop postgresql # only if you really mean to
```

Anything this repo did not start is left running — another team member's
Vite or uvicorn is never signalled.

## Environment variable names (values are never printed by these scripts)

| Variable | Read by | Default if unset |
|---|---|---|
| `VITE_API_BASE_URL` | frontend | `http://127.0.0.1:8000` |
| `VITE_TRANSLATION_API_URL` | frontend | `http://127.0.0.1:8001` |
| `VITE_TRANSLATION_API_KEY` | frontend | `nyaymitra-local-test-2026` |
| `VITE_MODEL_API_URL` | frontend | `http://127.0.0.1:8000` — set to `8002` in `frontend/.env` |
| `VITE_AUTH_MODE` / `VITE_CHAT_MODE` | frontend | `api` (mock only if explicitly set) |
| `NYAYMITRA_NLP_KEY` | NLP service | same local dev key as the frontend |
| `NYAYMITRA_AUTH_DB` | Lawyer API | `data/nyaymitra.db` (SQLite) |
| `NYAYMITRA_DB_HOST` / `_PORT` / `_NAME` / `_USER` / `_PASSWORD` | Lawyer API | `localhost` / `5432` / `nyaymitra` / `nyaymitra` / dev password from `docker-compose.yml` |

Lawyer API also uses `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`,
`PGPASSWORD` if you prefer libpq-style variables.

## Why the Model API is on 8002

Both the Lawyer API and the Model API were written for `:8000`, so they
cannot share it. The Lawyer API keeps `:8000` (the frontend's
`VITE_API_BASE_URL` default) and the Model API takes `:8002`, which is what
`frontend/.env` already points `VITE_MODEL_API_URL` at. `src/api.py` only
allows the origin `http://localhost:5173`, so the dev server must stay on
`5173`.

## Health endpoints (verified, not assumed)

| Service | Health path | Notes |
|---|---|---|
| Lawyer API | `GET /` | There is **no** `/health` route — `/` answers `200 {"message": "NyayMitra API is running"}`. `/health` returns 404 here. |
| NLP | `GET /health` | `{"status":"ok","model_loaded":false}` — `model_loaded` is a lazy-load flag, not a fault. |
| Model API | `GET /health` | `{"status":"ok"}` |
| Frontend | `GET /` | Vite dev server |
| PostgreSQL | `pg_isready -h 127.0.0.1 -p 5432` | |

`health.sh` exits non-zero if anything is failing, so it can be used as a
readiness gate in CI or a start script.

NLP accepts `Authorization: Bearer <NYAYMITRA_NLP_KEY>` and allows **any**
origin; the Lawyer and Model APIs allow only the Vite dev origins
(`localhost`/`127.0.0.1` on `5173`/`5174`/`8080`).

## Endpoints added by this session

`GET|POST /api/saved-cases` and `DELETE /api/saved-cases/{cnr}` — server-side
My Cases (SQLite, same file as auth/chat). See `cases/saved_routes.py` for why
it exists next to the browser's `localStorage` copy rather than replacing it.

## Stop/start cycle (tested)

`stop_all.sh --web` released `:5173`, `start_all.sh` brought it back, and an
immediate second `start_all.sh` spawned **no** duplicate processes — each
service printed `already serving on :NNNN (left alone)`. Only services a given
invocation actually launched receive a pid file, so a run that finds everything
already up will not hand a teammate's process to `stop_all.sh`.

Each service can be stopped on its own: `stop_all.sh --lawyer`, `--nlp`,
`--model` or `--web`. An unrecognised flag is refused with exit 2 and stops
nothing — earlier a typo silently fell back to stopping every service, which
turned a slip of the keyboard into a full outage.

## Logs

`~/.nyaymitra/logs/{lawyer,nlp,model,web}.log`, pid files in
`~/.nyaymitra/pids/`. Nothing is written into the repository.
