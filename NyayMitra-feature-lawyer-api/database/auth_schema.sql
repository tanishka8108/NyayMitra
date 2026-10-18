-- =========================================================
-- NyayMitra — auth / verification / chat schema
--
-- Runs on SQLite today (the only database available in this
-- environment). Written as portable SQL so it can later be
-- applied to PostgreSQL unchanged apart from two noted
-- substitutions:
--     INTEGER PRIMARY KEY AUTOINCREMENT  ->  BIGSERIAL PRIMARY KEY
--     (SQLite auto-assigns rowid for the INTEGER PRIMARY KEY)
--
-- Applied automatically and idempotently (CREATE ... IF NOT EXISTS)
-- by database/sqlite_db.py on first use. Nothing here drops or
-- alters any existing table: the legacy PostgreSQL tables in
-- lawyer_database.sql / case_database.sql are untouched.
--
-- Roles: exactly USER / LAWYER / ADMIN (Phase 1 decision). There is
-- no self-registration path for ADMIN — the demo admin is seeded by
-- database/seed_demo_accounts.py for integration testing only.
-- =========================================================

-- ---------------------------------------------------------
-- users — one login system for every role.
-- password_hash holds PBKDF2-HMAC-SHA256 in the format
--     pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>
-- (see auth/security.py). Plaintext passwords are never stored.
-- is_demo = 1 marks seeded DEMO/TEST accounts so they can never be
-- mistaken for real user data.
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          VARCHAR(250) NOT NULL,
    email         VARCHAR(320) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role          VARCHAR(10)  NOT NULL DEFAULT 'USER'
                  CHECK (role IN ('USER', 'LAWYER', 'ADMIN')),
    is_demo       INTEGER      NOT NULL DEFAULT 0
                  CHECK (is_demo IN (0, 1)),
    created_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS users_email_unique
    ON users (email);

