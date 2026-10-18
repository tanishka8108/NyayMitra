-- ============================================================
-- NyayMitra — My Cases schema
--
-- The API ships with a file-backed development provider (see
-- cases/provider.py), so nothing here is applied automatically.
-- This file is the schema to load when the project gets a
-- PostgreSQL instance it is entitled to use:
--
--     psql -U nyaymitra -d nyaymitra -f case_database.sql
--
-- then set CASE_DATA_PROVIDER=external and implement
-- AuthorizedExternalCaseProvider against these tables.
--
-- Data in the tables loaded from cases/data/development_cases.jsonl
-- is development data captured manually from the eCourts site — it is
-- not live eCourts data, and data_origin records that on every row.
-- ============================================================

BEGIN;

CREATE TABLE IF NOT EXISTS cases (
    cnr_number           CHAR(16) PRIMARY KEY,
    case_type            TEXT        NOT NULL,
    case_title           TEXT,
    filing_number        TEXT,
    filing_date          DATE,
    registration_number  TEXT,
    registration_date    DATE,
    first_hearing_date   DATE,
    next_hearing_date    DATE,
    disposal_date        DATE,
    business_on_date     DATE,
    case_status          TEXT        NOT NULL DEFAULT 'Unknown',
    nature_of_disposal   TEXT,
    current_case_stage   TEXT,
    presiding_judge      TEXT,
    court_number_and_judge TEXT,
    court_name           TEXT,
    court_state          TEXT,
    court_district       TEXT,
    court_complex        TEXT,
    petitioner_name      TEXT,
    petitioner_advocate  TEXT,
    applied_act          TEXT,
    applied_section      TEXT,
    fir_number           TEXT,
    police_station       TEXT,
    record_source        JSONB,
    data_quality_flags   JSONB,
    data_origin          TEXT        NOT NULL DEFAULT 'development_dataset',
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT cases_cnr_format_check
        CHECK (cnr_number ~ '^[A-Z]{4}[0-9]{12}$')
);

CREATE TABLE IF NOT EXISTS case_parties (
    case_party_id  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cnr_number     CHAR(16) NOT NULL REFERENCES cases (cnr_number) ON DELETE CASCADE,
    party_type     TEXT     NOT NULL CHECK (party_type IN ('PETITIONER', 'RESPONDENT')),
    party_name     TEXT     NOT NULL,
    advocate_name  TEXT,
    position       INT      NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS case_timeline (
    case_timeline_id   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cnr_number         CHAR(16) NOT NULL REFERENCES cases (cnr_number) ON DELETE CASCADE,
    row_number         INT,
    judge              TEXT,
    business_on_date   DATE,
    hearing_date       DATE,
    purpose_of_hearing TEXT
);

CREATE TABLE IF NOT EXISTS case_orders (
    case_order_id  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cnr_number     CHAR(16) NOT NULL REFERENCES cases (cnr_number) ON DELETE CASCADE,
    order_type     TEXT,
    order_number   TEXT,
    order_date     DATE,
    order_details  TEXT,
    order_section  TEXT
);

CREATE INDEX IF NOT EXISTS idx_cases_status        ON cases (lower(case_status));
CREATE INDEX IF NOT EXISTS idx_cases_state_district ON cases (lower(court_state), lower(court_district));
CREATE INDEX IF NOT EXISTS idx_cases_next_hearing  ON cases (next_hearing_date);
CREATE INDEX IF NOT EXISTS idx_cases_case_type     ON cases (lower(case_type));
CREATE INDEX IF NOT EXISTS idx_case_parties_cnr    ON case_parties (cnr_number);
CREATE INDEX IF NOT EXISTS idx_case_timeline_cnr   ON case_timeline (cnr_number, hearing_date);
CREATE INDEX IF NOT EXISTS idx_case_orders_cnr     ON case_orders (cnr_number, order_date);

CREATE OR REPLACE FUNCTION set_cases_updated_at() RETURNS TRIGGER AS
$$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS cases_updated_at ON cases;
CREATE TRIGGER cases_updated_at
    BEFORE UPDATE ON cases
    FOR EACH ROW EXECUTE FUNCTION set_cases_updated_at();

COMMIT;
