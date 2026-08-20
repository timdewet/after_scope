-- Declared imaging plan (modality/objective/timing tokens) for the session.
-- Biological plan fields already exist (planned_strain/condition/coverslip);
-- imaging intent is session-scoped context for the dashboard and CSV exports —
-- per-file imaging truth still comes from the CZI headers at ingest.
ALTER TABLE sessions ADD COLUMN planned_imaging TEXT;