-- ---------------------------------------------------------
-- lawyers — account-linked lawyer registration.
-- Reuses the public key shape of the existing PostgreSQL
-- directory (public.lawyers.lawyer_id is a VARCHAR primary key
-- like this one) while adding the account link and the
-- verification workflow the directory table never had:
-- PENDING -> APPROVED / REJECTED, decided server-side by ADMIN
-- only (verification endpoints land in a later phase).
--
-- lawyer_id keeps the project's LAWYER_NNNN convention so the
-- frontend's ChatTarget / session.lawyerId strings work unchanged.
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS lawyers (
    lawyer_id           VARCHAR(20)  PRIMARY KEY,
    user_id             INTEGER      NOT NULL UNIQUE
                        REFERENCES users (id) ON DELETE CASCADE,
    license_id          VARCHAR(100) NOT NULL,
    practice_areas      TEXT,
    -- Phase 2b optional profile details ("other relevant lawyer
    -- profile information"), all nullable — registration predating
    -- them reads NULL. The same four are added to pre-existing
    -- files by the guarded ALTER in database/sqlite_db.py, since
    -- CREATE ... IF NOT EXISTS will not touch an old table.
    bar_council              VARCHAR(200),
    years_of_experience      INTEGER,
    professional_phone_number VARCHAR(50),
    professional_bio         TEXT,
    verification_status VARCHAR(10)  NOT NULL DEFAULT 'PENDING'
                        CHECK (verification_status IN
                               ('PENDING', 'APPROVED', 'REJECTED')),
    verified_by         INTEGER      REFERENCES users (id),
    verified_at         TIMESTAMP,
    created_at          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- One licence cannot back two accounts.
CREATE UNIQUE INDEX IF NOT EXISTS lawyers_license_unique
    ON lawyers (license_id);

-- ---------------------------------------------------------
-- sessions — opaque random bearer tokens.
-- Only the SHA-256 hash of a token is stored, so a leaked
-- database never hands out usable sessions. Expiry is checked
-- on every authenticated request.
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS sessions (
    token_hash CHAR(64)   PRIMARY KEY,
    user_id    INTEGER    NOT NULL
               REFERENCES users (id) ON DELETE CASCADE,
    created_at TIMESTAMP  NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP  NOT NULL
);

CREATE INDEX IF NOT EXISTS sessions_user_idx
    ON sessions (user_id);

-- ---------------------------------------------------------
-- conversations — one thread per (citizen, lawyer) pair, as the
-- existing mock chat already models it. case_cnr is an optional
-- starting context; it is a plain string because cases live in
-- the file-backed dataset, not in this database.
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS conversations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL
               REFERENCES users (id) ON DELETE CASCADE,
    lawyer_id  VARCHAR(20) NOT NULL
               REFERENCES lawyers (lawyer_id) ON DELETE CASCADE,
    case_cnr   CHAR(16),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS conversations_pair_unique
    ON conversations (user_id, lawyer_id);

CREATE INDEX IF NOT EXISTS conversations_user_idx
    ON conversations (user_id);

CREATE INDEX IF NOT EXISTS conversations_lawyer_idx
    ON conversations (lawyer_id);

-- ---------------------------------------------------------
-- messages — plain request/response chat, no WebSockets.
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL
                    REFERENCES conversations (id) ON DELETE CASCADE,
    sender_id       INTEGER NOT NULL
                    REFERENCES users (id),
    message         TEXT    NOT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS messages_conversation_idx
    ON messages (conversation_id, id);

-- ---------------------------------------------------------
-- lawyer_documents — the licence/registration proof a lawyer
-- attaches at registration (Phase 2b). ONE row per lawyer
-- (PRIMARY KEY on lawyer_id): re-uploading replaces the row and
-- the previous file is deleted, so no unnecessary copies exist.
--
-- Only metadata lives here; the bytes sit in
--   data/uploads/verification/<server-generated-name>
-- which is deliberately NOT served statically — retrieval is a
-- ADMIN-only authenticated endpoint (GET
-- /api/admin/lawyers/{id}/document). The filename on disk is
-- generated by the server, never derived from user input.
--
-- Portable SQL (INTEGER/ TIMESTAMP notes as above); the file
-- storage uses plain pathlib writes, no database extension.
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS lawyer_documents (
    lawyer_id          VARCHAR(20)  PRIMARY KEY
                       REFERENCES lawyers (lawyer_id) ON DELETE CASCADE,
    original_filename  VARCHAR(255) NOT NULL,
    stored_filename    VARCHAR(255) NOT NULL,
    mime_type          VARCHAR(100) NOT NULL,
    size_bytes         INTEGER      NOT NULL,
    sha256             CHAR(64)     NOT NULL,
    uploaded_at        TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------
-- saved_cases — server-side My Cases (one citizen's shortlist).
--
-- WHY THIS EXISTS ALONGSIDE THE BROWSER STORE
-- frontend/src/api/caseApi.ts keeps `nyaymitra.cases.added.v1` in
-- localStorage so the screens render on the first pass with no
-- request to wait for. That copy belongs to one browser and cannot
-- survive a new machine or a cleared profile. This table is the
-- same shortlist held by the server, so it can be read back after
-- a refresh, a restart or a reinstall. The browser rows are NOT
-- migrated here: until the frontend reads this endpoint, existing
-- saved cases stay exactly where they are.
--
-- WHAT IS STORED
-- Only the CNR and who saved it — never a copy of the case. The
-- case record itself lives in the provider's dataset and is the
-- single source of truth, so a corrected hearing date or a renamed
-- party is picked up on the next read instead of being frozen into
-- a stale duplicate. list endpoints join the record at read time.
--
-- OWNERSHIP
-- user_id is written from the server-side session (see
-- auth/security.py: get_current_user), never from the request
-- body. There is no column through which one account could name
-- another.
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS saved_cases (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL
                REFERENCES users (id) ON DELETE CASCADE,
    cnr_number  CHAR(16) NOT NULL,
    saved_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Duplicate-save protection is structural, not just a code check:
-- a second save of the same CNR by the same account can never
-- insert. ON CONFLICT target of this unique pair is what the
-- write path relies on.
CREATE UNIQUE INDEX IF NOT EXISTS saved_cases_user_cnr_unique
    ON saved_cases (user_id, cnr_number);

CREATE INDEX IF NOT EXISTS saved_cases_user_idx
    ON saved_cases (user_id);
